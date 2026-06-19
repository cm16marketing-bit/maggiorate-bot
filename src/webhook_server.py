import os
import re
import logging
import json
from fastapi import FastAPI, Request
from telegram import Bot
from dotenv import load_dotenv
from session_manager import SessionManager
from sheets_logger import log_response

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
session_mgr = SessionManager()


def extract_request_id(text):
    match = re.search(r'#?([A-F0-9]{8})', text.upper())
    return match.group(1) if match else None


def parse_esito(text):
    t = text.upper()
    if "APPROVATA" in t:
        return "approvata"
    elif "RIFIUTATA" in t:
        return "rifiutata"
    elif "CONTROPROPOSTA" in t:
        return "controproposta"
    return None


def strip_html(text):
    clean = re.sub(r'<[^>]+>', '', text)
    return clean.strip()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/trader-response")
async def trader_response(request: Request):
    # Log raw body per debug
    try:
        raw = await request.body()
        logger.info("RAW BODY: " + raw.decode("utf-8", errors="replace"))
        data = json.loads(raw)
    except Exception as e:
        logger.error("Parse error: " + str(e))
        return {"ok": False, "error": "invalid json"}

    logger.info("DATA RECEIVED: " + str(data))

    # Prova tutti i possibili campi dove Teams mette il testo
    message = (
        data.get("message") or
        data.get("content") or
        data.get("body") or
        data.get("text") or
        data.get("messageContent") or
        ""
    )
    sender = (
        data.get("sender") or
        data.get("from") or
        data.get("displayName") or
        "Trader"
    )

    # Rimuovi HTML dal messaggio Teams
    message = strip_html(str(message))
    logger.info("MESSAGE CLEAN: " + message)
    logger.info("SENDER: " + sender)

    if not message:
        logger.warning("Messaggio vuoto")
        return {"ok": False, "error": "messaggio vuoto"}

    request_id = extract_request_id(message)
    if not request_id:
        logger.warning("request_id non trovato in: " + message)
        return {"ok": False, "error": "request_id non trovato"}

    esito = parse_esito(message)
    if not esito:
        logger.warning("esito non trovato in: " + message)
        return {"ok": False, "error": "esito non trovato"}

    session = session_mgr.get_request(request_id)
    if not session:
        logger.warning("sessione non trovata: " + request_id)
        return {"ok": False, "error": "sessione non trovata"}

    tipster_id = session["tipster_id"]
    fields = session["fields"]
    evento = fields.get("evento", "")
    mercato = fields.get("mercato", "")

    session_mgr.update_stato(request_id, esito)

    if esito == "approvata":
        msg = "Richiesta #" + request_id + " — " + evento + " " + mercato + "\n\nESITO: APPROVATA\nRisposta di: " + sender
    elif esito == "rifiutata":
        msg = "Richiesta #" + request_id + " — " + evento + " " + mercato + "\n\nESITO: RIFIUTATA\nRisposta di: " + sender
    else:
        msg = "Richiesta #" + request_id + " — " + evento + " " + mercato + "\n\nCONTROPROPOSTA:\n" + message + "\n\nRisposta di: " + sender

    try:
        await bot.send_message(chat_id=tipster_id, text=msg)
        logger.info("Messaggio inviato a tipster " + str(tipster_id))
    except Exception as e:
        logger.error("Telegram error: " + str(e))
        return {"ok": False, "error": str(e)}

    try:
        log_response(request_id, esito, {"note": message})
    except Exception as e:
        logger.warning("Sheet error: " + str(e))

    return {"ok": True, "request_id": request_id, "esito": esito}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

import os
import re
import logging
from fastapi import FastAPI, Request
from telegram import Bot
from dotenv import load_dotenv
from session_manager import SessionManager
from sheets_logger import log_response

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI()
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
session_mgr = SessionManager()


def extract_request_id(text):
    # Cerca pattern tipo #A932B266 nel testo
    match = re.search(r'#([A-F0-9]{8})', text.upper())
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


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/trader-response")
async def trader_response(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid json"}

    message = data.get("message", "")
    sender = data.get("sender", "Trader")

    logger.info("Risposta trader ricevuta: " + message)

    # Estrai request_id dal messaggio
    request_id = extract_request_id(message)
    if not request_id:
        logger.warning("Nessun request_id trovato nel messaggio: " + message)
        return {"ok": False, "error": "request_id non trovato"}

    # Estrai esito
    esito = parse_esito(message)
    if not esito:
        logger.warning("Nessun esito trovato nel messaggio: " + message)
        return {"ok": False, "error": "esito non trovato"}

    # Recupera sessione
    session = session_mgr.get_request(request_id)
    if not session:
        logger.warning("Sessione non trovata per request_id: " + request_id)
        return {"ok": False, "error": "sessione non trovata"}

    tipster_id = session["tipster_id"]
    fields = session["fields"]
    evento = fields.get("evento", "")
    mercato = fields.get("mercato", "")

    # Aggiorna stato
    session_mgr.update_stato(request_id, esito)

    # Costruisci messaggio per tipster
    if esito == "approvata":
        msg = (
            "Aggiornamento richiesta #" + request_id + "\n"
            + evento + " - " + mercato + "\n\n"
            + "Esito: APPROVATA\n"
            + "Risposta di: " + sender
        )
    elif esito == "rifiutata":
        msg = (
            "Aggiornamento richiesta #" + request_id + "\n"
            + evento + " - " + mercato + "\n\n"
            + "Esito: RIFIUTATA\n"
            + "Risposta di: " + sender
        )
    else:
        # Controproposta — manda il testo completo del trader
        msg = (
            "Aggiornamento richiesta #" + request_id + "\n"
            + evento + " - " + mercato + "\n\n"
            + "CONTROPROPOSTA:\n"
            + message + "\n\n"
            + "Risposta di: " + sender
        )

    # Manda al tipster
    try:
        await bot.send_message(chat_id=tipster_id, text=msg)
        logger.info("Risposta inviata al tipster " + str(tipster_id))
    except Exception as e:
        logger.error("Errore invio Telegram: " + str(e))
        return {"ok": False, "error": str(e)}

    # Log sheet
    try:
        log_response(request_id, esito, {"note": message})
    except Exception as e:
        logger.warning("Sheet log error: " + str(e))

    return {"ok": True, "request_id": request_id, "esito": esito}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

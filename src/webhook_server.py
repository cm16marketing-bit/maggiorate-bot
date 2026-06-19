import os
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


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/trader-response")
async def trader_response(request: Request):
    try:
        raw = await request.body()
        logger.info("RAW: " + raw.decode("utf-8", errors="replace"))
        data = json.loads(raw)
    except Exception as e:
        logger.error("Parse error: " + str(e))
        return {"ok": False, "error": "invalid json"}

    request_id = data.get("request_id", "")
    esito = data.get("esito", "").lower()
    commento = data.get("commento", "")
    sender = data.get("sender", "Trader")
    quota_nuova = data.get("quota_nuova", "")
    stake_nuovo = data.get("stake_nuovo", "")
    budget_nuovo = data.get("budget_nuovo", "")
    note = data.get("note", "")

    logger.info("request_id: " + request_id + " esito: " + esito)

    if not request_id or not esito:
        return {"ok": False, "error": "dati mancanti"}

    session = session_mgr.get_request(request_id)
    if not session:
        logger.warning("Sessione non trovata: " + request_id)
        return {"ok": False, "error": "sessione non trovata"}

    tipster_id = session["tipster_id"]
    fields = session["fields"]
    evento = fields.get("evento", "")
    mercato = fields.get("mercato", "")
    header = "Richiesta #" + request_id + " — " + evento + " · " + mercato + "\n\n"

    session_mgr.update_stato(request_id, esito)

    if esito == "approvata":
        msg = header + "ESITO: APPROVATA"
        if commento:
            msg += "\nCommento: " + commento
        if sender and sender != "{{sender}}":
            msg += "\nRisposta di: " + sender

    elif esito == "rifiutata":
        msg = header + "ESITO: RIFIUTATA"
        if commento:
            msg += "\nCommento: " + commento
        if sender and sender != "{{sender}}":
            msg += "\nRisposta di: " + sender

    elif esito == "controproposta":
        msg = header + "CONTROPROPOSTA:\n"
        if quota_nuova:
            msg += "Quota approvata: " + quota_nuova + "\n"
        if stake_nuovo:
            msg += "Max stake: " + stake_nuovo + "\n"
        if budget_nuovo:
            msg += "Budget: " + budget_nuovo + "\n"
        if note:
            msg += "Note: " + note + "\n"
        if commento:
            msg += "Commento: " + commento + "\n"
        if sender and sender != "{{sender}}":
            msg += "Risposta di: " + sender
    else:
        msg = header + "Risposta: " + esito

    try:
        await bot.send_message(chat_id=tipster_id, text=msg)
        logger.info("Messaggio inviato a tipster " + str(tipster_id))
    except Exception as e:
        logger.error("Telegram error: " + str(e))
        return {"ok": False, "error": str(e)}

    try:
        log_response(request_id, esito, {"note": commento or note})
    except Exception as e:
        logger.warning("Sheet error: " + str(e))

    return {"ok": True, "request_id": request_id, "esito": esito}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

import os
import logging
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
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


def success_page(title, message):
    return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>""" + title + """</title>
    <style>
        body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: #f5f5f5; }
        .card { background: white; padding: 40px; border-radius: 12px; text-align: center; max-width: 400px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h2 { color: #333; margin-bottom: 10px; }
        p { color: #666; }
        .icon { font-size: 48px; margin-bottom: 16px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">""" + ("✅" if "approvata" in title.lower() else "❌" if "rifiutata" in title.lower() else "🔄") + """</div>
        <h2>""" + title + """</h2>
        <p>""" + message + """</p>
        <p style="margin-top:20px;font-size:12px;color:#999">Puoi chiudere questa finestra.</p>
    </div>
</body>
</html>""")


async def notify_tipster(request_id, esito, commento="", quota_nuova=""):
    session = session_mgr.get_request(request_id)
    if not session:
        logger.warning("Sessione non trovata: " + request_id)
        return False

    tipster_id = session["tipster_id"]
    fields = session["fields"]
    evento = fields.get("evento", "")
    mercato = fields.get("mercato", "")
    header = "Richiesta #" + request_id + " — " + evento + " · " + mercato + "\n\n"

    if session["stato"] != "in_attesa":
        logger.warning("Richiesta " + request_id + " gia processata")
        return False
    session_mgr.update_stato(request_id, esito)

    if esito == "approvata":
        msg = header + "ESITO: APPROVATA ✅"
        if commento:
            msg += "\nCommento: " + commento
    elif esito == "rifiutata":
        msg = header + "ESITO: RIFIUTATA ❌"
        if commento:
            msg += "\nCommento: " + commento
    else:
        msg = header + "CONTROPROPOSTA 🔄\n"
        if quota_nuova:
            msg += "Quota approvata: " + quota_nuova + "\n"
        if commento:
            msg += "Note: " + commento

    try:
        await bot.send_message(chat_id=tipster_id, text=msg)
        logger.info("Notifica inviata a tipster " + str(tipster_id))
        try:
            log_response(request_id, esito, {"note": commento})
        except Exception as e:
            logger.warning("Sheet error: " + str(e))
        return True
    except Exception as e:
        logger.error("Telegram error: " + str(e))
        return False


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/approve")
async def approve(id: str):
    ok = await notify_tipster(id, "approvata")
    if ok:
        return success_page("Approvata", "La risposta è stata inviata al tipster.")
    return success_page("Errore", "Richiesta non trovata o già processata.")


@app.get("/reject")
async def reject(id: str):
    ok = await notify_tipster(id, "rifiutata")
    if ok:
        return success_page("Rifiutata", "La risposta è stata inviata al tipster.")
    return success_page("Errore", "Richiesta non trovata o già processata.")


@app.get("/counter")
async def counter(id: str, quota: str = "", note: str = ""):
    ok = await notify_tipster(id, "controproposta", commento=note, quota_nuova=quota)
    if ok:
        return success_page("Controproposta", "La risposta è stata inviata al tipster.")
    return success_page("Errore", "Richiesta non trovata o già processata.")


@app.post("/trader-response")
async def trader_response(request: Request):
    try:
        data = json.loads(await request.body())
    except Exception as e:
        return {"ok": False, "error": "invalid json"}

    request_id = data.get("request_id", "")
    esito = data.get("esito", "").lower()
    commento = data.get("commento", "")
    quota_nuova = data.get("quota_nuova", "")

    ok = await notify_tipster(request_id, esito, commento, quota_nuova)
    return {"ok": ok, "request_id": request_id, "esito": esito}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

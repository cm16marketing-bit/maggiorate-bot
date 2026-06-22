import os
import logging
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
from session_manager import SessionManager
from sheets_logger import log_response

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
session_mgr = SessionManager()
SECRET = os.getenv("WEBHOOK_SECRET", "mb2026")


def confirm_page(request_id, esito, title, color, emoji, nome_tipster=""):
    """Pagina con form di conferma — il trader può aggiungere una nota e poi confermare."""
    tipster_display = (
        f'<div class="tipster">Tipster: <strong>{nome_tipster}</strong></div>'
        if nome_tipster else ""
    )
    return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Conferma risposta</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #f0f2f5; }
        .card { background: white; padding: 40px 32px; border-radius: 16px; text-align: center; max-width: 380px; width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.12); }
        .icon { font-size: 52px; margin-bottom: 16px; }
        h2 { color: #1a1a1a; font-size: 22px; margin-bottom: 8px; }
        .id { font-size: 13px; color: #888; margin-bottom: 10px; font-family: monospace; background: #f5f5f5; padding: 6px 12px; border-radius: 6px; display: inline-block; }
        .tipster { font-size: 14px; color: #555; margin-bottom: 20px; }
        .nota-label { text-align: left; font-size: 13px; color: #555; margin-bottom: 6px; font-weight: bold; }
        textarea { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 8px; font-size: 13px; resize: vertical; min-height: 80px; margin-bottom: 16px; font-family: Arial, sans-serif; color: #333; }
        textarea:focus { outline: none; border-color: """ + color + """; }
        .btn { display: block; padding: 14px 32px; border-radius: 10px; font-size: 16px; font-weight: bold; color: white; background: """ + color + """; border: none; cursor: pointer; width: 100%; margin-top: 8px; }
        .btn:hover { opacity: 0.9; }
        .cancel { display: inline-block; margin-top: 12px; font-size: 13px; color: #999; cursor: pointer; text-decoration: underline; background: none; border: none; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">""" + emoji + """</div>
        <h2>Conferma """ + title + """</h2>
        <div class="id">#""" + request_id + """</div>
        """ + tipster_display + """
        <form method="get" action="/confirm">
            <input type="hidden" name="id" value=\"""" + request_id + """\">
            <input type="hidden" name="esito" value=\"""" + esito + """\">
            <input type="hidden" name="secret" value=\"""" + SECRET + """\">
            <div class="nota-label">Nota del trader (opzionale):</div>
            <textarea name="commento" placeholder="es. accettiamo massimo 10mila euro a questa quota..."></textarea>
            <button type="submit" class="btn">""" + emoji + """ Conferma """ + title + """</button>
        </form>
        <button class="cancel" onclick="window.close()">Annulla</button>
    </div>
</body>
</html>""")


def result_page(title, message, success=True):
    emoji = "✅" if success else "❌"
    return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>""" + title + """</title>
    <style>
        body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #f0f2f5; }
        .card { background: white; padding: 40px 32px; border-radius: 16px; text-align: center; max-width: 380px; width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.12); }
        .icon { font-size: 52px; margin-bottom: 16px; }
        h2 { color: #1a1a1a; margin-bottom: 8px; }
        p { color: #666; font-size: 14px; }
        .note { margin-top: 20px; font-size: 12px; color: #aaa; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">""" + emoji + """</div>
        <h2>""" + title + """</h2>
        <p>""" + message + """</p>
        <p class="note">Puoi chiudere questa finestra.</p>
    </div>
</body>
</html>""")


async def notify_tipster(request_id, esito, commento="", quota_nuova=""):
    session = session_mgr.get_request(request_id)
    if not session:
        logger.warning("Sessione non trovata: " + request_id)
        return False
    if session["stato"] != "in_attesa":
        logger.warning("Richiesta " + request_id + " gia processata")
        return False

    tipster_id = session["tipster_id"]
    fields = session["fields"]
    evento = fields.get("evento", "")
    mercato = fields.get("mercato", "")
    nome_tipster = session.get("tipster_name", "")

    if nome_tipster:
        header = "Richiesta #" + request_id + " — " + nome_tipster + " · " + evento + " · " + mercato + "\n\n"
    else:
        header = "Richiesta #" + request_id + " — " + evento + " · " + mercato + "\n\n"

    session_mgr.update_stato(request_id, esito)

    if esito == "approvata":
        msg = header + "ESITO: APPROVATA ✅"
        if commento:
            msg += "\nNota del trader: " + commento
        reply_markup = None

    elif esito == "rifiutata":
        msg = header + "ESITO: RIFIUTATA ❌"
        if commento:
            msg += "\nNota del trader: " + commento
        reply_markup = None

    else:  # controproposta
        msg = header + "CONTROPROPOSTA 🔄\n"
        if quota_nuova:
            msg += "Quota approvata: " + quota_nuova + "\n"
        if commento:
            msg += "Nota del trader: " + commento
        msg += "\n\nVuoi accettare o rifiutare la controproposta?"
        # Bottoni inline per il tipster
        reply_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Accetta", callback_data="cp_accetta:" + request_id),
            InlineKeyboardButton("❌ Rifiuta", callback_data="cp_rifiuta:" + request_id),
        ]])

    try:
        await bot.send_message(
            chat_id=tipster_id,
            text=msg,
            reply_markup=reply_markup if esito == "controproposta" else None
        )
        logger.info("Notifica inviata a " + str(tipster_id))
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


# Step 1 — Mostra pagina di conferma con form + textarea nota
@app.get("/approve")
async def approve(id: str):
    session = session_mgr.get_request(id)
    nome_tipster = session.get("tipster_name", "") if session else ""
    return confirm_page(id, "approvata", "Approvazione", "#22c55e", "✅", nome_tipster)

@app.get("/reject")
async def reject(id: str):
    session = session_mgr.get_request(id)
    nome_tipster = session.get("tipster_name", "") if session else ""
    return confirm_page(id, "rifiutata", "Rifiuto", "#ef4444", "❌", nome_tipster)

@app.get("/counter")
async def counter(id: str):
    session = session_mgr.get_request(id)
    nome_tipster = session.get("tipster_name", "") if session else ""
    return confirm_page(id, "controproposta", "Controproposta", "#f59e0b", "🔄", nome_tipster)


# Step 2 — Processa dopo conferma esplicita
@app.get("/confirm")
async def confirm(id: str, esito: str, secret: str, commento: str = "", quota_nuova: str = ""):
    if secret != SECRET:
        return result_page("Accesso negato", "Token non valido.", success=False)
    ok = await notify_tipster(id, esito, commento, quota_nuova)
    if ok:
        labels = {"approvata": "Approvata", "rifiutata": "Rifiutata", "controproposta": "Controproposta"}
        return result_page(labels.get(esito, esito), "Risposta inviata al tipster.")
    return result_page("Errore", "Richiesta non trovata o già processata.", success=False)


@app.post("/trader-response")
async def trader_response(request: Request):
    try:
        data = json.loads(await request.body())
    except Exception:
        return {"ok": False, "error": "invalid json"}
    ok = await notify_tipster(
        data.get("request_id", ""),
        data.get("esito", "").lower(),
        data.get("commento", ""),
        data.get("quota_nuova", "")
    )
    return {"ok": ok}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

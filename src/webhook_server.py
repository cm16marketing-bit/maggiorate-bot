import os
import logging
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
from dotenv import load_dotenv
from session_manager import SessionManager
from sheets_logger import log_response
import aiohttp

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
session_mgr = SessionManager()
SECRET = os.getenv("WEBHOOK_SECRET", "mb2026")
POWER_AUTOMATE_URL = os.getenv("POWER_AUTOMATE_URL", "")
BACKEND_URL = os.getenv("BACKEND_URL", "https://web-production-162d3.up.railway.app")

STYLE = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #f0f2f5; padding: 20px; }
.card { background: white; padding: 32px; border-radius: 16px; max-width: 420px; width: 100%; box-shadow: 0 4px 20px rgba(0,0,0,0.12); }
.icon { font-size: 48px; text-align: center; margin-bottom: 12px; }
h2 { text-align: center; color: #1a1a1a; font-size: 20px; margin-bottom: 6px; }
.rid { text-align: center; font-size: 13px; color: #888; font-family: monospace; background: #f5f5f5; padding: 4px 10px; border-radius: 6px; display: block; margin-bottom: 20px; }
label { display: block; font-size: 13px; color: #555; margin-bottom: 4px; margin-top: 14px; font-weight: bold; }
input, textarea { width: 100%; padding: 10px 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; outline: none; font-family: Arial, sans-serif; }
textarea { height: 90px; resize: vertical; }
.btn { display: block; width: 100%; padding: 14px; border-radius: 10px; font-size: 16px; font-weight: bold; color: white; border: none; cursor: pointer; margin-top: 20px; }
.cancel { display: block; text-align: center; margin-top: 12px; font-size: 13px; color: #999; cursor: pointer; text-decoration: underline; }
</style>
"""


def result_page(title, message, success=True):
    emoji = "✅" if success else "❌"
    return HTMLResponse(content="""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>""" + title + """</title>""" + STYLE + """</head>
<body><div class="card">
<div class="icon">""" + emoji + """</div>
<h2>""" + title + """</h2>
<p style="text-align:center;color:#666;margin-top:8px;font-size:14px;">""" + message + """</p>
<p style="text-align:center;margin-top:20px;font-size:12px;color:#aaa;">Puoi chiudere questa finestra.</p>
</div></body></html>""")


async def notify_tipster(request_id, esito, commento="", quota_nuova="", stake_nuovo="", budget_nuovo=""):
    session = session_mgr.get_request(request_id)
    if not session:
        logger.warning("Sessione non trovata: " + request_id)
        return False
    if session["stato"] != "in_attesa":
        logger.warning("Gia processata: " + request_id)
        return False

    tipster_id = session["tipster_id"]
    fields = session["fields"]
    evento = fields.get("evento", "")
    mercato = fields.get("mercato", "")
    header = "Richiesta #" + request_id + " — " + evento + " · " + mercato + "\n\n"

    if esito == "approvata":
        session_mgr.update_stato(request_id, esito)
        msg = header + "ESITO: APPROVATA ✅"
        if commento:
            msg += "\n\nNote: " + commento
        try:
            await bot.send_message(chat_id=tipster_id, text=msg)
            log_response(request_id, esito, {"note": commento})
            return True
        except Exception as e:
            logger.error("Telegram error: " + str(e))
            return False

    elif esito == "rifiutata":
        session_mgr.update_stato(request_id, esito)
        msg = header + "ESITO: RIFIUTATA ❌"
        if commento:
            msg += "\n\nNote: " + commento
        try:
            await bot.send_message(chat_id=tipster_id, text=msg)
            log_response(request_id, esito, {"note": commento})
            return True
        except Exception as e:
            logger.error("Telegram error: " + str(e))
            return False

    elif esito == "controproposta":
        # Non aggiorniamo ancora lo stato — aspettiamo risposta tipster
        session_mgr.update_stato(request_id, "controproposta_pending")

        # Costruisci riepilogo controproposta
        cp_lines = []
        if quota_nuova:
            cp_lines.append("Quota approvata: " + quota_nuova)
        if stake_nuovo:
            cp_lines.append("Max stake: " + stake_nuovo)
        if budget_nuovo:
            cp_lines.append("Budget: " + budget_nuovo)
        if commento:
            cp_lines.append("Nota del trader: " + commento)

        cp_text = "\n".join(cp_lines) if cp_lines else "Nessun dettaglio fornito."

        msg = (header + "CONTROPROPOSTA 🔄\n" + cp_text +
               "\n\nVuoi accettare o rifiutare la controproposta?")

        # Bottoni inline per il tipster
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Accetta", callback_data="cp_accept_" + request_id),
                InlineKeyboardButton("❌ Rifiuta", callback_data="cp_reject_" + request_id)
            ]
        ])

        # Salva i dettagli CP nella sessione per dopo
        session_mgr.save_cp_details(request_id, {
            "quota_nuova": quota_nuova,
            "stake_nuovo": stake_nuovo,
            "budget_nuovo": budget_nuovo,
            "commento": commento,
            "tipster_id": tipster_id
        })

        try:
            await bot.send_message(chat_id=tipster_id, text=msg, reply_markup=keyboard)
            return True
        except Exception as e:
            logger.error("Telegram error: " + str(e))
            return False

    return False


async def notify_trader_teams(request_id, esito_tipster):
    """Manda notifica al gruppo Teams quando il tipster risponde alla controproposta."""
    if not POWER_AUTOMATE_URL:
        return

    evento = ""
    mercato = ""
    session = session_mgr.get_request(request_id)
    if session:
        evento = session["fields"].get("evento", "")
        mercato = session["fields"].get("mercato", "")

    if esito_tipster == "accepted":
        msg = (
            "✅ Il tipster ha ACCETTATO la controproposta\n"
            "Richiesta #" + request_id + " — " + evento + " · " + mercato + "\n\n"
            "Conferma quando la quota è online:"
        )
        confirm_url = BACKEND_URL + "/quota-online?id=" + request_id + "&secret=" + SECRET
        # Manda messaggio su Teams con link di conferma
        payload = {
            "request_id": request_id,
            "tipster": "Sistema",
            "nome_tipster": "RISPOSTA TIPSTER",
            "evento": "✅ CP ACCETTATA #" + request_id,
            "mercato": mercato,
            "quota_partenza": msg,
            "maggiorazione": confirm_url,
            "max_stake": "",
            "budget": "",
            "go_live": "",
            "attivita": "",
            "ora_richiesta": ""
        }
    else:
        payload = {
            "request_id": request_id,
            "tipster": "Sistema",
            "nome_tipster": "RISPOSTA TIPSTER",
            "evento": "❌ CP RIFIUTATA #" + request_id,
            "mercato": mercato,
            "quota_partenza": "Il tipster ha rifiutato la controproposta.",
            "maggiorazione": "",
            "max_stake": "",
            "budget": "",
            "go_live": "",
            "attivita": "",
            "ora_richiesta": ""
        }

    try:
        async with aiohttp.ClientSession() as s:
            await s.post(POWER_AUTOMATE_URL, json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=15))
    except Exception as e:
        logger.error("Teams notify error: " + str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/approve")
async def approve(id: str):
    return HTMLResponse(content="""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Approvazione</title>""" + STYLE + """</head>
<body><div class="card">
<div class="icon">✅</div>
<h2>Conferma Approvazione</h2>
<span class="rid">#""" + id + """</span>
<form method="POST" action="/confirm">
<input type="hidden" name="id" value=\"""" + id + """\">
<input type="hidden" name="esito" value="approvata">
<input type="hidden" name="secret" value=\"""" + SECRET + """\">
<label>Note per il tipster (opzionale)</label>
<textarea name="commento" placeholder="Aggiungi un messaggio per il tipster..."></textarea>
<button type="submit" class="btn" style="background:#22c55e;">✅ Conferma Approvazione</button>
</form>
<span class="cancel" onclick="window.close()">Annulla</span>
</div></body></html>""")


@app.get("/reject")
async def reject(id: str):
    return HTMLResponse(content="""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rifiuto</title>""" + STYLE + """</head>
<body><div class="card">
<div class="icon">❌</div>
<h2>Conferma Rifiuto</h2>
<span class="rid">#""" + id + """</span>
<form method="POST" action="/confirm">
<input type="hidden" name="id" value=\"""" + id + """\">
<input type="hidden" name="esito" value="rifiutata">
<input type="hidden" name="secret" value=\"""" + SECRET + """\">
<label>Note per il tipster (opzionale)</label>
<textarea name="commento" placeholder="Motivo del rifiuto..."></textarea>
<button type="submit" class="btn" style="background:#ef4444;">❌ Conferma Rifiuto</button>
</form>
<span class="cancel" onclick="window.close()">Annulla</span>
</div></body></html>""")


@app.get("/counter")
async def counter(id: str):
    return HTMLResponse(content="""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Controproposta</title>""" + STYLE + """</head>
<body><div class="card">
<div class="icon">🔄</div>
<h2>Controproposta</h2>
<span class="rid">#""" + id + """</span>
<form method="POST" action="/confirm">
<input type="hidden" name="id" value=\"""" + id + """\">
<input type="hidden" name="esito" value="controproposta">
<input type="hidden" name="secret" value=\"""" + SECRET + """\">
<label>Quota approvata</label>
<input type="text" name="quota_nuova" placeholder="es. 2.10">
<label>Max stake rivisto (€)</label>
<input type="text" name="stake_nuovo" placeholder="es. 25">
<label>Budget rivisto (€)</label>
<input type="text" name="budget_nuovo" placeholder="es. 300">
<label>Note per il tipster</label>
<textarea name="commento" placeholder="Aggiungi un messaggio per il tipster..."></textarea>
<button type="submit" class="btn" style="background:#f59e0b;">🔄 Invia Controproposta</button>
</form>
<span class="cancel" onclick="window.close()">Annulla</span>
</div></body></html>""")


@app.get("/quota-online")
async def quota_online(id: str, secret: str):
    if secret != SECRET:
        return result_page("Accesso negato", "Token non valido.", success=False)

    session = session_mgr.get_request(id)
    if not session:
        return result_page("Errore", "Richiesta non trovata.", success=False)

    tipster_id = session["tipster_id"]
    fields = session["fields"]
    evento = fields.get("evento", "")
    mercato = fields.get("mercato", "")

    session_mgr.update_stato(id, "quota_online")

    try:
        await bot.send_message(
            chat_id=tipster_id,
            text="Richiesta #" + id + " — " + evento + " · " + mercato + "\n\n🟢 Quota online! Il trader ha confermato che la quota è attiva."
        )
    except Exception as e:
        logger.error("Telegram error: " + str(e))
        return result_page("Errore", "Impossibile notificare il tipster.", success=False)

    return result_page("Quota confermata", "Il tipster è stato notificato.")


@app.post("/confirm")
async def confirm(request: Request):
    form = await request.form()
    id = form.get("id", "")
    esito = form.get("esito", "")
    secret = form.get("secret", "")
    commento = form.get("commento", "")
    quota_nuova = form.get("quota_nuova", "")
    stake_nuovo = form.get("stake_nuovo", "")
    budget_nuovo = form.get("budget_nuovo", "")

    if secret != SECRET:
        return result_page("Accesso negato", "Token non valido.", success=False)

    ok = await notify_tipster(id, esito, commento, quota_nuova, stake_nuovo, budget_nuovo)
    if ok:
        labels = {"approvata": "Approvata", "rifiutata": "Rifiutata", "controproposta": "Controproposta inviata"}
        return result_page(labels.get(esito, esito), "Risposta inviata al tipster.")
    return result_page("Errore", "Richiesta non trovata o gia processata.", success=False)


@app.post("/tipster-response")
async def tipster_response(request: Request):
    """Riceve la risposta del tipster alla controproposta (da callback Telegram)."""
    try:
        data = json.loads(await request.body())
    except Exception:
        return {"ok": False}

    request_id = data.get("request_id", "")
    esito = data.get("esito", "")

    session = session_mgr.get_request(request_id)
    if not session or session["stato"] != "controproposta_pending":
        return {"ok": False}

    if esito == "accepted":
        session_mgr.update_stato(request_id, "cp_accepted")
        tipster_id = session["tipster_id"]
        fields = session["fields"]
        evento = fields.get("evento", "")
        mercato = fields.get("mercato", "")

        # Notifica tipster
        await bot.send_message(
            chat_id=tipster_id,
            text="Richiesta #" + request_id + " — " + evento + " · " + mercato + "\n\n✅ Controproposta accettata!\nVerrai notificato quando la quota è online."
        )
        # Notifica trader su Teams
        await notify_trader_teams(request_id, "accepted")

    elif esito == "rejected":
        session_mgr.update_stato(request_id, "cp_rejected")
        tipster_id = session["tipster_id"]
        fields = session["fields"]
        evento = fields.get("evento", "")
        mercato = fields.get("mercato", "")

        await bot.send_message(
            chat_id=tipster_id,
            text="Richiesta #" + request_id + " — " + evento + " · " + mercato + "\n\n❌ Controproposta rifiutata."
        )
        await notify_trader_teams(request_id, "rejected")

    return {"ok": True}


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
        data.get("quota_nuova", ""),
        data.get("stake_nuovo", ""),
        data.get("budget_nuovo", "")
    )
    return {"ok": ok}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

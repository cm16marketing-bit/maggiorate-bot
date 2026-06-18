"""
webhook_server.py — Backend HTTP per ricevere le risposte dei trader da Teams.
Quando un trader clicca Approva/Rifiuta/Controproposta sulla Adaptive Card,
Teams fa una chiamata POST a questo server, che poi notifica il tipster via Telegram.
"""

import os
import logging
import asyncio
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from telegram import Bot
from dotenv import load_dotenv

from session_manager import SessionManager
from sheets_logger import log_response
from reminder import cancel_reminder

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="Marathonbet Maggiorate — Webhook Server")

bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
session_mgr = SessionManager()


class TraderResponse(BaseModel):
    request_id: str
    esito: str  # "approvata" | "rifiutata" | "controproposta"
    quota_approvata: str = ""
    max_stake_rivisto: str = ""
    budget_rivisto: str = ""
    note: str = ""


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/trader-response")
async def trader_response(data: TraderResponse):
    """
    Riceve la risposta del trader da Teams e la inoltra al tipster via Telegram.
    """
    request_id = data.request_id
    esito = data.esito.lower().strip()

    session = session_mgr.get_request(request_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Richiesta #{request_id} non trovata")

    if session["stato"] != "in_attesa":
        logger.warning(f"Richiesta #{request_id} già processata — stato: {session['stato']}")
        return {"ok": True, "note": "già processata"}

    tipster_id = session["tipster_id"]
    fields = session["fields"]

    # Ferma reminder
    cancel_reminder(request_id)

    # Aggiorna stato in DB
    session_mgr.update_stato(request_id, esito)

    # Costruisce messaggio per il tipster
    evento = fields.get("evento", "")
    mercato = fields.get("mercato", "")
    header = f"_{evento} · {mercato}_\n\n" if evento or mercato else ""

    if esito == "approvata":
        msg = (
            f"✅ *Aggiornamento richiesta #{request_id}*\n\n"
            f"{header}"
            f"*Esito: Approvata* ✓\n"
            f"La maggiorazione è confermata."
        )
        extra = {}

    elif esito == "rifiutata":
        msg = (
            f"❌ *Aggiornamento richiesta #{request_id}*\n\n"
            f"{header}"
            f"*Esito: Rifiutata*\n"
            f"La maggiorazione richiesta non è approvabile."
        )
        extra = {}

    elif esito == "controproposta":
        lines = []
        if data.quota_approvata:
            lines.append(f"  Quota approvata:   {data.quota_approvata}  _(richiesta: {fields.get('maggiorazione', 'N/D')})_")
        if data.max_stake_rivisto:
            lines.append(f"  Max stake:         {data.max_stake_rivisto}")
        if data.budget_rivisto:
            lines.append(f"  Budget:            {data.budget_rivisto}")
        if data.note:
            lines.append(f"  Note:              {data.note}")

        body = "\n".join(lines) if lines else "Nessun dettaglio fornito."
        msg = (
            f"🔄 *Aggiornamento richiesta #{request_id}*\n\n"
            f"{header}"
            f"*Controproposta:*\n{body}\n\n"
            f"_Per accettare o chiedere chiarimenti contatta il tuo account manager._"
        )
        extra = {
            "quota_approvata": data.quota_approvata,
            "note": data.note
        }

    else:
        msg = f"📩 *Aggiornamento richiesta #{request_id}*\n\nEsito: {esito}"
        extra = {}

    # Invia messaggio al tipster via Telegram
    try:
        await bot.send_message(chat_id=tipster_id, text=msg, parse_mode="Markdown")
        logger.info(f"Risposta #{request_id} inviata al tipster {tipster_id}")
    except Exception as e:
        logger.error(f"Errore invio Telegram: {e}")
        raise HTTPException(status_code=500, detail=f"Errore invio Telegram: {e}")

    # Aggiorna log Sheet
    try:
        log_response(request_id, esito, extra)
    except Exception as e:
        logger.warning(f"Sheet log error: {e}")

    return {"ok": True, "request_id": request_id, "esito": esito}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

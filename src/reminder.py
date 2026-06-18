"""
reminder.py — Gestisce i reminder automatici ogni 5 minuti per richieste senza risposta.
"""

import asyncio
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

REMINDER_INTERVAL = int(os.getenv("REMINDER_INTERVAL_SECONDS", "300"))  # 5 min default

# Dizionario dei task attivi: request_id -> asyncio.Task
_active_reminders: dict[str, asyncio.Task] = {}


def schedule_reminder(request_id: str, tipster_id: int, context):
    """
    Avvia il loop di reminder per una richiesta.
    Ogni 5 minuti invia un reminder al tipster e a Teams.
    Si ferma quando cancel_reminder() viene chiamato.
    """
    task = asyncio.create_task(
        _reminder_loop(request_id, tipster_id, context)
    )
    _active_reminders[request_id] = task
    logger.info(f"Reminder avviato per richiesta #{request_id}")


def cancel_reminder(request_id: str):
    """Ferma il reminder per una richiesta (chiamato quando arriva la risposta)."""
    task = _active_reminders.pop(request_id, None)
    if task and not task.done():
        task.cancel()
        logger.info(f"Reminder cancellato per richiesta #{request_id}")


async def _reminder_loop(request_id: str, tipster_id: int, context):
    """
    Loop interno: aspetta 5 min, poi invia reminder.
    Ripete fino a cancellazione.
    """
    from session_manager import SessionManager
    from teams_webhook import send_reminder_to_teams

    session_mgr = SessionManager()
    count = 0

    try:
        while True:
            await asyncio.sleep(REMINDER_INTERVAL)
            count += 1

            # Recupera sessione aggiornata
            session = session_mgr.get_request(request_id)
            if not session or session["stato"] != "in_attesa":
                logger.info(f"Richiesta #{request_id} non più in attesa — reminder fermato")
                break

            fields = session["fields"]
            tipster_name = session.get("tipster_name", "")

            # Avvisa il tipster su Telegram
            try:
                await context.bot.send_message(
                    chat_id=tipster_id,
                    text=(
                        f"⏱ *Richiesta #{request_id} ancora in attesa*\n\n"
                        f"_{fields.get('evento', '')} · {fields.get('mercato', '')}_\n\n"
                        f"Ho inviato un reminder ai trader. Ti aggiorno appena disponibile."
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Errore invio reminder Telegram: {e}")

            # Reminder su Teams
            try:
                await send_reminder_to_teams(request_id, tipster_name, fields, count)
            except Exception as e:
                logger.warning(f"Errore invio reminder Teams: {e}")

            logger.info(f"Reminder #{count} inviato per richiesta #{request_id}")

    except asyncio.CancelledError:
        logger.info(f"Reminder loop #{request_id} terminato per cancellazione")

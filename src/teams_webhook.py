bash

cat /home/claude/maggiorate_bot/src/teams_webhook.py
Output

"""
teams_webhook.py — Invia richiesta ai trader via Power Automate → Teams.
"""

import os
import aiohttp
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

POWER_AUTOMATE_URL = os.getenv("POWER_AUTOMATE_URL")


async def send_to_teams(request_id: str, tipster: str, fields: dict) -> bool:
    if not POWER_AUTOMATE_URL:
        logger.error("POWER_AUTOMATE_URL non configurato")
        return False

    payload = {
        "request_id": request_id,
        "tipster": tipster,
        "evento": fields.get("evento", "N/D"),
        "mercato": fields.get("mercato", "N/D"),
        "quota_partenza": fields.get("quota_partenza", "N/D"),
        "maggiorazione": fields.get("maggiorazione", "N/D"),
        "max_stake": fields.get("max_stake", "N/D"),
        "budget": fields.get("budget", "N/D"),
        "go_live": fields.get("go_live", "N/D"),
        "ora_richiesta": datetime.now().strftime("%H:%M")
    }

    logger.info(f"Invio a Power Automate — URL: {POWER_AUTOMATE_URL[:80]}...")
    logger.info(f"Payload: {payload}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                POWER_AUTOMATE_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                body = await resp.text()
                logger.info(f"Power Automate response — status: {resp.status} body: {body[:300]}")
                if resp.status in (200, 202):
                    return True
                else:
                    logger.error(f"Power Automate error {resp.status}: {body}")
                    return False
    except Exception as e:
        logger.error(f"Power Automate exception: {e}")
        return False


async def send_reminder_to_teams(request_id: str, tipster: str, fields: dict, reminder_count: int):
    if not POWER_AUTOMATE_URL:
        return
    payload = {
        "request_id": f"⏱ REMINDER #{reminder_count} — {request_id}",
        "tipster": tipster,
        "evento": fields.get("evento", "N/D"),
        "mercato": fields.get("mercato", "N/D"),
        "quota_partenza": "IN ATTESA DI RISPOSTA",
        "maggiorazione": fields.get("maggiorazione", "N/D"),
        "max_stake": fields.get("max_stake", "N/D"),
        "budget": fields.get("budget", "N/D"),
        "go_live": fields.get("go_live", "N/D"),
        "ora_richiesta": datetime.now().strftime("%H:%M")
    }
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                POWER_AUTOMATE_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            )
    except Exception as e:
        logger.error(f"Reminder Teams error: {e}")

"""
teams_webhook.py — Invia richiesta ai trader via Power Automate → Teams.
"""

import os
import json
import aiohttp
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

POWER_AUTOMATE_URL = os.getenv("POWER_AUTOMATE_URL")


async def send_to_teams(request_id: str, tipster: str, fields: dict) -> bool:
    if not POWER_AUTOMATE_URL:
        logger.warning("POWER_AUTOMATE_URL non configurato")
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

    async with aiohttp.ClientSession() as session:
        async with session.post(
            POWER_AUTOMATE_URL,
            json=payload,
            headers={"Content-Type": "application/json"}
        ) as resp:
            body = await resp.text()
            if resp.status in (200, 202):
                logger.info(f"Richiesta #{request_id} inviata a Teams via Power Automate")
                return True
            else:
                logger.error(f"Power Automate error {resp.status}: {body}")
                return False


async def send_reminder_to_teams(request_id: str, tipster: str, fields: dict, reminder_count: int):
    if not POWER_AUTOMATE_URL:
        return

    payload = {
        "request_id": f"REMINDER #{reminder_count} — {request_id}",
        "tipster": tipster,
        "evento": fields.get("evento", "N/D"),
        "mercato": fields.get("mercato", "N/D"),
        "quota_partenza": "⏱ IN ATTESA DI RISPOSTA",
        "maggiorazione": fields.get("maggiorazione", "N/D"),
        "max_stake": fields.get("max_stake", "N/D"),
        "budget": fields.get("budget", "N/D"),
        "go_live": fields.get("go_live", "N/D"),
        "ora_richiesta": datetime.now().strftime("%H:%M")
    }

    async with aiohttp.ClientSession() as session:
        await session.post(
            POWER_AUTOMATE_URL,
            json=payload,
            headers={"Content-Type": "application/json"}
        )

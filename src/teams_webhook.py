import os
import aiohttp
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

POWER_AUTOMATE_URL = os.getenv("POWER_AUTOMATE_URL")


async def send_to_teams(request_id, tipster, fields):
    if not POWER_AUTOMATE_URL:
        logger.error("POWER_AUTOMATE_URL non configurato")
        return False

    payload = {
        "request_id": request_id,
        "tipster": tipster,
        "evento": fields.get("evento", "ND"),
        "mercato": fields.get("mercato", "ND"),
        "quota_partenza": fields.get("quota_partenza", "ND"),
        "maggiorazione": fields.get("maggiorazione", "ND"),
        "max_stake": fields.get("max_stake", "ND"),
        "budget": fields.get("budget", "ND"),
        "go_live": fields.get("go_live", "ND"),
        "ora_richiesta": datetime.now().strftime("%H:%M")
    }

    logger.info("Invio a Power Automate")
    logger.info(str(payload))

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                POWER_AUTOMATE_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                body = await resp.text()
                logger.info("Power Automate status: " + str(resp.status))
                logger.info("Power Automate body: " + body[:200])
                if resp.status in (200, 202):
                    return True
                else:
                    logger.error("Power Automate error: " + str(resp.status))
                    return False
    except Exception as e:
        logger.error("Power Automate exception: " + str(e))
        return False


async def send_reminder_to_teams(request_id, tipster, fields, reminder_count):
    if not POWER_AUTOMATE_URL:
        return
    payload = {
        "request_id": "REMINDER " + str(reminder_count) + " " + request_id,
        "tipster": tipster,
        "evento": fields.get("evento", "ND"),
        "mercato": fields.get("mercato", "ND"),
        "quota_partenza": "IN ATTESA",
        "maggiorazione": fields.get("maggiorazione", "ND"),
        "max_stake": fields.get("max_stake", "ND"),
        "budget": fields.get("budget", "ND"),
        "go_live": fields.get("go_live", "ND"),
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
        logger.error("Reminder error: " + str(e))

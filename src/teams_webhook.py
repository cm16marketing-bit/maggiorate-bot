import os
import aiohttp
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

POWER_AUTOMATE_URL = os.getenv("POWER_AUTOMATE_URL")
BACKEND_URL = os.getenv("BACKEND_URL", "https://web-production-162d3.up.railway.app")


def build_adaptive_card(request_id, tipster, fields):
    webhook_url = BACKEND_URL + "/trader-response"
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "NUOVA RICHIESTA #" + request_id,
                            "weight": "Bolder",
                            "size": "Medium"
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Evento", "value": fields.get("evento", "N/D")},
                                {"title": "Mercato", "value": fields.get("mercato", "N/D")},
                                {"title": "Quota partenza", "value": fields.get("quota_partenza", "N/D")},
                                {"title": "Maggiorazione", "value": fields.get("maggiorazione", "N/D")},
                                {"title": "Max stake", "value": fields.get("max_stake", "N/D")},
                                {"title": "Budget totale", "value": fields.get("budget", "N/D")},
                                {"title": "Go-live", "value": fields.get("go_live", "N/D")},
                                {"title": "Tipster", "value": tipster},
                                {"title": "Ora richiesta", "value": datetime.now().strftime("%H:%M")}
                            ]
                        },
                        {
                            "type": "Input.Text",
                            "id": "commento",
                            "label": "Commento (opzionale)",
                            "placeholder": "es. quota rivista, mercato volatile...",
                            "isMultiline": False
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.Http",
                            "title": "APPROVATA",
                            "method": "POST",
                            "url": webhook_url,
                            "headers": [{"name": "Content-Type", "value": "application/json"}],
                            "body": '{"request_id":"' + request_id + '","esito":"approvata","commento":"{{commento.value}}","sender":"{{sender}}"}',
                            "style": "positive"
                        },
                        {
                            "type": "Action.Http",
                            "title": "RIFIUTATA",
                            "method": "POST",
                            "url": webhook_url,
                            "headers": [{"name": "Content-Type", "value": "application/json"}],
                            "body": '{"request_id":"' + request_id + '","esito":"rifiutata","commento":"{{commento.value}}","sender":"{{sender}}"}',
                            "style": "destructive"
                        },
                        {
                            "type": "Action.ShowCard",
                            "title": "CONTROPROPOSTA",
                            "card": {
                                "type": "AdaptiveCard",
                                "body": [
                                    {"type": "Input.Text", "id": "quota_nuova", "label": "Quota approvata", "placeholder": "es. 2.10"},
                                    {"type": "Input.Text", "id": "stake_nuovo", "label": "Max stake rivisto", "placeholder": "es. 25"},
                                    {"type": "Input.Text", "id": "budget_nuovo", "label": "Budget rivisto", "placeholder": "es. 300"},
                                    {"type": "Input.Text", "id": "note", "label": "Note", "isMultiline": True, "placeholder": "dettagli controproposta"}
                                ],
                                "actions": [
                                    {
                                        "type": "Action.Http",
                                        "title": "Invia controproposta",
                                        "method": "POST",
                                        "url": webhook_url,
                                        "headers": [{"name": "Content-Type", "value": "application/json"}],
                                        "body": '{"request_id":"' + request_id + '","esito":"controproposta","quota_nuova":"{{quota_nuova.value}}","stake_nuovo":"{{stake_nuovo.value}}","budget_nuovo":"{{budget_nuovo.value}}","note":"{{note.value}}","sender":"{{sender}}"}'
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        ]
    }


async def send_to_teams(request_id, tipster, fields):
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
                if resp.status in (200, 202):
                    return True
                else:
                    logger.error("Power Automate error: " + body)
                    return False
    except Exception as e:
        logger.error("Exception: " + str(e))
        return False


async def send_reminder_to_teams(request_id, tipster, fields, reminder_count):
    if not POWER_AUTOMATE_URL:
        return
    payload = {
        "request_id": "REMINDER " + str(reminder_count) + " - " + request_id,
        "tipster": tipster,
        "evento": fields.get("evento", "N/D"),
        "mercato": fields.get("mercato", "N/D"),
        "quota_partenza": "IN ATTESA",
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
        logger.error("Reminder error: " + str(e))

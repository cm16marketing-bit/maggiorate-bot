import os
import aiohttp
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

POWER_AUTOMATE_URL = os.getenv("POWER_AUTOMATE_URL")
BACKEND_URL = os.getenv("BACKEND_URL", "https://web-production-162d3.up.railway.app")


def build_adaptive_card(request_id, tipster, fields, title_prefix="NUOVA RICHIESTA"):
    """
    Costruisce il payload completo (message + adaptive card) da postare direttamente al webhook Teams.
    Usa Action.OpenUrl che apre le pagine HTML gia esistenti su Railway (/approve, /reject, /counter).
    Include sia nome_tipster (nome reale) che tipster_tg (handle Telegram).
    """
    nome_tipster = fields.get("nome_tipster", "N/D")
    approve_url = BACKEND_URL + "/approve?id=" + request_id
    reject_url = BACKEND_URL + "/reject?id=" + request_id
    counter_url = BACKEND_URL + "/counter?id=" + request_id
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
                            "text": title_prefix + " #" + request_id,
                            "weight": "Bolder",
                            "size": "Medium"
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Nome tipster", "value": nome_tipster},
                                {"title": "Evento", "value": fields.get("evento", "N/D")},
                                {"title": "Mercato", "value": fields.get("mercato", "N/D")},
                                {"title": "Quota partenza", "value": fields.get("quota_partenza", "N/D")},
                                {"title": "Maggiorazione", "value": fields.get("maggiorazione", "N/D")},
                                {"title": "Max stake", "value": fields.get("max_stake", "N/D")},
                                {"title": "Budget totale", "value": fields.get("budget", "N/D")},
                                {"title": "Go-live", "value": fields.get("go_live", "N/D")},
                                {"title": "Attività", "value": fields.get("attivita", "N/D")},
                                {"title": "Tipster TG", "value": tipster},
                                {"title": "Ora richiesta", "value": datetime.now().strftime("%H:%M")}
                            ]
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "APPROVATA",
                            "url": approve_url,
                            "style": "positive"
                        },
                        {
                            "type": "Action.OpenUrl",
                            "title": "RIFIUTATA",
                            "url": reject_url,
                            "style": "destructive"
                        },
                        {
                            "type": "Action.OpenUrl",
                            "title": "CONTROPROPOSTA",
                            "url": counter_url
                        }
                    ]
                }
            }
        ]
    }


async def _post_card_to_teams(card_payload: dict) -> bool:
    """Helper interno: invia la card adattiva al webhook Teams e restituisce True se ok."""
    if not POWER_AUTOMATE_URL:
        logger.error("POWER_AUTOMATE_URL non configurato")
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                POWER_AUTOMATE_URL,
                json=card_payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                body = await resp.text()
                logger.info("Teams webhook status: " + str(resp.status))
                if resp.status in (200, 202):
                    return True
                else:
                    logger.error("Teams webhook error: " + body)
                    return False
    except Exception as e:
        logger.error("Exception: " + str(e))
        return False


async def send_to_teams(request_id, tipster, fields):
    card = build_adaptive_card(request_id, tipster, fields, title_prefix="NUOVA RICHIESTA")
    return await _post_card_to_teams(card)


async def send_reminder_to_teams(request_id, tipster, fields, reminder_count):
    reminder_fields = dict(fields)
    reminder_fields["quota_partenza"] = "IN ATTESA"
    reminder_id = "REMINDER " + str(reminder_count) + " - " + request_id
    card = build_adaptive_card(reminder_id, tipster, reminder_fields, title_prefix="REMINDER")
    await _post_card_to_teams(card)


async def send_cp_accepted_to_teams(sub_request_id, orig_request_id, tipster, fields):
    """
    Il tipster ha accettato la controproposta.
    Invia su Teams una nuova card con sub_request_id: il trader deve cliccare APPROVATA per confermare.
    """
    cp_fields = dict(fields)
    cp_fields["evento"] = f"[CP ACCETTATA #{orig_request_id}] {fields.get('evento', 'N/D')}"
    card = build_adaptive_card(sub_request_id, tipster, cp_fields, title_prefix="CP ACCETTATA")
    return await _post_card_to_teams(card)


async def send_cp_rejected_to_teams(orig_request_id, tipster, fields):
    """
    Il tipster ha rifiutato la controproposta.
    Invia notifica informativa su Teams. Nessuna azione richiesta ai trader.
    """
    info_payload = {
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
                            "text": f"CP RIFIUTATA #{orig_request_id}",
                            "weight": "Bolder",
                            "size": "Medium",
                            "color": "Attention"
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Nome tipster", "value": fields.get("nome_tipster", "N/D")},
                                {"title": "Evento", "value": fields.get("evento", "N/D")},
                                {"title": "Tipster TG", "value": tipster},
                                {"title": "Ora", "value": datetime.now().strftime("%H:%M")}
                            ]
                        },
                        {
                            "type": "TextBlock",
                            "text": "Nessuna azione richiesta: il tipster ha rifiutato la controproposta.",
                            "wrap": True,
                            "isSubtle": True
                        }
                    ]
                }
            }
        ]
    }
    await _post_card_to_teams(info_payload)


async def send_segnalazione_to_teams(request_id, tipster, nome_tipster, match, commento):
    """
    Invia card SEGNALAZIONE su Teams con pulsante Rispondi che apre pagina Railway.
    """
    rispondi_url = BACKEND_URL + "/rispondi-segnalazione?id=" + request_id
    card_payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": "SEGNALAZIONE #" + request_id, "weight": "Bolder", "size": "Medium", "color": "Warning"},
                    {"type": "FactSet", "facts": [
                        {"title": "Nome tipster", "value": nome_tipster or "N/D"},
                        {"title": "Tipster TG", "value": tipster},
                        {"title": "Match", "value": match or "N/D"},
                        {"title": "Ora", "value": datetime.now().strftime("%H:%M")}
                    ]},
                    {"type": "TextBlock", "text": "Commento:", "weight": "Bolder", "spacing": "Medium"},
                    {"type": "TextBlock", "text": commento or "N/D", "wrap": True}
                ],
                "actions": [
                    {"type": "Action.OpenUrl", "title": "Rispondi", "url": rispondi_url, "style": "positive"}
                ]
            }
        }]
    }
    return await _post_card_to_teams(card_payload)

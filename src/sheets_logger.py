"""
sheets_logger.py — Log automatico su Google Sheet.
Ogni richiesta e risposta viene scritta nel foglio configurato.
"""

import os
import logging
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CREDS_PATH = os.getenv("GOOGLE_CREDS_PATH", "config/google_creds.json")

# Header colonne (riga 1 del foglio)
HEADERS = [
    "ID", "Data", "Ora richiesta", "Tipster",
    "Evento", "Mercato", "Quota partenza", "Maggiorazione richiesta",
    "Max stake/cliente", "Budget totale", "Go-live",
    "Esito", "Quota approvata", "Note trader",
    "Ora risposta", "Tempo risposta (min)", "Canale"
]


def _get_sheet():
    creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)

    # Usa il primo foglio oppure crea "Log Maggiorate"
    try:
        sheet = spreadsheet.worksheet("Log Maggiorate")
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("Log Maggiorate", rows=1000, cols=20)
        sheet.append_row(HEADERS)

    return sheet


def log_request(request_id: str, tipster: str, fields: dict):
    """Logga la richiesta al momento dell'invio."""
    if not SHEET_ID:
        logger.warning("GOOGLE_SHEET_ID non configurato — skip log")
        return

    sheet = _get_sheet()
    now = datetime.now()

    row = [
        request_id,
        now.strftime("%d/%m/%Y"),
        now.strftime("%H:%M"),
        tipster,
        fields.get("evento", "N/D"),
        fields.get("mercato", "N/D"),
        fields.get("quota_partenza", "N/D"),
        fields.get("maggiorazione", "N/D"),
        fields.get("max_stake", "N/D"),
        fields.get("budget", "N/D"),
        fields.get("go_live", "N/D"),
        "in_attesa",  # Esito — verrà aggiornato
        "",  # Quota approvata
        "",  # Note trader
        "",  # Ora risposta
        "",  # Tempo risposta
        "Telegram"
    ]

    sheet.append_row(row)
    logger.info(f"Log richiesta #{request_id} scritto su Sheet")


def log_response(request_id: str, esito: str, extra: dict = None):
    """
    Aggiorna la riga del log con la risposta del trader.
    Cerca la riga per request_id e aggiorna i campi risposta.
    """
    if not SHEET_ID:
        return

    if extra is None:
        extra = {}

    sheet = _get_sheet()
    now = datetime.now()
    now_str = now.strftime("%H:%M")

    # Trova la riga con questo request_id
    try:
        cell = sheet.find(request_id)
        row_num = cell.row

        # Recupera ora richiesta per calcolare tempo risposta
        ora_richiesta_str = sheet.cell(row_num, 3).value  # colonna "Ora richiesta"
        try:
            ora_richiesta = datetime.strptime(ora_richiesta_str, "%H:%M")
            delta = now - now.replace(hour=ora_richiesta.hour, minute=ora_richiesta.minute, second=0)
            tempo_risposta = int(delta.total_seconds() / 60)
        except Exception:
            tempo_risposta = ""

        # Aggiorna colonne risposta
        sheet.update_cell(row_num, 12, esito)                              # Esito
        sheet.update_cell(row_num, 13, extra.get("quota_approvata", ""))  # Quota approvata
        sheet.update_cell(row_num, 14, extra.get("note", ""))             # Note trader
        sheet.update_cell(row_num, 15, now_str)                           # Ora risposta
        sheet.update_cell(row_num, 16, str(tempo_risposta))               # Tempo risposta (min)

        logger.info(f"Log risposta #{request_id} aggiornato su Sheet")

    except gspread.exceptions.CellNotFound:
        logger.warning(f"Richiesta #{request_id} non trovata nel Sheet — skip aggiornamento")
    except Exception as e:
        logger.error(f"Errore aggiornamento Sheet: {e}")

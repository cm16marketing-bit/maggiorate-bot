"""
Marathonbet Italia — Bot Richieste Maggiorate
"""
import logging
import os
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)
from dotenv import load_dotenv
from session_manager import SessionManager
from teams_webhook import send_to_teams, send_reminder_to_teams
from sheets_logger import log_request, log_response

load_dotenv()
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states — NOME_TIPSTER è il primo step
(NOME_TIPSTER, EVENTO, MERCATO, QUOTA_PARTENZA, MAGGIORAZIONE, MAX_STAKE, BUDGET, GO_LIVE) = range(8)

FIELD_LABELS = [
    "Evento",
    "Mercato",
    "Quota di partenza",
    "Maggiorazione richiesta",
    "Max stake per cliente (€)",
    "Budget totale (€)",
    "Orario go-live",
]
FIELD_KEYS = ["evento", "mercato", "quota_partenza", "maggiorazione", "max_stake", "budget", "go_live"]
FIELD_HINTS = [
    "es. Milan vs Inter",
    "es. Over 2.5 / 1X2 / Marcatore",
    "es. 1.85",
    "es. 2.20",
    "es. 50",
    "es. 500",
    "es. 20:45",
]

session_manager = SessionManager()

# Reminder tasks attivi
_reminders: dict = {}


def nd_if_empty(text: str) -> str:
    skip = {"skip", "nd", "n/d", "non so", "non lo so", "-", "–", "boh", "?", "niente", "/"}
    return "N/D" if text.strip().lower() in skip else text.strip()


def format_recap(fields: dict, request_id: str) -> str:
    nome = fields.get("nome_tipster", "")
    nome_line = f"👤  Tipster:           {nome}\n" if nome else ""
    return (
        f"✅ *Richiesta #{request_id} inviata ai trader*\n\n"
        f"{nome_line}"
        f"🏟  Evento:           {fields.get('evento', 'N/D')}\n"
        f"📊  Mercato:          {fields.get('mercato', 'N/D')}\n"
        f"📈  Quota partenza:   {fields.get('quota_partenza', 'N/D')}\n"
        f"🎯  Maggiorazione:    {fields.get('maggiorazione', 'N/D')}\n"
        f"💰  Max stake:        {fields.get('max_stake', 'N/D')}\n"
        f"💼  Budget totale:    {fields.get('budget', 'N/D')}\n"
        f"⏰  Go-live:          {fields.get('go_live', 'N/D')}\n\n"
        f"_Ti rispondo qui appena i trader confermano._"
    )


async def ask_field(update: Update, index: int):
    label = FIELD_LABELS[index]
    hint = FIELD_HINTS[index]
    await update.message.reply_text(
        f"*{index + 1}/7 — {label}*\n_{hint}_\n\n"
        f"_(scrivi_ `skip` _per N/D)_",
        parse_mode="Markdown"
    )


# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Ciao {user.first_name}!\n\n"
        f"Sono il sistema richieste maggiorate di *Marathonbet Italia*.\n\n"
        f"Digita /richiesta per inviare una nuova richiesta.\n"
        f"Digita /annulla per interrompere in qualsiasi momento.",
        parse_mode="Markdown"
    )


# /richiesta — primo step: chiede il nome del tipster
async def richiesta_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = update.effective_user
    context.user_data["tipster_id"] = user.id
    context.user_data["fields"] = {}
    await update.message.reply_text(
        "📝 *Come vuoi essere chiamato?*\n_es. Mario_",
        parse_mode="Markdown"
    )
    return NOME_TIPSTER


# Raccoglie il nome inserito manualmente dal tipster
async def get_nome_tipster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nome = update.message.text.strip()
    context.user_data["nome_tipster"] = nome
    context.user_data["tipster"] = nome                   # usato in send_to_teams / log
    context.user_data["fields"]["nome_tipster"] = nome    # letto dal webhook
    await ask_field(update, 0)
    return EVENTO


async def collect(update: Update, context: ContextTypes.DEFAULT_TYPE, index: int, next_state):
    value = nd_if_empty(update.message.text)
    context.user_data["fields"][FIELD_KEYS[index]] = value
    if next_state is None:
        await submit(update, context)
        return ConversationHandler.END
    await ask_field(update, index + 1)
    return next_state


async def get_evento(u, c): return await collect(u, c, 0, MERCATO)
async def get_mercato(u, c): return await collect(u, c, 1, QUOTA_PARTENZA)
async def get_quota_partenza(u, c): return await collect(u, c, 2, MAGGIORAZIONE)
async def get_maggiorazione(u, c): return await collect(u, c, 3, MAX_STAKE)
async def get_max_stake(u, c): return await collect(u, c, 4, BUDGET)
async def get_budget(u, c): return await collect(u, c, 5, GO_LIVE)
async def get_go_live(u, c): return await collect(u, c, 6, None)


async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fields = context.user_data["fields"]
    tipster = context.user_data["tipster"]
    tipster_id = context.user_data["tipster_id"]

    request_id = session_manager.new_request(tipster_id, fields, tipster)
    await update.message.reply_text(format_recap(fields, request_id), parse_mode="Markdown")

    # Invia a Teams via Power Automate
    ok = await send_to_teams(request_id, tipster, fields)
    if not ok:
        await update.message.reply_text(
            "⚠️ Errore nell'invio ai trader. Riprova o contatta il tuo account manager."
        )
        return

    # Log Sheet
    try:
        log_request(request_id, tipster, fields)
    except Exception as e:
        logger.warning(f"Sheet log error: {e}")

    # Avvia reminder ogni 5 min
    task = asyncio.create_task(
        reminder_loop(request_id, tipster_id, tipster, fields, context)
    )
    _reminders[request_id] = task


async def reminder_loop(request_id, tipster_id, tipster, fields, context):
    interval = int(os.getenv("REMINDER_INTERVAL_SECONDS", "300"))
    count = 0
    try:
        while True:
            await asyncio.sleep(interval)
            session = session_manager.get_request(request_id)
            if not session or session["stato"] != "in_attesa":
                break
            count += 1
            try:
                await context.bot.send_message(
                    chat_id=tipster_id,
                    text=(
                        f"⏱ *Richiesta #{request_id} ancora in attesa*\n"
                        f"_{fields.get('evento','')} · {fields.get('mercato','')}_\n\n"
                        f"Reminder #{count} inviato ai trader."
                    ),
                    parse_mode="Markdown"
                )
                await send_reminder_to_teams(request_id, tipster, fields, count)
            except Exception as e:
                logger.warning(f"Reminder error: {e}")
    except asyncio.CancelledError:
        pass


def cancel_reminder(request_id: str):
    task = _reminders.pop(request_id, None)
    if task and not task.done():
        task.cancel()


# /annulla
async def annulla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Richiesta annullata.\n\nDigita /richiesta per iniziarne una nuova."
    )
    return ConversationHandler.END


# Messaggi fuori protocollo
async def fuori_protocollo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Questo canale è riservato alle richieste di maggiorazione.\n\n"
        "Digita /richiesta per iniziare.\n"
        "Per altre richieste contatta il tuo account manager."
    )


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN mancante")

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("richiesta", richiesta_start)],
        states={
            NOME_TIPSTER:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nome_tipster)],
            EVENTO:         [MessageHandler(filters.TEXT & ~filters.COMMAND, get_evento)],
            MERCATO:        [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mercato)],
            QUOTA_PARTENZA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_quota_partenza)],
            MAGGIORAZIONE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_maggiorazione)],
            MAX_STAKE:      [MessageHandler(filters.TEXT & ~filters.COMMAND, get_max_stake)],
            BUDGET:         [MessageHandler(filters.TEXT & ~filters.COMMAND, get_budget)],
            GO_LIVE:        [MessageHandler(filters.TEXT & ~filters.COMMAND, get_go_live)],
        },
        fallbacks=[
            CommandHandler("annulla", annulla),
            MessageHandler(filters.COMMAND, annulla),
        ],
        conversation_timeout=600,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fuori_protocollo))

    logger.info("Bot avviato")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

import logging
import os
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler, CallbackQueryHandler
)
from dotenv import load_dotenv

from session_manager import SessionManager
from teams_webhook import send_to_teams, send_reminder_to_teams, send_segnalazione_to_teams
from sheets_logger import log_request, log_response

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── STATI MAGGIORATA ───
(NOME_TIPSTER, EVENTO, MERCATO, QUOTA_PARTENZA, MAGGIORAZIONE, MAX_STAKE, BUDGET, GO_LIVE, ATTIVITA) = range(9)

FIELD_LABELS = [
    "Nome Tipster",
    "Evento",
    "Mercato",
    "Quota di partenza",
    "Maggiorazione richiesta",
    "Max stake per cliente (EUR)",
    "Budget totale (EUR)",
    "Orario go-live",
    "Attivita promozionale",
]
FIELD_KEYS = ["nome_tipster", "evento", "mercato", "quota_partenza", "maggiorazione", "max_stake", "budget", "go_live", "attivita"]
FIELD_HINTS = [
    "es. Marco Rossi",
    "es. Milan vs Inter",
    "es. Over 2.5 / 1X2 / Marcatore",
    "es. 1.85",
    "es. 2.20",
    "es. 50",
    "es. 500",
    "es. 20:45",
    "es. collab, scalata, pubblicita",
]

# ─── STATI SEGNALAZIONE ───
(SEG_NOME, SEG_MATCH, SEG_COMMENTO) = range(100, 103)

session_manager = SessionManager()
_reminders = {}

WHITELIST = os.getenv("WHITELIST_USER_IDS", "")


def is_authorized(user_id: int) -> bool:
    if not WHITELIST.strip():
        return True
    allowed = [int(x.strip()) for x in WHITELIST.split(",") if x.strip()]
    return user_id in allowed


def nd_if_empty(text):
    skip = {"skip", "nd", "n/d", "non so", "non lo so", "-", "boh", "?", "niente", "/"}
    return "N/D" if text.strip().lower() in skip else text.strip()


def format_recap(fields, request_id):
    return (
        "*Richiesta #" + request_id + " inviata ai trader*\n\n"
        + "Nome tipster:    " + fields.get("nome_tipster", "N/D") + "\n"
        + "Evento:          " + fields.get("evento", "N/D") + "\n"
        + "Mercato:         " + fields.get("mercato", "N/D") + "\n"
        + "Quota partenza:  " + fields.get("quota_partenza", "N/D") + "\n"
        + "Maggiorazione:   " + fields.get("maggiorazione", "N/D") + "\n"
        + "Max stake:       " + fields.get("max_stake", "N/D") + "\n"
        + "Budget totale:   " + fields.get("budget", "N/D") + "\n"
        + "Go-live:         " + fields.get("go_live", "N/D") + "\n"
        + "Attivita:        " + fields.get("attivita", "N/D") + "\n\n"
        + "_Ti rispondo qui appena i trader confermano._"
    )


async def ask_field(update_or_query, index):
    label = FIELD_LABELS[index]
    hint = FIELD_HINTS[index]
    text = str(index + 1) + "/9 - " + label + "\n" + hint + "\n\n(scrivi skip per N/D)"
    if hasattr(update_or_query, "message") and update_or_query.message:
        await update_or_query.message.reply_text(text)
    else:
        # CallbackQuery
        await update_or_query.callback_query.message.reply_text(text)


# ─── /start con menu a 2 pulsanti ──────────────────────────────────────────
async def start(update, context):
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("Accesso non autorizzato.")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔼 Quota Maggiorata", callback_data="menu_maggiorata")],
        [InlineKeyboardButton("⚠️ Segnalazione",    callback_data="menu_segnalazione")],
    ])
    await update.message.reply_text(
        "Ciao " + user.first_name + "!\n\n"
        "Sono il sistema richieste di Marathonbet Italia.\n\n"
        "Scegli cosa vuoi fare:",
        reply_markup=keyboard
    )


# ─── FLUSSO MAGGIORATA ─────────────────────────────────────────────────────
async def richiesta_start(update, context):
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("Accesso non autorizzato.")
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["tipster"] = "@" + user.username if user.username else user.first_name
    context.user_data["tipster_id"] = user.id
    context.user_data["fields"] = {}
    await ask_field(update, 0)
    return NOME_TIPSTER


async def richiesta_from_menu(update, context):
    """Entry point per /start -> clic su Quota Maggiorata."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not is_authorized(user.id):
        await query.message.reply_text("Accesso non autorizzato.")
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["tipster"] = "@" + user.username if user.username else user.first_name
    context.user_data["tipster_id"] = user.id
    context.user_data["fields"] = {}
    # Chiedi primo campo
    label = FIELD_LABELS[0]
    hint = FIELD_HINTS[0]
    await query.message.reply_text("1/9 - " + label + "\n" + hint + "\n\n(scrivi skip per N/D)")
    return NOME_TIPSTER


async def collect(update, context, index, next_state):
    value = nd_if_empty(update.message.text)
    context.user_data["fields"][FIELD_KEYS[index]] = value
    if next_state is None:
        await submit(update, context)
        return ConversationHandler.END
    await ask_field(update, index + 1)
    return next_state


async def get_nome_tipster(u, c): return await collect(u, c, 0, EVENTO)
async def get_evento(u, c): return await collect(u, c, 1, MERCATO)
async def get_mercato(u, c): return await collect(u, c, 2, QUOTA_PARTENZA)
async def get_quota_partenza(u, c): return await collect(u, c, 3, MAGGIORAZIONE)
async def get_maggiorazione(u, c): return await collect(u, c, 4, MAX_STAKE)
async def get_max_stake(u, c): return await collect(u, c, 5, BUDGET)
async def get_budget(u, c): return await collect(u, c, 6, GO_LIVE)
async def get_go_live(u, c): return await collect(u, c, 7, ATTIVITA)
async def get_attivita(u, c): return await collect(u, c, 8, None)


async def submit(update, context):
    fields = context.user_data["fields"]
    tipster = context.user_data["tipster"]
    tipster_id = context.user_data["tipster_id"]

    request_id = session_manager.new_request(tipster_id, fields, tipster)
    await update.message.reply_text(format_recap(fields, request_id), parse_mode="Markdown")

    ok = await send_to_teams(request_id, tipster, fields)
    if not ok:
        await update.message.reply_text(
            "Errore nell'invio ai trader. Riprova o contatta il tuo account manager."
        )
        return

    try:
        log_request(request_id, tipster, fields)
    except Exception as e:
        logger.warning("Sheet log error: " + str(e))

    interval = int(os.getenv("REMINDER_INTERVAL_SECONDS", "600"))
    task = asyncio.create_task(
        reminder_loop(request_id, tipster_id, tipster, fields, context, interval)
    )
    _reminders[request_id] = task


async def reminder_loop(request_id, tipster_id, tipster, fields, context, interval):
    count = 0
    try:
        await asyncio.sleep(interval)
        while True:
            session = session_manager.get_request(request_id)
            if not session or session["stato"] != "in_attesa":
                break
            count += 1
            try:
                await context.bot.send_message(
                    chat_id=tipster_id,
                    text=(
                        "Richiesta #" + request_id + " ancora in attesa\n"
                        + fields.get("evento", "") + " - " + fields.get("mercato", "") + "\n\n"
                        + "Reminder #" + str(count) + " inviato ai trader."
                    )
                )
                await send_reminder_to_teams(request_id, tipster, fields, count)
            except Exception as e:
                logger.warning("Reminder error: " + str(e))
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass


# ─── FLUSSO SEGNALAZIONE ──────────────────────────────────────────────────
async def segnalazione_start_cmd(update, context):
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("Accesso non autorizzato.")
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["tipster"] = "@" + user.username if user.username else user.first_name
    context.user_data["tipster_id"] = user.id
    context.user_data["seg"] = {}
    await update.message.reply_text(
        "⚠️ Nuova segnalazione\n\n1/3 - Nome Tipster\nes. Marco Rossi"
    )
    return SEG_NOME


async def segnalazione_from_menu(update, context):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not is_authorized(user.id):
        await query.message.reply_text("Accesso non autorizzato.")
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["tipster"] = "@" + user.username if user.username else user.first_name
    context.user_data["tipster_id"] = user.id
    context.user_data["seg"] = {}
    await query.message.reply_text(
        "⚠️ Nuova segnalazione\n\n1/3 - Nome Tipster\nes. Marco Rossi"
    )
    return SEG_NOME


async def seg_get_nome(update, context):
    context.user_data["seg"]["nome_tipster"] = update.message.text.strip() or "N/D"
    await update.message.reply_text("2/3 - Match\nes. Milan vs Inter")
    return SEG_MATCH


async def seg_get_match(update, context):
    context.user_data["seg"]["match"] = update.message.text.strip() or "N/D"
    await update.message.reply_text("3/3 - Commento (descrivi il problema)\nes. Manca Lautaro Martinez marcatore")
    return SEG_COMMENTO


async def seg_get_commento(update, context):
    context.user_data["seg"]["commento"] = update.message.text.strip() or "N/D"
    seg = context.user_data["seg"]
    tipster = context.user_data["tipster"]
    tipster_id = context.user_data["tipster_id"]

    # Salva come richiesta di tipo segnalazione (riusa tabella requests)
    pseudo_fields = {
        "nome_tipster": seg["nome_tipster"],
        "evento": seg["match"],
        "mercato": seg["commento"],
        "quota_partenza": "",
        "maggiorazione": "",
        "max_stake": "",
        "budget": "",
        "go_live": "",
        "attivita": "segnalazione",
    }
    request_id = session_manager.new_request(tipster_id, pseudo_fields, tipster)
    session_manager.update_stato(request_id, "segnalazione_aperta")

    await update.message.reply_text(
        "⚠️ *Segnalazione #" + request_id + " inviata ai trader*\n\n"
        "Nome tipster: " + seg["nome_tipster"] + "\n"
        "Match: " + seg["match"] + "\n"
        "Commento: " + seg["commento"] + "\n\n"
        "_Ti rispondo qui quando il trader risponde._",
        parse_mode="Markdown"
    )

    ok = await send_segnalazione_to_teams(request_id, tipster, seg["nome_tipster"], seg["match"], seg["commento"])
    if not ok:
        await update.message.reply_text("Errore nell'invio ai trader. Contatta il tuo account manager.")
    return ConversationHandler.END


# ─── FALLBACK ───────────────────────────────────────────────────────────────
async def annulla(update, context):
    context.user_data.clear()
    msg = update.message if update.message else update.callback_query.message
    await msg.reply_text(
        "Operazione annullata.\n\nDigita /start per ricominciare."
    )
    return ConversationHandler.END


async def fuori_protocollo(update, context):
    user = update.effective_user
    if not is_authorized(user.id):
        return
    await update.message.reply_text(
        "Questo canale e riservato alle richieste.\n\n"
        "Digita /start per iniziare."
    )


# ─── CALLBACK HANDLER per bottoni inline controproposta ───────────────────
async def handle_cp_callback(update, context):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("cp_accept_"):
        request_id = data.replace("cp_accept_", "")
        esito = "accepted"
    elif data.startswith("cp_reject_"):
        request_id = data.replace("cp_reject_", "")
        esito = "rejected"
    else:
        return

    import aiohttp as _aiohttp
    import os as _os
    backend = _os.getenv("BACKEND_URL", "https://web-production-162d3.up.railway.app")
    try:
        async with _aiohttp.ClientSession() as s:
            await s.post(
                backend + "/tipster-response",
                json={"request_id": request_id, "esito": esito},
                headers={"Content-Type": "application/json"},
                timeout=_aiohttp.ClientTimeout(total=15)
            )
    except Exception as e:
        logger.error("Callback error: " + str(e))

    if esito == "accepted":
        await query.edit_message_text(
            query.message.text + "\n\n✅ Hai accettato la controproposta. Verrai notificato quando la quota è online."
        )
    else:
        await query.edit_message_text(
            query.message.text + "\n\n❌ Hai rifiutato la controproposta."
        )


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN mancante")

    app = Application.builder().token(token).build()

    # ConversationHandler Maggiorata (entry: /richiesta OR callback menu_maggiorata)
    conv_maggiorata = ConversationHandler(
        entry_points=[
            CommandHandler("richiesta", richiesta_start),
            CallbackQueryHandler(richiesta_from_menu, pattern="^menu_maggiorata$"),
        ],
        states={
            NOME_TIPSTER:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nome_tipster)],
            EVENTO:         [MessageHandler(filters.TEXT & ~filters.COMMAND, get_evento)],
            MERCATO:        [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mercato)],
            QUOTA_PARTENZA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_quota_partenza)],
            MAGGIORAZIONE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_maggiorazione)],
            MAX_STAKE:      [MessageHandler(filters.TEXT & ~filters.COMMAND, get_max_stake)],
            BUDGET:         [MessageHandler(filters.TEXT & ~filters.COMMAND, get_budget)],
            GO_LIVE:        [MessageHandler(filters.TEXT & ~filters.COMMAND, get_go_live)],
            ATTIVITA:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_attivita)],
        },
        fallbacks=[
            CommandHandler("annulla", annulla),
            CommandHandler("start", annulla),
        ],
        conversation_timeout=600,
    )

    # ConversationHandler Segnalazione (entry: /segnalazione OR callback menu_segnalazione)
    conv_segnalazione = ConversationHandler(
        entry_points=[
            CommandHandler("segnalazione", segnalazione_start_cmd),
            CallbackQueryHandler(segnalazione_from_menu, pattern="^menu_segnalazione$"),
        ],
        states={
            SEG_NOME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, seg_get_nome)],
            SEG_MATCH:    [MessageHandler(filters.TEXT & ~filters.COMMAND, seg_get_match)],
            SEG_COMMENTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, seg_get_commento)],
        },
        fallbacks=[
            CommandHandler("annulla", annulla),
            CommandHandler("start", annulla),
        ],
        conversation_timeout=600,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_maggiorata)
    app.add_handler(conv_segnalazione)
    app.add_handler(CallbackQueryHandler(handle_cp_callback, pattern="^cp_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fuori_protocollo))

    logger.info("Bot avviato")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

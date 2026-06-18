# SETUP GUIDE — Bot Richieste Maggiorate
## Marathonbet Italia — Telegram Bot

---

## PASSO 1 — Crea il bot su Telegram

1. Apri Telegram e cerca **@BotFather**
2. Scrivi `/newbot`
3. Scegli un nome visibile (es. `Marathonbet Maggiorate`)
4. Scegli uno username (es. `MarathonbetMaggiorateBot`) — deve finire in `Bot`
5. BotFather ti darà un **token** tipo `7123456789:AAF...`
6. Copia il token → inseriscilo in `.env` come `TELEGRAM_BOT_TOKEN`

---

## PASSO 2 — Trova i Telegram ID dei tipster (whitelist)

Per ogni tipster autorizzato:
1. Chiedi al tipster di aprire Telegram e scrivere a **@userinfobot**
2. Il bot risponderà con il suo ID numerico (es. `123456789`)
3. Raccoglili tutti e inseriscili in `.env`:
   ```
   WHITELIST_USER_IDS=123456789,987654321,456789123
   ```

---

## PASSO 3 — Configura il webhook Teams

1. Apri Microsoft Teams
2. Vai nel **canale dei trader** (quello già esistente)
3. Clicca sui `...` del canale → **Connettori**
4. Cerca **Incoming Webhook** → Configura
5. Dai un nome (es. `Maggiorate Bot`) e salva
6. Teams ti darà un URL tipo `https://outlook.office.com/webhook/...`
7. Copia l'URL → inseriscilo in `.env` come `TEAMS_WEBHOOK_URL`

---

## PASSO 4 — Configura Google Sheets

1. Vai su [console.cloud.google.com](https://console.cloud.google.com)
2. Crea un progetto nuovo (es. `marathonbet-bot`)
3. Abilita le API: **Google Sheets API** e **Google Drive API**
4. Crea un **Service Account**:
   - IAM → Service Accounts → Crea
   - Nome: `maggiorate-bot`
   - Scarica il file JSON delle credenziali
5. Salva il file JSON come `config/google_creds.json`
6. Crea un Google Sheet nuovo
7. **Condividi il Sheet** con l'email del service account (es. `maggiorate-bot@progetto.iam.gserviceaccount.com`) con permesso **Editor**
8. Copia l'ID del Sheet dall'URL → inseriscilo in `.env` come `GOOGLE_SHEET_ID`

---

## PASSO 5 — Deploy su Railway

1. Crea account su [railway.app](https://railway.app)
2. Crea un nuovo progetto → **Deploy from GitHub repo**
   - (oppure: installa Railway CLI con `npm install -g @railway/cli` e fai `railway up`)
3. Nel progetto Railway, vai in **Variables** e aggiungi tutte le variabili del file `.env.example`
4. Railway ti darà un URL pubblico tipo `https://maggiorate-bot.up.railway.app`
5. Inserisci questo URL in `.env` come `BACKEND_URL`

---

## PASSO 6 — Test locale (opzionale prima del deploy)

```bash
# Installa dipendenze
pip install -r requirements.txt

# Copia e compila il file .env
cp .env.example .env
# Edita .env con i tuoi valori

# Avvia
python main.py
```

---

## PASSO 7 — Test con i tipster

1. Condividi il link del bot con i tipster: `t.me/MarathonbetMaggiorateBot`
2. Chiedi a un tipster di scrivere `/start` e poi `/richiesta`
3. Verifica che la Adaptive Card arrivi su Teams
4. Clicca "Approva" e verifica che il tipster riceva la notifica
5. Controlla il Google Sheet che la riga sia stata scritta correttamente

---

## STRUTTURA FILE

```
maggiorate_bot/
├── main.py                  ← Entry point (bot + webhook server)
├── requirements.txt         ← Dipendenze Python
├── railway.toml             ← Config deploy Railway
├── Procfile                 ← Comando avvio
├── .env.example             ← Template variabili ambiente
├── config/
│   └── google_creds.json    ← Credenziali Google (NON committare!)
└── src/
    ├── bot.py               ← Bot Telegram (flow conversazionale)
    ├── session_manager.py   ← Gestione sessioni (SQLite)
    ├── teams_webhook.py     ← Invio Adaptive Card a Teams
    ├── webhook_server.py    ← Server per ricevere risposte trader
    ├── reminder.py          ← Reminder automatico ogni 5 min
    └── sheets_logger.py     ← Log su Google Sheet
```

---

## .gitignore consigliato

```
.env
config/google_creds.json
sessions.db
__pycache__/
*.pyc
.venv/
```

---

## COSTI STIMATI

| Componente | Costo |
|---|---|
| Bot Telegram | €0 |
| Railway free tier | €0 (fino a 500h/mese) |
| Railway starter (uptime H24) | €5/mese |
| Google Sheets API | €0 |
| Microsoft Teams webhook | €0 |
| **TOTALE** | **€0 – €5/mese** |

---

## SUPPORTO

Per qualsiasi problema durante il setup, contatta Chris Mitoli.

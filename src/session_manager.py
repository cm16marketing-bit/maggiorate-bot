import sqlite3
import uuid
import os
import json
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "sessions.db")


class SessionManager:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY,
                    tipster_id INTEGER,
                    tipster_name TEXT,
                    nome_tipster TEXT,
                    evento TEXT,
                    mercato TEXT,
                    quota_partenza TEXT,
                    maggiorazione TEXT,
                    max_stake TEXT,
                    budget TEXT,
                    go_live TEXT,
                    attivita TEXT,
                    stato TEXT DEFAULT 'in_attesa',
                    cp_details TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            # Aggiungi colonne mancanti se tabella esiste già
            try:
                conn.execute("ALTER TABLE requests ADD COLUMN nome_tipster TEXT")
            except:
                pass
            try:
                conn.execute("ALTER TABLE requests ADD COLUMN attivita TEXT")
            except:
                pass
            try:
                conn.execute("ALTER TABLE requests ADD COLUMN cp_details TEXT")
            except:
                pass
            conn.commit()

    def new_request(self, tipster_id: int, fields: dict, tipster_name: str = "") -> str:
        request_id = str(uuid.uuid4())[:8].upper()
        now = datetime.now().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO requests (
                    id, tipster_id, tipster_name, nome_tipster,
                    evento, mercato, quota_partenza, maggiorazione,
                    max_stake, budget, go_live, attivita,
                    stato, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'in_attesa', ?, ?)
            """, (
                request_id, tipster_id, tipster_name,
                fields.get("nome_tipster", "N/D"),
                fields.get("evento", "N/D"),
                fields.get("mercato", "N/D"),
                fields.get("quota_partenza", "N/D"),
                fields.get("maggiorazione", "N/D"),
                fields.get("max_stake", "N/D"),
                fields.get("budget", "N/D"),
                fields.get("go_live", "N/D"),
                fields.get("attivita", "N/D"),
                now, now
            ))
            conn.commit()
        return request_id

    def get_request(self, request_id: str) -> dict | None:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not row:
            return None
        return {
            "request_id": row["id"],
            "tipster_id": row["tipster_id"],
            "tipster_name": row["tipster_name"],
            "fields": {
                "nome_tipster": row["nome_tipster"] or "N/D",
                "evento": row["evento"],
                "mercato": row["mercato"],
                "quota_partenza": row["quota_partenza"],
                "maggiorazione": row["maggiorazione"],
                "max_stake": row["max_stake"],
                "budget": row["budget"],
                "go_live": row["go_live"],
                "attivita": row["attivita"] or "N/D",
            },
            "stato": row["stato"],
            "cp_details": json.loads(row["cp_details"]) if row["cp_details"] else {},
            "created_at": row["created_at"],
        }

    def update_stato(self, request_id: str, stato: str):
        now = datetime.now().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE requests SET stato = ?, updated_at = ? WHERE id = ?", (stato, now, request_id))
            conn.commit()

    def save_cp_details(self, request_id: str, details: dict):
        now = datetime.now().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE requests SET cp_details = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(details), now, request_id))
            conn.commit()

    def get_pending_requests(self) -> list:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM requests WHERE stato = 'in_attesa'").fetchall()
        return [self.get_request(row["id"]) for row in rows]

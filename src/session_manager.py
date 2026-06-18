"""
SessionManager — gestisce le sessioni richiesta in SQLite.
Ogni richiesta ha un ID univoco, i field, il tipster e lo stato.
"""

import sqlite3
import uuid
import os
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
                    evento TEXT,
                    mercato TEXT,
                    quota_partenza TEXT,
                    maggiorazione TEXT,
                    max_stake TEXT,
                    budget TEXT,
                    go_live TEXT,
                    stato TEXT DEFAULT 'in_attesa',
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()

    def new_request(self, tipster_id: int, fields: dict, tipster_name: str = "") -> str:
        request_id = str(uuid.uuid4())[:8].upper()  # es. "A3F7B2C1"
        now = datetime.now().isoformat()

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO requests (
                    id, tipster_id, tipster_name,
                    evento, mercato, quota_partenza,
                    maggiorazione, max_stake, budget, go_live,
                    stato, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'in_attesa', ?, ?)
            """, (
                request_id,
                tipster_id,
                tipster_name,
                fields.get("evento", "N/D"),
                fields.get("mercato", "N/D"),
                fields.get("quota_partenza", "N/D"),
                fields.get("maggiorazione", "N/D"),
                fields.get("max_stake", "N/D"),
                fields.get("budget", "N/D"),
                fields.get("go_live", "N/D"),
                now, now
            ))
            conn.commit()

        return request_id

    def get_request(self, request_id: str) -> dict | None:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM requests WHERE id = ?", (request_id,)
            ).fetchone()

        if not row:
            return None

        return {
            "request_id": row["id"],
            "tipster_id": row["tipster_id"],
            "tipster_name": row["tipster_name"],
            "fields": {
                "evento": row["evento"],
                "mercato": row["mercato"],
                "quota_partenza": row["quota_partenza"],
                "maggiorazione": row["maggiorazione"],
                "max_stake": row["max_stake"],
                "budget": row["budget"],
                "go_live": row["go_live"],
            },
            "stato": row["stato"],
            "created_at": row["created_at"],
        }

    def update_stato(self, request_id: str, stato: str):
        now = datetime.now().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE requests SET stato = ?, updated_at = ? WHERE id = ?",
                (stato, now, request_id)
            )
            conn.commit()

    def get_pending_requests(self) -> list[dict]:
        """Restituisce le richieste ancora in attesa di risposta."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM requests WHERE stato = 'in_attesa'"
            ).fetchall()

        return [self.get_request(row["id"]) for row in rows]

    def all_requests(self) -> list[dict]:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM requests ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

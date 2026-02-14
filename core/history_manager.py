"""HistoryManager — SQLite-хранилище истории диктовок."""

import sqlite3
from datetime import datetime
from pathlib import Path

MAX_RECORDS = 50

DB_PATH = Path(__file__).parent.parent / "history.db"


class HistoryManager:
    """Автоматическое сохранение диктовок в SQLite через EventBus."""

    def __init__(self, event_bus, model_manager):
        self._bus = event_bus
        self._model_manager = model_manager
        self._pending_metadata = None

        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row

        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS dictations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    text TEXT NOT NULL,
                    language TEXT,
                    model TEXT,
                    duration REAL
                )
            """)

        self._bus.text_recognized.connect(self._on_text_recognized)
        self._bus.text_processed.connect(self._on_text_processed)

    def _on_text_recognized(self, text, metadata):
        self._pending_metadata = {
            'language': metadata.get('language'),
            'elapsed': metadata.get('elapsed'),
            'model': self._model_manager.model_name,
        }

    def _on_text_processed(self, text):
        if self._pending_metadata is None:
            return
        meta = self._pending_metadata
        self._pending_metadata = None
        self.add(text, meta['language'], meta['model'], meta['elapsed'])

    def add(self, text, language=None, model=None, duration=None):
        ts = datetime.now().isoformat()
        with self._conn:
            self._conn.execute(
                "INSERT INTO dictations (timestamp, text, language, model, duration) VALUES (?, ?, ?, ?, ?)",
                (ts, text, language, model, duration),
            )
            self._conn.execute(
                "DELETE FROM dictations WHERE id NOT IN (SELECT id FROM dictations ORDER BY timestamp DESC LIMIT ?)",
                (MAX_RECORDS,),
            )

    def get_all(self):
        cur = self._conn.execute("SELECT * FROM dictations ORDER BY timestamp DESC")
        return [dict(row) for row in cur.fetchall()]

    def search(self, query):
        cur = self._conn.execute(
            "SELECT * FROM dictations WHERE text LIKE ? ORDER BY timestamp DESC",
            (f"%{query}%",),
        )
        return [dict(row) for row in cur.fetchall()]

    def delete(self, record_id):
        with self._conn:
            self._conn.execute("DELETE FROM dictations WHERE id = ?", (record_id,))

    def clear(self):
        with self._conn:
            self._conn.execute("DELETE FROM dictations")

    def close(self):
        self._conn.close()

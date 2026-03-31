"""SQLite-backed snapshot storage for the watch engine."""

from __future__ import annotations

import os
import sqlite3
import time

_DEFAULT_DB_DIR = os.path.join(os.path.expanduser("~"), ".sports-skills")
_DEFAULT_DB_PATH = os.path.join(_DEFAULT_DB_DIR, "watch.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS snapshots (
    watcher_id   TEXT PRIMARY KEY,
    json_text    TEXT NOT NULL,
    sha256_hash  TEXT NOT NULL,
    updated_at   REAL NOT NULL
)
"""


class SnapshotStore:
    """Thread-safe SQLite store for watcher snapshots.

    Each watcher_id maps to its most recent response JSON and hash.
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or _DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    def get_snapshot(self, watcher_id: str) -> tuple[str | None, str | None]:
        """Return (json_text, sha256_hash) or (None, None) if not found."""
        row = self._conn.execute(
            "SELECT json_text, sha256_hash FROM snapshots WHERE watcher_id = ?",
            (watcher_id,),
        ).fetchone()
        if row:
            return row[0], row[1]
        return None, None

    def save_snapshot(self, watcher_id: str, json_text: str, sha256_hash: str) -> None:
        """Upsert the snapshot for a watcher_id."""
        self._conn.execute(
            "INSERT INTO snapshots (watcher_id, json_text, sha256_hash, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(watcher_id) DO UPDATE SET "
            "json_text=excluded.json_text, sha256_hash=excluded.sha256_hash, updated_at=excluded.updated_at",
            (watcher_id, json_text, sha256_hash, time.time()),
        )
        self._conn.commit()

    def delete_snapshot(self, watcher_id: str) -> None:
        """Remove snapshot for a watcher."""
        self._conn.execute("DELETE FROM snapshots WHERE watcher_id = ?", (watcher_id,))
        self._conn.commit()

    def list_watchers(self) -> list[dict]:
        """Return all stored watcher_ids with their last update timestamp."""
        rows = self._conn.execute("SELECT watcher_id, updated_at FROM snapshots ORDER BY updated_at DESC").fetchall()
        return [{"watcher_id": r[0], "updated_at": r[1]} for r in rows]

    def prune(self, max_age_seconds: int = 86400 * 7) -> int:
        """Delete snapshots older than max_age. Returns count deleted."""
        cutoff = time.time() - max_age_seconds
        cursor = self._conn.execute("DELETE FROM snapshots WHERE updated_at < ?", (cutoff,))
        self._conn.commit()
        return cursor.rowcount

    def close(self) -> None:
        """Close the DB connection."""
        self._conn.close()

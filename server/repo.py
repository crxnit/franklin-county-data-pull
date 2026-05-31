"""Read-only access to the parcel cache for the API.

Opens SQLite read-only, loads + cleans all parcels once, and memoizes the
cleaned list keyed on the latest pull_meta id — so a refresh transparently
invalidates the cache and requests never re-query SQLite per call. Thread-safe
for FastAPI's sync-endpoint threadpool.
"""

from __future__ import annotations

import os
import sqlite3
import threading

from franklin_housing.cache import COLUMNS
from franklin_housing.clean import clean_records
from franklin_housing.config import Config


class ReadRepo:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._pull_id = None
        self._records = None
        self._neighborhoods = None

    # -- connection ---------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{os.path.abspath(self.db_path)}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    def _current_pull_id(self, conn) -> int | None:
        try:
            row = conn.execute("SELECT MAX(id) AS m FROM pull_meta").fetchone()
            return row["m"] if row else None
        except sqlite3.Error:
            return None

    # -- cleaned records (memoized on pull_meta id) -------------------------

    def records(self) -> list[dict]:
        conn = self._connect()
        try:
            pid = self._current_pull_id(conn)
            if self._records is not None and pid == self._pull_id:
                return self._records
            with self._lock:
                if self._records is not None and pid == self._pull_id:
                    return self._records
                cols = ",".join(f'"{c}"' for c in COLUMNS)
                rows = [dict(r) for r in conn.execute(f"SELECT {cols} FROM parcels")]
                cleaned = clean_records(rows, Config())
                self._records = cleaned
                self._pull_id = pid
                self._neighborhoods = None
                return cleaned
        finally:
            conn.close()

    def etag(self) -> str:
        self.records()
        return f'"pull-{self._pull_id}"'

    def meta(self) -> dict:
        conn = self._connect()
        try:
            last = conn.execute(
                "SELECT pulled_at, where_clause, row_count FROM pull_meta "
                "ORDER BY id DESC LIMIT 1").fetchone()
            last = dict(last) if last else None
        finally:
            conn.close()
        recs = self.records()
        nbhds = {r["nbhdcd"] for r in recs if r.get("nbhdcd")}
        enriched = sum(1 for r in recs if r.get("valid_raw") not in (None, ""))
        return {"last_pull": last, "parcels": len(recs),
                "neighborhoods": len(nbhds), "enriched_valid": enriched}

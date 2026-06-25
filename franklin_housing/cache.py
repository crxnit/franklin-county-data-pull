"""Local SQLite cache of raw pulls.

One row per parcel (this layer carries only the latest sale per parcel, so
PARCELID is a natural primary key). Re-runs read from here unless --refresh is
passed. A `pull_meta` table records when/what was pulled.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone

from . import config

log = logging.getLogger(__name__)

COLUMNS = list(config.OUT_FIELDS)


class Cache:
    def __init__(self, db_path: str = "data/franklin_housing.sqlite"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        # WAL lets read-only API connections read concurrently with the single
        # writer (refresh job); busy_timeout avoids spurious "database locked".
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def _init_schema(self) -> None:
        cols = ",\n  ".join(f'"{c}"' for c in COLUMNS)
        self.conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS parcels (
              {cols},
              pulled_at TEXT,
              PRIMARY KEY ("PARCELID")
            );
            CREATE TABLE IF NOT EXISTS pull_meta (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              pulled_at TEXT NOT NULL,
              where_clause TEXT NOT NULL,
              row_count INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trend_cache (
              pull_id INTEGER PRIMARY KEY,
              computed_at TEXT NOT NULL,
              report_json TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def is_empty(self) -> bool:
        cur = self.conn.execute("SELECT COUNT(*) AS n FROM parcels")
        return cur.fetchone()["n"] == 0

    def last_pull(self) -> dict | None:
        cur = self.conn.execute(
            "SELECT pulled_at, where_clause, row_count FROM pull_meta "
            "ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def save(self, rows: list[dict], where_clause: str) -> int:
        """Upsert rows and record pull metadata. Returns row count stored."""
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        placeholders = ",".join("?" for _ in COLUMNS) + ",?"
        collist = ",".join(f'"{c}"' for c in COLUMNS) + ',pulled_at'
        sql = f"INSERT OR REPLACE INTO parcels ({collist}) VALUES ({placeholders})"
        data = [tuple(r.get(c) for c in COLUMNS) + (ts,) for r in rows]
        self.conn.executemany(sql, data)
        self.conn.execute(
            "INSERT INTO pull_meta (pulled_at, where_clause, row_count) VALUES (?,?,?)",
            (ts, where_clause, len(rows)),
        )
        self.conn.commit()
        log.info("cached %d rows at %s", len(rows), ts)
        return len(rows)

    def latest_pull_id(self) -> int | None:
        row = self.conn.execute("SELECT MAX(id) AS m FROM pull_meta").fetchone()
        return row["m"] if row else None

    def save_trends(self, pull_id: int, report_json: str) -> None:
        """Materialize a precomputed trend report keyed on the pull it reflects."""
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT OR REPLACE INTO trend_cache (pull_id, computed_at, report_json) "
            "VALUES (?,?,?)",
            (pull_id, ts, report_json),
        )
        self.conn.commit()

    def load_trends(self) -> dict | None:
        """Latest materialized trend report: {pull_id, computed_at, report_json}."""
        row = self.conn.execute(
            "SELECT pull_id, computed_at, report_json FROM trend_cache "
            "ORDER BY pull_id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def clear(self) -> None:
        self.conn.executescript(
            "DELETE FROM parcels; DELETE FROM pull_meta; DELETE FROM trend_cache;"
        )
        self.conn.commit()

    def load(self) -> list[dict]:
        cur = self.conn.execute(f"SELECT {','.join(chr(34)+c+chr(34) for c in COLUMNS)} FROM parcels")
        return [dict(row) for row in cur.fetchall()]

    def update_valid(self, parcelid: str, valid: str) -> None:
        """Used by the optional enrichment step to write a true VALID flag."""
        self.conn.execute('UPDATE parcels SET "VALID"=? WHERE "PARCELID"=?', (valid, parcelid))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

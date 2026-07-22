"""Read-only access to the parcel cache for the API.

Opens SQLite read-only, loads + cleans all parcels once, and memoizes the
cleaned list keyed on the latest pull_meta id — so a refresh transparently
invalidates the cache and requests never re-query SQLite per call. Thread-safe
for FastAPI's sync-endpoint threadpool.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading

from franklin_housing import trends as trends_engine
from franklin_housing.bulk_sales import annotate_valid
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
        self._trends = None
        self._trends_pull_id = None

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
                # County-coded VALID from the bulk sales table (if ingested)
                # supersedes the ratio proxy via clean.py's existing precedence.
                # Read-time because the daily refresh rewrites VALID to null.
                annotate_valid(rows, conn)
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

    # -- trend report (materialized by the refresh job; computed as fallback) --

    def trends(self) -> dict:
        """The sales-trend report current as of the latest pull. Prefers the
        materialized `trend_cache` row; if absent or stale (e.g. a fresh DB
        before the first materialization), recomputes from cleaned records."""
        conn = self._connect()
        try:
            pid = self._current_pull_id(conn)
            if self._trends is not None and pid == self._trends_pull_id:
                return self._trends
            report = self._load_materialized(conn, pid)
        finally:
            conn.close()
        # records() manages its own lock, so compute the fallback BEFORE taking
        # ours (a non-reentrant Lock — nesting the two would deadlock).
        if report is None:
            report = trends_engine.build_report(self.records())
        with self._lock:
            self._trends = report
            self._trends_pull_id = pid
            return report

    @staticmethod
    def _load_materialized(conn, pid) -> dict | None:
        try:
            row = conn.execute(
                "SELECT pull_id, report_json FROM trend_cache "
                "ORDER BY pull_id DESC LIMIT 1").fetchone()
        except sqlite3.Error:
            return None
        if not row or (pid is not None and row["pull_id"] != pid):
            return None
        try:
            return json.loads(row["report_json"])
        except (ValueError, TypeError):
            return None

    # -- bulk sale history (1:many, rebuilt monthly by bulk_sales.ingest) ----

    def sales_for(self, parcelid: str) -> list[dict]:
        """Every recorded conveyance for one parcel, oldest first. Empty when
        the bulk sales table hasn't been ingested yet."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT sale_date, price, adj_price, valid_code, instrument,"
                " n_parcels, condsale, flags FROM sales WHERE parcelid = ?"
                " ORDER BY sale_date IS NULL, sale_date", (parcelid,))
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def sales_meta(self) -> dict | None:
        """Latest bulk ingest info, or None if never ingested."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT ingested_at, extract_date, row_count FROM sales_meta"
                " ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else None
        except sqlite3.Error:
            return None
        finally:
            conn.close()

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
                "neighborhoods": len(nbhds), "enriched_valid": enriched,
                "bulk_sales": self.sales_meta()}

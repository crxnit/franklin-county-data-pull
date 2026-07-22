"""Append-only sales-history ledger.

The county GIS layer carries only the LATEST sale per parcel — a resale
overwrites the prior sale forever. This module accumulates every sale we ever
observe into a separate append-only SQLite DB, so that over time we build the
per-parcel sale history the county feed can't provide. Both refresh paths
(server/jobs/refresh.py and the CLI --refresh) call record_sales() after a
successful pull; scripts/sales_history.py backfills and reports.

Unlike the parcel caches (derived, rebuildable from the county API), this DB is
NOT derivable — losing it loses observations. It is never cleared by any code
path; writes are INSERT OR IGNORE keyed on (parcelid, sale_date, sale_price).

Stdlib only — lives in the zero-dep core so the CLI can use it without pulling
in the backend's third-party deps.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .clean import _epoch_ms_to_date

HISTORY_NAME = "sales_history.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sales (
  parcelid     TEXT NOT NULL,
  sale_date    TEXT NOT NULL,             -- ISO date
  sale_price   REAL NOT NULL,             -- 0.0 = unpriced/non-market transfer
  site_address TEXT,                      -- context at first observation
  nbhdcd       TEXT,
  schldscrp    TEXT,
  classcd      TEXT,
  sqft_ag      REAL,
  totvaluebase REAL,
  first_seen   TEXT NOT NULL,             -- when this observation was recorded
  source       TEXT NOT NULL,             -- e.g. 'webapp', 'cli', 'backfill:...'
  PRIMARY KEY (parcelid, sale_date, sale_price)
);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales (sale_date);
"""


def history_path(db_path: str | Path) -> Path:
    """The history DB lives next to whichever parcel cache fed it (both local
    caches share data/, so they share one ledger; on the VPS this lands on the
    persistent /data volume)."""
    return Path(db_path).with_name(HISTORY_NAME)


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_SCHEMA)
    return conn


def record_sales(db_path: str | Path, rows: list[dict], source: str,
                 history_db: str | Path | None = None) -> int:
    """Append newly-observed sales from raw parcel rows. Returns # inserted.

    The ledger path derives from db_path (see history_path) unless history_db
    overrides it — the backfill script uses that to fold snapshot baselines
    (which live in data/snapshots/) into the main data/ ledger.

    Rows without a SALEDATE (never-sold parcels) are skipped — there is no sale
    to record. A null SALEPRICE is stored as 0.0 (the county's own convention
    for non-market transfers) so the primary key stays NULL-free; sqlite treats
    each NULL in a unique index as distinct, which would duplicate the row on
    every refresh.
    """
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data = []
    for r in rows:
        d = _epoch_ms_to_date(r.get("SALEDATE"))
        if d is None:
            continue
        data.append((
            r.get("PARCELID"), d.isoformat(), float(r.get("SALEPRICE") or 0.0),
            r.get("SITEADDRESS"), r.get("NBHDCD"), r.get("SCHLDSCRP"),
            r.get("CLASSCD"), r.get("RESFLRAREA_AG"), r.get("TOTVALUEBASE"),
            ts, source,
        ))
    conn = _connect(Path(history_db) if history_db else history_path(db_path))
    try:
        before = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        conn.executemany(
            "INSERT OR IGNORE INTO sales (parcelid, sale_date, sale_price,"
            " site_address, nbhdcd, schldscrp, classcd, sqft_ag, totvaluebase,"
            " first_seen, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            data,
        )
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        return after - before
    finally:
        conn.close()

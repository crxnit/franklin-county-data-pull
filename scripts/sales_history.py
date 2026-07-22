"""Backfill and inspect the append-only sales-history ledger.

The ledger (data/sales_history.sqlite, see franklin_housing.history) grows
automatically on every refresh, but this script seeds it from data that already
exists locally — the two parcel caches and their baseline snapshots — and
reports what's accumulated.

Usage:
    python -m scripts.sales_history backfill   # fold existing DBs into the ledger
    python -m scripts.sales_history report     # what the ledger holds
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from franklin_housing.history import history_path, record_sales
from franklin_housing.snapshot import SNAP_DIR

# Every local DB whose parcels table may hold sales the ledger hasn't seen.
CACHE_DBS = [Path("data/webapp.sqlite"), Path("data/franklin_housing.sqlite")]
LEDGER = history_path(CACHE_DBS[0])   # data/sales_history.sqlite


def _parcel_rows(db: Path) -> list[dict]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM parcels")]
    finally:
        conn.close()


def backfill() -> int:
    sources = [db for db in CACHE_DBS if db.exists()]
    sources += sorted(SNAP_DIR.glob("*.baseline.sqlite"))
    if not sources:
        print("no local parcel DBs found — nothing to backfill")
        return 1
    total = 0
    for db in sources:
        rows = _parcel_rows(db)
        n = record_sales(db, rows, source=f"backfill:{db.stem}", history_db=LEDGER)
        total += n
        print(f"  {db}: {len(rows):,} parcels scanned, +{n:,} new sale(s)")
    print(f"backfill complete: +{total:,} sale(s) -> {LEDGER}")
    return 0


def report() -> int:
    if not LEDGER.exists():
        print(f"no ledger at {LEDGER} — run a refresh or `backfill` first")
        return 1
    conn = sqlite3.connect(f"file:{LEDGER}?mode=ro", uri=True)
    try:
        q = conn.execute
        n, parcels = q("SELECT COUNT(*), COUNT(DISTINCT parcelid) FROM sales").fetchone()
        lo, hi = q("SELECT MIN(sale_date), MAX(sale_date) FROM sales").fetchone()
        multi = q("SELECT COUNT(*) FROM (SELECT parcelid FROM sales"
                  " GROUP BY parcelid HAVING COUNT(*) > 1)").fetchone()[0]
        priced = q("SELECT COUNT(*) FROM sales WHERE sale_price >= 1").fetchone()[0]
        print(f"ledger: {LEDGER}")
        print(f"  sales      : {n:,}  ({priced:,} priced, {n - priced:,} $0 transfers)")
        print(f"  parcels    : {parcels:,}  ({multi:,} with >1 observed sale)")
        print(f"  date range : {lo} .. {hi}")
        print("  by source  :")
        for src, c in q("SELECT source, COUNT(*) FROM sales"
                        " GROUP BY source ORDER BY 2 DESC"):
            print(f"    {src:28s} {c:,}")
        print("  by first_seen date (recent):")
        for day, c in q("SELECT substr(first_seen,1,10) d, COUNT(*) FROM sales"
                        " GROUP BY d ORDER BY d DESC LIMIT 5"):
            print(f"    {day:28s} {c:,}")
    finally:
        conn.close()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="sales_history", description=__doc__)
    p.add_argument("cmd", choices=("backfill", "report"))
    args = p.parse_args(argv)
    return backfill() if args.cmd == "backfill" else report()


if __name__ == "__main__":
    sys.exit(main())

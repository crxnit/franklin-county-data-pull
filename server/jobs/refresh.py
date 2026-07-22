"""Scheduled data refresh — the ONLY place the county API is hit.

Pulls every Dublin SFR parcel (sales_only=False, so any address is lookup-able)
into the webapp SQLite cache via the existing ArcGISClient + Cache. Uses upsert
(no clear()) so a failed pull leaves the last-good data serving. Bumps pull_meta,
which auto-invalidates the API's in-memory cleaned-records cache.

Run:  python -m server.jobs.refresh   (also the first-boot seeding command)
"""

from __future__ import annotations

import json
import logging
import sys

from franklin_housing import trends
from franklin_housing.bulk_sales import annotate_valid
from franklin_housing.cache import Cache
from franklin_housing.clean import clean_records
from franklin_housing.client import ArcGISClient
from franklin_housing.config import Config
from franklin_housing.history import record_sales
from franklin_housing.snapshot import snapshot_db

from ..settings import get_settings

log = logging.getLogger(__name__)


def refresh(db_path: str | None = None) -> int:
    s = get_settings()
    cfg = Config(db_path=db_path or s.db_path)
    where = cfg.where_clause(sales_only=False)   # ALL parcels in target area

    client = ArcGISClient()
    expected = client.count(where)
    log.info("refresh: %d parcels match where: %s", expected, where)

    rows = list(client.query_all(where))
    if not rows:
        log.error("refresh pulled 0 rows — keeping existing data, aborting")
        return 0

    # Capture the pre-refresh state so a post-refresh diff is possible. Only
    # reached on a successful, non-empty pull (we're about to overwrite). Never
    # let a snapshot problem block the data update.
    try:
        snap = snapshot_db(cfg.db_path)
        if snap:
            log.info("refresh: baseline snapshot -> %s", snap)
    except Exception:
        log.warning("refresh: baseline snapshot failed (continuing)", exc_info=True)

    cache = Cache(cfg.db_path)
    try:
        cache.save(rows, where)        # INSERT OR REPLACE; no clear()
        log.info("refresh: upserted %d rows into %s", len(rows), cfg.db_path)
        # Append any newly-observed sales to the permanent history ledger
        # (the GIS layer overwrites a parcel's sale on resale; this is the
        # only record we keep of the prior one). Never blocks the refresh.
        try:
            n_new = record_sales(cfg.db_path, rows, source="webapp")
            log.info("refresh: %d new sale(s) appended to history", n_new)
        except Exception:
            log.warning("refresh: sales-history append failed (continuing)",
                        exc_info=True)
        # Materialize the sales-trend report for this pull. A trend-compute
        # failure must never block the data refresh — log and move on (same
        # discipline as the baseline snapshot above).
        try:
            pull_id = cache.latest_pull_id()
            # Annotate county-coded VALID (bulk sales table) before cleaning so
            # materialized trends agree with ReadRepo's live-cleaned records.
            loaded = cache.load()
            annotate_valid(loaded, cache.conn)
            report = trends.build_report(clean_records(loaded, cfg))
            cache.save_trends(pull_id, json.dumps(report))
            log.info("refresh: materialized trends for pull %s", pull_id)
        except Exception:
            log.warning("refresh: trend materialization failed (continuing)",
                        exc_info=True)
    finally:
        cache.close()
    return len(rows)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    n = refresh()
    print(f"refresh complete: {n} parcels")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())

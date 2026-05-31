"""Scheduled data refresh — the ONLY place the county API is hit.

Pulls every Dublin SFR parcel (sales_only=False, so any address is lookup-able)
into the webapp SQLite cache via the existing ArcGISClient + Cache. Uses upsert
(no clear()) so a failed pull leaves the last-good data serving. Bumps pull_meta,
which auto-invalidates the API's in-memory cleaned-records cache.

Run:  python -m server.jobs.refresh   (also the first-boot seeding command)
"""

from __future__ import annotations

import logging
import sys

from franklin_housing.cache import Cache
from franklin_housing.client import ArcGISClient
from franklin_housing.config import Config

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

    cache = Cache(cfg.db_path)
    try:
        cache.save(rows, where)        # INSERT OR REPLACE; no clear()
        log.info("refresh: upserted %d rows into %s", len(rows), cfg.db_path)
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

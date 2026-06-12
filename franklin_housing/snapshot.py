"""Baseline snapshot of a parcel DB, taken before a refresh overwrites it.

A refresh replaces rows in place (the webapp job upserts; the CLI clears+saves),
so without a copy of the prior state there is nothing to diff against. The
writers — server/jobs/refresh.py and the CLI --refresh path — call snapshot_db()
before re-pulling; the scripts/db_diff.py reporting tool reads the baseline back.
All must agree on the path, so the naming lives in one place: snapshot_path().

Stdlib only — lives in the zero-dep core so the CLI can use it without pulling
in the backend's third-party deps.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SNAP_DIR = Path("data/snapshots")


def snapshot_path(db_path: str | Path) -> Path:
    """Where the baseline copy of db_path lives, e.g. webapp.baseline.sqlite."""
    return SNAP_DIR / (Path(db_path).stem + ".baseline.sqlite")


def snapshot_db(db_path: str | Path) -> Path | None:
    """Back up db_path to its baseline copy (WAL-safe via the sqlite backup API).

    Returns the destination path, or None if the source doesn't exist yet
    (e.g. the first-boot seed has nothing to snapshot).
    """
    src = Path(db_path)
    if not src.exists():
        return None
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    dst = snapshot_path(src)
    con = sqlite3.connect(str(src))
    bck = sqlite3.connect(str(dst))
    try:
        with bck:
            con.backup(bck)
    finally:
        bck.close()
        con.close()
    return dst

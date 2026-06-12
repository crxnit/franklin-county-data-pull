"""Baseline snapshot of a parcel DB, taken before a refresh overwrites it.

The refresh upserts in place, so without a copy of the prior state there is
nothing to diff against. The refresh job writes the baseline here; the
scripts/db_diff.py reporting tool reads it back. Both must agree on the path,
so the naming lives in one place: snapshot_path().

Stdlib only — keeps the refresh job's import surface light and works without
the backend's third-party deps.
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

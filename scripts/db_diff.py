"""Snapshot a parcel DB before a refresh, then diff it after — for a true
added / removed / changed report (the refresh upserts in place, so without a
baseline copy there is nothing to diff against).

Usage:
    # 1) before refreshing, capture the current state as the baseline
    python -m scripts.db_diff snapshot

    # 2) run the refresh as usual
    python -m server.jobs.refresh
    python -m franklin_housing --refresh

    # 3) report what changed vs the baseline
    python -m scripts.db_diff diff

Both DBs are handled. Rows are keyed on PARCELID; "changed" lists the specific
fields that differ (sale, price, valuations, sqft, etc.).
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path

from franklin_housing.snapshot import snapshot_db, snapshot_path

# (live db, table). franklin_housing.sqlite's table is resolved at runtime.
DBS = [
    ("data/webapp.sqlite", "parcels"),
    ("data/franklin_housing.sqlite", None),
]

# Fields worth reporting when a row changes (skip pulled_at — it always moves).
TRACKED = [
    "SALEDATE", "SALEPRICE", "TOTVALUEBASE", "LNDVALUEBASE", "BLDVALUEBASE",
    "RESFLRAREA_AG", "BEDRMS", "BATHS", "SITEADDRESS", "VALID",
]


def _table(con: sqlite3.Connection, declared: str | None) -> str:
    if declared:
        return declared
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' AND name!='pull_meta'"
    ).fetchall()
    return rows[0][0]


def _fmt_date(ms) -> str | None:
    if ms in (None, 0):
        return None
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date().isoformat()


def _load(db: str, declared: str | None) -> dict[str, dict]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    tbl = _table(con, declared)
    rows = {r["PARCELID"]: dict(r) for r in con.execute(f"SELECT * FROM {tbl}")}
    con.close()
    return rows


def snapshot() -> int:
    for db, _ in DBS:
        dst = snapshot_db(db)
        if dst is None:
            print(f"  skip {db} (not found)")
        else:
            print(f"  snapshot {db} -> {dst}")
    print("baseline captured. refresh, then: python -m scripts.db_diff diff")
    return 0


def _diff_one(db: str, declared: str | None) -> None:
    snap = snapshot_path(db)
    print(f"================= {db} =================")
    if not snap.exists():
        print(f"  no baseline at {snap} — run 'snapshot' before refreshing.")
        return
    old = _load(str(snap), declared)
    new = _load(db, declared)

    added = sorted(new.keys() - old.keys())
    removed = sorted(old.keys() - new.keys())

    changed = []
    for pid in old.keys() & new.keys():
        o, n = old[pid], new[pid]
        deltas = {f: (o.get(f), n.get(f)) for f in TRACKED if o.get(f) != n.get(f)}
        if deltas:
            changed.append((pid, deltas))

    print(f"  total: {len(old):,} -> {len(new):,}  (net {len(new) - len(old):+d})")
    print(f"  added parcels...... {len(added)}")
    print(f"  removed parcels.... {len(removed)}")
    print(f"  changed rows....... {len(changed)}")

    # A moved SALEDATE or SALEPRICE is the most useful signal — a genuinely new
    # transaction (or a price correction on an existing one).
    sales_moved = [(pid, c) for pid, c in changed if "SALEDATE" in c or "SALEPRICE" in c]
    if sales_moved:
        # Sort by the new sale date when present, else current cached date.
        def _key(item):
            pid, c = item
            return (c["SALEDATE"][1] if "SALEDATE" in c else new[pid].get("SALEDATE")) or 0

        print(f"\n  --- {len(sales_moved)} parcels with a NEW/CHANGED sale ---")
        for pid, c in sorted(sales_moved, key=_key, reverse=True)[:25]:
            od, nd = c.get("SALEDATE", (new[pid].get("SALEDATE"),) * 2)
            new_price = c["SALEPRICE"][1] if "SALEPRICE" in c else new[pid].get("SALEPRICE")
            addr = new[pid].get("SITEADDRESS", "")
            print(
                f"    {pid}  {addr:<28.28}  "
                f"{_fmt_date(od)} -> {_fmt_date(nd)}  "
                f"${int(new_price or 0):,}"
            )
        if len(sales_moved) > 25:
            print(f"    ... and {len(sales_moved) - 25} more")

    # Non-sale field changes (valuations etc.), summarised by field. Sale fields
    # are already itemised above.
    field_counts: dict[str, int] = {}
    for _, c in changed:
        for f in c:
            if f not in ("SALEDATE", "SALEPRICE"):
                field_counts[f] = field_counts.get(f, 0) + 1
    if field_counts:
        print("\n  --- other field changes (count of parcels) ---")
        for f, n in sorted(field_counts.items(), key=lambda x: -x[1]):
            print(f"    {f:<16} {n}")

    if added:
        print(f"\n  --- new parcels ({len(added)}) ---")
        for pid in added[:25]:
            print(f"    {pid}  {new[pid].get('SITEADDRESS','')}")
        if len(added) > 25:
            print(f"    ... and {len(added) - 25} more")
    if removed:
        print(f"\n  --- removed parcels ({len(removed)}) ---")
        for pid in removed[:25]:
            print(f"    {pid}  {old[pid].get('SITEADDRESS','')}")


def diff() -> int:
    for db, declared in DBS:
        if not Path(db).exists():
            print(f"================= {db} =================\n  (live DB not found)")
            continue
        _diff_one(db, declared)
        print()
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "snapshot":
        return snapshot()
    if cmd == "diff":
        return diff()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())

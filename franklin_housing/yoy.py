"""Same-period year-over-year trends from the bulk conveyance history.

Answers "how did the last two weeks of August do, year over year?" — a fixed
calendar window (MM-DD..MM-DD) compared across every year of the county's bulk
sales extract (back to ~1986 for Dublin). This is only possible against the
`sales` table that bulk_sales.ingest rebuilds monthly; the GIS `parcels` layer
carries just the latest sale per parcel, so it can't see prior years.

Hygiene mirrors the app's abstain-don't-mislabel discipline:
- pre-2014 rows are uncoded (valid_code = '') — the county only started
  arms-length coding ~2014 — so they're KEPT, behind the price floor;
- county-coded invalid rows (nonzero reason codes) are excluded;
- non-numeric codes (e.g. 'Y - WF FLAG') are abstentions — kept;
- excluded rows are COUNTED per year (n_excluded), never silently dropped.

$/sqft uses the parcel's current RESFLRAREA_AG (the only sqft we have), so it
is approximate for houses that gained additions since the sale.

Stdlib only — lives in the zero-dep core.

Run:  python -m franklin_housing.yoy --window 08-18:08-31   (data/webapp.sqlite)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime

from .analyze import _median
from .bulk_sales import map_valid

PRICE_FLOOR = 10_000  # below this, treat as a non-market transfer

ROWS_SQL = (
    'SELECT s.sale_date, s.price, s.valid_code, s.n_parcels, s.condsale,'
    ' p."RESFLRAREA_AG" AS sqft'
    ' FROM sales s JOIN parcels p ON p."PARCELID" = s.parcelid'
    ' WHERE s.sale_date IS NOT NULL')


def parse_window(spec: str) -> tuple[str, str]:
    """'08-18:08-31' -> ('08-18', '08-31'). Raises ValueError on malformed
    input. A start after the end (e.g. 12-20:01-05) is a valid wrap-around
    window spanning the year boundary."""
    parts = spec.split(":")
    if len(parts) != 2:
        raise ValueError(f"window must be 'MM-DD:MM-DD', got {spec!r}")
    for p in parts:
        try:
            # Zero-padding matters (window compare is lexicographic) and
            # strptime tolerates '8-1', so check the shape explicitly.
            # 2000 is a leap year, so 02-29 validates.
            if len(p) != 5:
                raise ValueError
            datetime.strptime(f"2000-{p}", "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"bad month-day {p!r} in window (want MM-DD)") from None
    return parts[0], parts[1]


def _in_window(mmdd: str, start: str, end: str) -> bool:
    if start <= end:
        return start <= mmdd <= end
    return mmdd >= start or mmdd <= end  # wraps the year boundary


def _window_year(sale_date: str, start: str, end: str) -> int:
    """The year a sale's window instance STARTED in — for a Dec–Jan wrap
    window, January sales belong to the previous year's instance."""
    year = int(sale_date[:4])
    if start > end and sale_date[5:] <= end:
        return year - 1
    return year


def build_yoy(rows: list[dict], start: str, end: str,
              *, price_floor: int = PRICE_FLOOR) -> list[dict]:
    """Per-year medians for the calendar window, oldest first, with
    year-over-year deltas against the immediately preceding year."""
    kept: dict[int, list[dict]] = {}
    excluded: dict[int, int] = {}
    for r in rows:
        d = r["sale_date"]
        if not d or not _in_window(d[5:], start, end):
            continue
        year = _window_year(d, start, end)
        bad = (not r["price"] or r["price"] <= price_floor
               or (r["n_parcels"] or 0) > 1 or r["condsale"]
               or map_valid(r["valid_code"]) == "N")
        if bad:
            excluded[year] = excluded.get(year, 0) + 1
        else:
            kept.setdefault(year, []).append(r)

    out, prev = [], None
    for year in sorted(set(kept) | set(excluded)):
        grp = kept.get(year, [])
        row = {
            "period": str(year),
            "n": len(grp),
            "n_excluded": excluded.get(year, 0),
            "median_price": _median([r["price"] for r in grp]),
            "median_ppsf": _median(
                [r["price"] / r["sqft"] for r in grp if r["sqft"]]),
            "yoy_price_pct": None,
            "yoy_ppsf_pct": None,
        }
        # YoY only against the directly preceding year — a gap means no delta.
        if prev and prev["_year"] == year - 1:
            for key, pct in (("median_price", "yoy_price_pct"),
                             ("median_ppsf", "yoy_ppsf_pct")):
                if row[key] and prev[key]:
                    row[pct] = round((row[key] / prev[key] - 1) * 100, 1)
        prev = {**row, "_year": year}
        out.append(row)
    return out


def fetch_rows(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.execute(ROWS_SQL)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Year-over-year medians for a fixed calendar window.")
    ap.add_argument("db", nargs="?", default="data/webapp.sqlite")
    ap.add_argument("--window", required=True, metavar="MM-DD:MM-DD",
                    help="calendar window, e.g. 08-18:08-31")
    args = ap.parse_args(argv)
    start, end = parse_window(args.window)

    conn = sqlite3.connect(args.db)
    try:
        rows = fetch_rows(conn)
    finally:
        conn.close()

    def pct(v):
        return f"{v:+.1f}%" if v is not None else "-"

    print(f"{'year':>4} {'n':>4} {'excl':>4} {'med price':>10} {'YoY':>7} "
          f"{'med $/sf':>8} {'YoY':>7}")
    for r in build_yoy(rows, start, end):
        mp = f"{r['median_price']:,.0f}" if r["median_price"] else "-"
        sf = f"{r['median_ppsf']:.0f}" if r["median_ppsf"] else "-"
        print(f"{r['period']:>4} {r['n']:>4} {r['n_excluded']:>4} {mp:>10} "
              f"{pct(r['yoy_price_pct']):>7} {sf:>8} {pct(r['yoy_ppsf_pct']):>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

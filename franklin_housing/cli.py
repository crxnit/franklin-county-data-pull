"""Command-line interface for the Franklin County housing pipeline.

Examples
--------
# Step-1 utility: dump a tiny raw sample to confirm fields, then exit
python -m franklin_housing --sample 5 --zip 43017

# Full run (pulls if cache empty), Dublin CSD single-family, last 24 months
python -m franklin_housing

# Force a fresh pull, narrow to a neighborhood, generate comps for my house
python -m franklin_housing --refresh --address "1234 SOMERSET" \
    --subject-sqft 2600 --beds 4 --baths 3 --year 1994 --comps 8 --plots
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys

from . import analyze, clean, trends
from .cache import Cache
from .client import ArcGISClient
from .config import Config
from .snapshot import snapshot_db


def _build_config(args) -> Config:
    cfg = Config()
    return cfg.with_overrides(
        school_district=args.school,
        zips=tuple(args.zip) if args.zip else None,
        class_codes=tuple(args.cls) if args.cls else None,
        nbhdcd=args.nbhd,
        months_back=args.months,
        db_path=args.db,
        subject_address=args.address,
        subject_sqft=args.subject_sqft,
        subject_beds=args.beds,
        subject_baths=args.baths,
        subject_year_built=args.year,
        subject_nbhdcd=args.subject_nbhd,
    )


def _print_table(rows: list[dict], cols: list[str], title: str = "") -> None:
    if title:
        print(f"\n{title}")
    if not rows:
        print("  (no rows)")
        return
    widths = {c: max(len(c), *(len(_fmt(r.get(c))) for r in rows)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    print("  " + header)
    print("  " + "  ".join("-" * widths[c] for c in cols))
    for r in rows:
        print("  " + "  ".join(_fmt(r.get(c)).ljust(widths[c]) for c in cols))


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def _sample(cfg: Config, n: int, args) -> None:
    """Step-1 utility: dump raw JSON for a tiny query."""
    client = ArcGISClient()
    where = cfg.where_clause() if not args.where else args.where
    params = {
        "where": where, "outFields": "*", "returnGeometry": "false",
        "resultRecordCount": n, "f": "json",
    }
    payload = client._get(params)
    print(json.dumps(payload, indent=2)[:8000])
    feats = payload.get("features", [])
    print(f"\n-- {len(feats)} feature(s); where: {where}", file=sys.stderr)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="franklin_housing", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    # target
    p.add_argument("--school", help="school district (default 'DUBLIN CSD')")
    p.add_argument("--zip", action="append", help="ZIP filter (repeatable)")
    p.add_argument("--cls", action="append", help="property class code (default 510)")
    p.add_argument("--nbhd", help="appraiser neighborhood code (NBHDCD) filter")
    p.add_argument("--months", type=int, default=24, help="months of sales history")
    # subject / comps
    p.add_argument("--address", help="subject address substring (for comp seed)")
    p.add_argument("--subject-sqft", type=int)
    p.add_argument("--beds", type=int)
    p.add_argument("--baths", type=int)
    p.add_argument("--year", type=int, help="subject year built")
    p.add_argument("--subject-nbhd", help="subject NBHDCD (restricts comps)")
    p.add_argument("--comps", type=int, default=10, help="number of comps to return")
    # run control
    p.add_argument("--refresh", action="store_true", help="force a fresh pull")
    p.add_argument("--enrich", action="store_true", help="attempt VALID enrichment (scrapes property site)")
    p.add_argument("--enrich-backend", choices=("property_site", "mobile_api"),
                   default="property_site", help="enrichment source (default property_site)")
    p.add_argument("--enrich-limit", type=int, default=25,
                   help="cap parcels enriched (default 25; ~3 HTTP req each)")
    p.add_argument("--sample", type=int, metavar="N", help="dump N raw records and exit")
    p.add_argument("--where", help="raw ArcGIS where clause (overrides target, sample only)")
    p.add_argument("--out", default="data/cleaned_sales.csv", help="cleaned-set CSV path")
    p.add_argument("--plots", action="store_true", help="write distribution PNGs (needs matplotlib)")
    p.add_argument("--db", default="data/franklin_housing.sqlite")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cfg = _build_config(args)

    if args.sample is not None:
        _sample(cfg, args.sample, args)
        return 0

    cache = Cache(cfg.db_path)
    where = cfg.where_clause()

    if args.refresh or cache.is_empty():
        client = ArcGISClient()
        expected = client.count(where)
        print(f"Pulling sales… where: {where}")
        print(f"  server reports {expected:,} matching parcels")
        rows = list(client.query_all(where))
        # Snapshot the prior cache before clearing, so `python -m scripts.db_diff
        # diff` can report what this pull changed. Never let it block the refresh.
        try:
            snap = snapshot_db(cfg.db_path)
            if snap:
                print(f"  baseline snapshot -> {snap}")
        except Exception:
            logging.getLogger(__name__).warning(
                "baseline snapshot failed (continuing)", exc_info=True
            )
        cache.clear()
        cache.save(rows, where)
        print(f"  cached {len(rows):,} rows")
    else:
        meta = cache.last_pull()
        print(f"Using cached data (pulled {meta['pulled_at']}, {meta['row_count']:,} rows). "
              f"Use --refresh to re-pull.")

    if args.enrich:
        from . import enrich
        print(f"VALID enrichment via {args.enrich_backend} "
              f"(limit {args.enrich_limit})…")
        stats = enrich.enrich_valid(cache, backend=args.enrich_backend,
                                    limit=args.enrich_limit,
                                    price_floor=cfg.arms_length_price_floor)
        print("  " + "  ".join(f"{k}={v}" for k, v in stats.items()))

    records = clean.clean_records(cache.load(), cfg)

    # --- summary ---
    s = analyze.summary(records)
    print("\n=== SUMMARY ===")
    for k, v in s.items():
        print(f"  {k:18s}: {_fmt(v)}")

    fb = analyze.flag_breakdown(records)
    if fb:
        print("\n=== HYGIENE FLAGS (rows flagged, not dropped) ===")
        for k, v in fb.items():
            print(f"  {k:20s}: {v:,}")

    # --- trend ---
    tr = analyze.trend(records, by="sale_month")
    _print_table(tr, ["period", "n", "median_ppsf", "median_price"],
                 title="=== MONTHLY TREND (median $/sqft, comps only) ===")

    # --- comps ---
    if args.address or args.subject_sqft or args.subject_nbhd:
        comp_rows, subj = analyze.comps(records, cfg, n=args.comps)
        print(f"\n=== COMP SET (subject: {subj}) ===")
        _print_table(
            comp_rows,
            ["address", "sale_date", "price", "sqft", "price_per_sqft",
             "beds", "baths", "year_built", "sale_to_assessment", "comp_score"],
        )

    # --- distribution ---
    hist = analyze.histogram(records)
    if hist:
        print("\n=== $/sqft DISTRIBUTION (comps) ===")
        maxc = max(h["count"] for h in hist) or 1
        for h in hist:
            bar = "#" * int(40 * h["count"] / maxc)
            print(f"  {h['lo']:>7.1f}–{h['hi']:<7.1f} {h['count']:>4}  {bar}")

    if args.plots:
        paths = analyze.save_plots(records, "data")
        print("\nplots: " + (", ".join(paths) if paths else "matplotlib not installed — skipped"))

    # --- write cleaned set ---
    _write_csv(records, args.out)
    print(f"\nWrote cleaned set ({len(records):,} rows) -> {args.out}")

    # --- write sales-trend artifacts (regenerated on every run) ---
    json_path, csv_path = _write_trends(records, args.out)
    print(f"Wrote sales trends -> {json_path}, {csv_path}")
    cache.close()
    return 0


def _write_csv(records: list[dict], path: str) -> None:
    if not records:
        return
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    cols = list(records[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(records)


def _write_trends(records: list[dict], out_path: str) -> tuple[str, str]:
    """Build the trend report and write it next to the cleaned CSV as both a
    nested JSON (full report) and a flat CSV (long format). Returns the paths."""
    import os
    out_dir = os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)
    report = trends.build_report(records)
    json_path = os.path.join(out_dir, "sales_trends.json")
    csv_path = os.path.join(out_dir, "sales_trends.csv")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    rows = trends.flatten(report)
    cols = ["dimension", "group", "granularity", "period", "n",
            "median_ppsf", "median_price"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return json_path, csv_path


if __name__ == "__main__":
    raise SystemExit(main())

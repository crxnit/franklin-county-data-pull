"""Sales-trend report builder.

One stdlib-only engine that turns cleaned records into median $/sqft and median
price trends across several *dimensions* (overall market, school district,
appraiser neighborhood, price tier, sqft band) and several time *granularities*
(bi-weekly / monthly / quarterly / yearly). Reuses `analyze.window` (recent-sale
filter) and `analyze.trend` (per-period medians) so the math matches the rest of
the app — this module only partitions records and labels the buckets.

Lives in the zero-dep core next to analyze.py so both the CLI and the server can
import it; it never imports from `server`.
"""

from __future__ import annotations

from datetime import date

from . import analyze

# Time buckets, finest first. Each is a field produced by clean.clean_records()
# that analyze.trend(by=...) can group on directly.
GRANULARITIES = ("sale_biweek", "sale_month", "sale_quarter", "sale_year")


def price_tier(price) -> str | None:
    if price is None:
        return None
    if price < 400_000:
        return "<400k"
    if price < 600_000:
        return "400-600k"
    if price < 800_000:
        return "600-800k"
    if price < 1_000_000:
        return "800k-1M"
    return "1M+"


def sqft_band(sqft) -> str | None:
    if sqft is None:
        return None
    if sqft < 1500:
        return "<1500"
    if sqft < 2500:
        return "1500-2500"
    if sqft < 3500:
        return "2500-3500"
    return "3500+"


# Dimension -> function mapping each record to its group label (None drops it).
DIMENSIONS = {
    "overall": lambda r: "all",
    "school": lambda r: r.get("school"),
    "neighborhood": lambda r: r.get("nbhdcd"),
    "price_tier": lambda r: price_tier(r.get("price")),
    "sqft_band": lambda r: sqft_band(r.get("sqft")),
}


def _grouped_trends(records: list[dict], key) -> dict[str, dict[str, list[dict]]]:
    """{group_value: {granularity: trend_rows}} for one dimension's key fn."""
    groups: dict[str, list[dict]] = {}
    for r in records:
        g = key(r)
        if g is None:
            continue
        groups.setdefault(str(g), []).append(r)
    return {
        g: {gran: analyze.trend(rows, by=gran) for gran in GRANULARITIES}
        for g, rows in groups.items()
    }


def build_report(
    records: list[dict], *, months_back: int = 24, today: date | None = None
) -> dict:
    """Full trend report across every dimension and granularity.

    Windows once to recent priced sales, then partitions per dimension. Trend
    medians are still over comps only (analyze.trend filters is_comp). The
    caller stamps `generated_at` (kept None here so the result is pure/testable).
    """
    windowed = analyze.window(records, months_back=months_back, today=today)
    dimensions = {
        dim: _grouped_trends(windowed, key) for dim, key in DIMENSIONS.items()
    }
    return {
        "generated_at": None,
        "months_back": months_back,
        # Convenience: the market-wide monthly line most callers want first.
        "overall": dimensions["overall"].get("all", {}).get("sale_month", []),
        "dimensions": dimensions,
    }


def flatten(report: dict) -> list[dict]:
    """Long-format rows for CSV/spreadsheet use, one per (dimension, group,
    granularity, period)."""
    out = []
    for dim, groups in report.get("dimensions", {}).items():
        for group, by_gran in groups.items():
            for gran, rows in by_gran.items():
                for row in rows:
                    out.append({
                        "dimension": dim,
                        "group": group,
                        "granularity": gran,
                        "period": row["period"],
                        "n": row["n"],
                        "median_ppsf": row["median_ppsf"],
                        "median_price": row["median_price"],
                    })
    return out

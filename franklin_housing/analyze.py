"""Analysis: summary stats, time trends, comp-set generation, distributions.

Stdlib-only (statistics module). All $/sqft aggregates are computed over the
"comp" subset (rows that passed hygiene), while counts also report the flagged
rows so nothing is hidden.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date

from .config import Config


def _median(values):
    vals = [v for v in values if v is not None]
    return round(statistics.median(vals), 2) if vals else None


def _mean(values):
    vals = [v for v in values if v is not None]
    return round(statistics.mean(vals), 2) if vals else None


def _percentile(sorted_vals, q):
    """Linear-interpolated percentile of an already-sorted list."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 < len(sorted_vals):
        return sorted_vals[lo] + frac * (sorted_vals[lo + 1] - sorted_vals[lo])
    return sorted_vals[lo]


def _month_cutoff(months, today):
    """ISO date `months` before the first of `today`'s month, or None."""
    if months is None:
        return None
    m = today.month - 1 - months
    return date(today.year + m // 12, m % 12 + 1, 1).isoformat()


def window(records: list[dict], months_back: int = 24, today: date | None = None):
    """Comp-eligible recent sales: priced sales with a sale_date within the
    window. The webapp pulls ALL parcels (so any address is lookup-able), so
    comp/analysis math must restrict to the recent-sale window in code."""
    cut = _month_cutoff(months_back, today or date.today())
    return [r for r in records
            if r.get("price") and r.get("sale_date") and (cut is None or r["sale_date"] >= cut)]


def price_estimate(records, *, subject_sqft, subject_assessed=None, nbhdcd=None,
                   band=0.15, recency_months=(None, 12), today=None):
    """Size-matched $/sqft pricing estimate for a subject home.

    Estimate = median price_per_sqft of comps within ±`band` of `subject_sqft`
    (restricted to `nbhdcd` when given and populated) × `subject_sqft`. Returns
    the recency-view table, an anchor value with a p40–p60 range, the comps
    used, and a sale-to-assessment sanity ratio. Pure/stdlib; formalized from
    scripts/whigham_report.py and reused by the report + comps endpoints.
    """
    today = today or date.today()
    pool = [r for r in records if r.get("is_comp") and r.get("price_per_sqft")]
    if nbhdcd:
        nb = [r for r in pool if r.get("nbhdcd") == nbhdcd]
        if nb:
            pool = nb

    if not subject_sqft:
        return {"subject_sqft": subject_sqft, "band": band, "nbhdcd": nbhdcd,
                "views": [], "anchor": {"value": None, "low": None, "high": None},
                "size_matched_comps": [], "sanity": None}

    lo_sqft, hi_sqft = subject_sqft * (1 - band), subject_sqft * (1 + band)
    size_matched = [r for r in pool if r.get("sqft") and lo_sqft <= r["sqft"] <= hi_sqft]

    views = []

    def _view(label, rows):
        ppsf = sorted(r["price_per_sqft"] for r in rows)
        med = round(statistics.median(ppsf), 2) if ppsf else None
        views.append({"label": label, "n": len(rows), "median_ppsf": med,
                      "estimate": round(med * subject_sqft) if med else None})

    _view("all_comps_neighborhood", pool)
    for months in recency_months:
        cut = _month_cutoff(months, today)
        rows = [r for r in size_matched
                if cut is None or (r.get("sale_date") and r["sale_date"] >= cut)]
        _view("size_matched_all" if months is None else f"size_matched_{months}mo", rows)

    sm_ppsf = sorted(r["price_per_sqft"] for r in size_matched)
    value = round(statistics.median(sm_ppsf) * subject_sqft) if sm_ppsf else None
    if len(sm_ppsf) >= 4:
        low = round(_percentile(sm_ppsf, 0.40) * subject_sqft)
        high = round(_percentile(sm_ppsf, 0.60) * subject_sqft)
    elif sm_ppsf:
        low, high = round(min(sm_ppsf) * subject_sqft), round(max(sm_ppsf) * subject_sqft)
    else:
        low = high = None

    return {
        "subject_sqft": subject_sqft,
        "band": band,
        "nbhdcd": nbhdcd,
        "views": views,
        "anchor": {"value": value, "low": low, "high": high},
        "size_matched_comps": sorted(size_matched, key=lambda r: r.get("sale_date") or "",
                                     reverse=True),
        "sanity": round(value / subject_assessed, 3) if (value and subject_assessed) else None,
    }


def summary(records: list[dict]) -> dict:
    comps = [r for r in records if r["is_comp"]]
    flagged = [r for r in records if r["flags"]]
    ppsf = [r["price_per_sqft"] for r in comps]
    prices = [r["price"] for r in comps]
    return {
        "rows_total": len(records),
        "comps_usable": len(comps),
        "rows_flagged": len(flagged),
        "median_ppsf": _median(ppsf),
        "mean_ppsf": _mean(ppsf),
        "median_price": _median(prices),
        "mean_price": _mean(prices),
        "median_sqft": _median([r["sqft"] for r in comps]),
    }


def trend(records: list[dict], by: str = "sale_month") -> list[dict]:
    """Median $/sqft and median price per period (month/quarter/year)."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if r["is_comp"] and r.get(by):
            buckets[r[by]].append(r)
    rows = []
    for period in sorted(buckets):
        grp = buckets[period]
        rows.append({
            "period": period,
            "n": len(grp),
            "median_ppsf": _median([r["price_per_sqft"] for r in grp]),
            "median_price": _median([r["price"] for r in grp]),
        })
    return rows


def flag_breakdown(records: list[dict]) -> dict:
    counts: dict[str, int] = defaultdict(int)
    for r in records:
        for f in (r["flags"].split(",") if r["flags"] else []):
            counts[f] += 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def find_subject(records: list[dict], address_substr: str) -> dict | None:
    needle = address_substr.strip().upper()
    for r in records:
        if r["address"] and needle in r["address"].upper():
            return r
    return None


def comps(records: list[dict], cfg: Config, n: int = 10) -> list[dict]:
    """Return the N closest comparable sales to the subject.

    Similarity is a weighted, normalized distance over sqft / beds / baths /
    year-built. If a subject neighborhood (`nbhdcd`) is known, comps are
    restricted to it (the tightest grouping) before scoring; otherwise scoring
    runs across the whole cleaned set.
    """
    pool = [r for r in records if r["is_comp"]]

    # Seed subject attributes from config, optionally discovering them from the
    # subject's own record by address.
    subj = {
        "nbhdcd": cfg.subject_nbhdcd,
        "sqft": cfg.subject_sqft,
        "beds": cfg.subject_beds,
        "baths": cfg.subject_baths,
        "year_built": cfg.subject_year_built,
    }
    if cfg.subject_address:
        rec = find_subject(records, cfg.subject_address)
        if rec:
            subj.setdefault("nbhdcd", rec.get("nbhdcd"))
            for k_subj, k_rec in (("nbhdcd", "nbhdcd"), ("sqft", "sqft"),
                                  ("beds", "beds"), ("baths", "baths"),
                                  ("year_built", "year_built")):
                if subj.get(k_subj) is None:
                    subj[k_subj] = rec.get(k_rec)
            pool = [r for r in pool if r["parcelid"] != rec["parcelid"]]

    if subj.get("nbhdcd"):
        same = [r for r in pool if r["nbhdcd"] == subj["nbhdcd"]]
        if same:
            pool = same

    def to_f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    s_sqft, s_beds = to_f(subj["sqft"]), to_f(subj["beds"])
    s_baths, s_year = to_f(subj["baths"]), to_f(subj["year_built"])

    def score(r):
        s = 0.0
        rs = to_f(r["sqft"])
        if s_sqft and rs:
            s += abs(rs - s_sqft) / s_sqft           # fractional sqft diff
        rb = to_f(r["beds"])
        if s_beds is not None and rb is not None:
            s += abs(rb - s_beds) * 0.15
        rba = to_f(r["baths"])
        if s_baths is not None and rba is not None:
            s += abs(rba - s_baths) * 0.15
        ry = to_f(r["year_built"])
        if s_year and ry:
            s += abs(ry - s_year) / 50.0             # ~50yr span normalizer
        return s

    ranked = sorted(pool, key=score)
    out = []
    for r in ranked[:n]:
        out.append({**r, "comp_score": round(score(r), 3)})
    return out, subj


def histogram(records: list[dict], bins: int = 12) -> list[dict]:
    """$/sqft distribution as text-friendly bins (comps only)."""
    vals = sorted(r["price_per_sqft"] for r in records
                  if r["is_comp"] and r["price_per_sqft"] is not None)
    if not vals:
        return []
    lo, hi = vals[0], vals[-1]
    if hi == lo:
        return [{"lo": lo, "hi": hi, "count": len(vals)}]
    width = (hi - lo) / bins
    out = []
    for i in range(bins):
        b_lo = lo + i * width
        b_hi = b_lo + width
        if i == bins - 1:
            count = sum(1 for v in vals if b_lo <= v <= b_hi)
        else:
            count = sum(1 for v in vals if b_lo <= v < b_hi)
        out.append({"lo": round(b_lo, 1), "hi": round(b_hi, 1), "count": count})
    return out


def save_plots(records: list[dict], out_dir: str) -> list[str]:
    """Write $/sqft histogram and price-vs-sqft scatter PNGs IF matplotlib is
    installed. Returns paths written (empty list if matplotlib is absent)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    import os
    os.makedirs(out_dir, exist_ok=True)
    comps_ = [r for r in records if r["is_comp"]]
    ppsf = [r["price_per_sqft"] for r in comps_]
    sqft = [r["sqft"] for r in comps_]
    price = [r["price"] for r in comps_]
    paths = []

    fig, ax = plt.subplots()
    ax.hist(ppsf, bins=20)
    ax.set_xlabel("$/sqft")
    ax.set_ylabel("sales")
    ax.set_title("$/sqft distribution")
    p1 = os.path.join(out_dir, "ppsf_hist.png")
    fig.savefig(p1, dpi=110, bbox_inches="tight")
    plt.close(fig)
    paths.append(p1)

    fig, ax = plt.subplots()
    ax.scatter(sqft, price, s=10, alpha=0.5)
    ax.set_xlabel("above-grade sqft")
    ax.set_ylabel("sale price")
    ax.set_title("price vs sqft")
    p2 = os.path.join(out_dir, "price_vs_sqft.png")
    fig.savefig(p2, dpi=110, bbox_inches="tight")
    plt.close(fig)
    paths.append(p2)
    return paths

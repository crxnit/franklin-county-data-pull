"""Cleaning / hygiene layer.

Turns raw cached rows into analysis records with computed `price_per_sqft` and
sale-to-assessment `ratio`, and attaches explicit hygiene *flags*. Per the
spec, suspect rows are FLAGGED, never silently dropped — callers decide whether
to exclude them.

VALID is null on the GIS layer, so arms-length judgement uses a proxy:
  - sale price below `arms_length_price_floor`  -> likely non-arms-length
  - sale-to-assessment ratio outside [ratio_low, ratio_high] -> flagged
If the optional enrichment step populated a true VALID, it takes precedence.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .config import SQFT_FIELD, Config

# Anchor for bi-weekly buckets: a fixed Monday, so every 14-day block starts on
# a Monday and block-start ISO dates sort chronologically.
_BIWEEK_ANCHOR = date(1970, 1, 5)


def _epoch_ms_to_date(ms):
    if ms in (None, ""):
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date()


def _biweek_start(d: date) -> str:
    """ISO date of the 14-day block (anchored on a Monday) containing `d`."""
    blocks = (d - _BIWEEK_ANCHOR).days // 14
    return (_BIWEEK_ANCHOR + timedelta(days=blocks * 14)).isoformat()


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def clean_records(rows: list[dict], cfg: Config) -> list[dict]:
    out = []
    for r in rows:
        d = _epoch_ms_to_date(r.get("SALEDATE"))
        price = _num(r.get("SALEPRICE"))
        sqft = _num(r.get(SQFT_FIELD))
        assessed = _num(r.get("TOTVALUEBASE"))

        ppsf = price / sqft if (price and sqft and sqft > 0) else None
        ratio = price / assessed if (price and assessed and assessed > 0) else None

        flags = []
        if price is None or price <= 0:
            flags.append("missing_price")
        if not sqft or sqft <= 0:
            flags.append("missing_sqft")
        if price is not None and price < cfg.arms_length_price_floor:
            flags.append("below_price_floor")
        if ratio is not None and not (cfg.ratio_low <= ratio <= cfg.ratio_high):
            flags.append("ratio_outlier")
        if ppsf is not None and not (cfg.ppsf_low <= ppsf <= cfg.ppsf_high):
            flags.append("ppsf_outlier")

        # True VALID (from enrichment) wins if present; 'N'/'0' => invalid.
        true_valid = r.get("VALID")
        if true_valid not in (None, ""):
            arms_length = str(true_valid).strip().upper() in ("Y", "1", "VALID", "V")
            if not arms_length:
                flags.append("valid_flag_invalid")
        else:
            # proxy: arms-length unless price-floor or ratio says otherwise
            arms_length = not ({"below_price_floor", "ratio_outlier"} & set(flags))

        # A row usable as a $/sqft comp: has sqft, has a price, looks arms-length,
        # and isn't a $/sqft outlier.
        is_comp = (
            sqft and sqft > 0
            and ppsf is not None
            and "ppsf_outlier" not in flags
            and arms_length
        )

        out.append({
            "parcelid": r.get("PARCELID"),
            "address": r.get("SITEADDRESS"),
            "zip": r.get("ZIPCD"),
            "school": r.get("SCHLDSCRP"),
            "nbhdcd": r.get("NBHDCD"),
            "class": r.get("CLASSCD"),
            "sale_date": d.isoformat() if d else None,
            "sale_year": d.year if d else None,
            "sale_month": f"{d.year:04d}-{d.month:02d}" if d else None,
            "sale_quarter": f"{d.year:04d}-Q{(d.month - 1)//3 + 1}" if d else None,
            "sale_biweek": _biweek_start(d) if d else None,
            "price": price,
            "sqft": int(sqft) if sqft else None,
            "price_per_sqft": round(ppsf, 2) if ppsf is not None else None,
            "assessed": assessed,
            "sale_to_assessment": round(ratio, 3) if ratio is not None else None,
            "year_built": r.get("RESYRBLT"),
            "beds": r.get("BEDRMS"),
            "baths": r.get("BATHS"),
            "x_coord": _num(r.get("X_COORD")),
            "y_coord": _num(r.get("Y_COORD")),
            "valid_raw": true_valid,
            "arms_length": arms_length,
            "is_comp": bool(is_comp),
            "flags": ",".join(flags),
        })
    # newest first
    out.sort(key=lambda x: x["sale_date"] or "", reverse=True)
    return out

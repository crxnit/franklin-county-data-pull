"""Unit tests for the sales-trend engine (no DB required)."""

from datetime import date, datetime, timedelta, timezone

from franklin_housing import trends
from franklin_housing.clean import _BIWEEK_ANCHOR, _biweek_start, clean_records
from franklin_housing.config import Config


def _epoch_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def _raw(d: date, price, sqft, *, school="DUBLIN CSD", nbhd="00111000", assessed=None):
    """A raw cached row that cleans to an arms-length comp."""
    return {
        "PARCELID": f"p-{d.isoformat()}-{price}-{sqft}",
        "SITEADDRESS": "1 TEST ST",
        "SCHLDSCRP": school,
        "NBHDCD": nbhd,
        "CLASSCD": "510",
        "SALEDATE": _epoch_ms(d),
        "SALEPRICE": price,
        "RESFLRAREA_AG": sqft,
        "TOTVALUEBASE": assessed if assessed is not None else price,
    }


def _clean(rows):
    return clean_records(rows, Config())


def test_biweek_boundaries():
    block_start = _BIWEEK_ANCHOR + timedelta(days=100 * 14)  # a known Monday block
    same = block_start + timedelta(days=13)
    nxt = block_start + timedelta(days=14)
    assert _biweek_start(block_start) == block_start.isoformat()
    assert _biweek_start(same) == block_start.isoformat()
    assert _biweek_start(nxt) != block_start.isoformat()
    # Labels sort chronologically (used directly as trend period strings).
    assert _biweek_start(block_start) < _biweek_start(nxt)


def test_clean_emits_sale_biweek():
    rec = _clean([_raw(date(2026, 6, 15), 500_000, 2000)])[0]
    assert rec["sale_biweek"] == _biweek_start(date(2026, 6, 15))
    assert rec["sale_month"] == "2026-06"


def test_price_tier_and_sqft_band():
    assert trends.price_tier(399_999) == "<400k"
    assert trends.price_tier(400_000) == "400-600k"
    assert trends.price_tier(1_000_000) == "1M+"
    assert trends.price_tier(None) is None
    assert trends.sqft_band(1499) == "<1500"
    assert trends.sqft_band(2500) == "2500-3500"
    assert trends.sqft_band(None) is None


def test_build_report_shape_and_dimensions():
    today = date(2026, 6, 20)
    rows = [
        _raw(date(2026, 6, 10), 500_000, 2000, nbhd="A", school="DUBLIN CSD"),
        _raw(date(2026, 5, 5), 700_000, 2500, nbhd="B", school="DUBLIN CSD"),
        _raw(date(2026, 4, 1), 900_000, 3000, nbhd="A", school="HILLIARD CSD"),
    ]
    report = trends.build_report(_clean(rows), today=today)
    dims = report["dimensions"]
    assert set(dims) == {"overall", "school", "neighborhood", "price_tier", "sqft_band"}
    assert report["months_back"] == 24
    # Overall has a single 'all' group with all four granularities.
    assert set(dims["overall"]["all"]) == set(trends.GRANULARITIES)
    # Neighborhood A grouped the two A-sales.
    assert set(dims["neighborhood"]) == {"A", "B"}
    # Convenience overall monthly line is present and sorted.
    months = [r["period"] for r in report["overall"]]
    assert months == sorted(months)
    assert {"2026-04", "2026-05", "2026-06"} <= set(months)


def test_trend_is_comps_only():
    today = date(2026, 6, 20)
    # A $0 transfer is not arms-length -> not a comp -> excluded from trends.
    rows = [
        _raw(date(2026, 6, 10), 500_000, 2000, nbhd="A"),
        _raw(date(2026, 6, 11), 0, 2000, nbhd="A"),
    ]
    report = trends.build_report(_clean(rows), today=today)
    monthly = report["dimensions"]["neighborhood"]["A"]["sale_month"]
    assert len(monthly) == 1
    assert monthly[0]["n"] == 1


def test_flatten_roundtrip():
    today = date(2026, 6, 20)
    rows = [_raw(date(2026, 6, 10), 500_000, 2000, nbhd="A")]
    report = trends.build_report(_clean(rows), today=today)
    flat = trends.flatten(report)
    assert flat, "expected at least one flattened row"
    cols = {"dimension", "group", "granularity", "period", "n", "median_ppsf", "median_price"}
    assert all(cols == set(r) for r in flat)
    # The single comp shows up under overall/all and neighborhood/A.
    keys = {(r["dimension"], r["group"]) for r in flat}
    assert ("overall", "all") in keys
    assert ("neighborhood", "A") in keys

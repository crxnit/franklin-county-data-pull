"""Tests for the same-period year-over-year engine."""

import pytest

from franklin_housing.yoy import build_yoy, parse_window


def row(date, price, sqft=2000, valid="", n_parcels=1, condsale=""):
    return {"sale_date": date, "price": price, "sqft": sqft,
            "valid_code": valid, "n_parcels": n_parcels, "condsale": condsale}


def test_parse_window():
    assert parse_window("08-18:08-31") == ("08-18", "08-31")
    assert parse_window("02-29:03-01") == ("02-29", "03-01")  # leap day OK
    for bad in ("junk", "08-18", "13-01:08-31", "08-32:08-31", "8-1:8-2"):
        with pytest.raises(ValueError):
            parse_window(bad)


def test_basic_yoy_pct():
    rows = [row("2023-08-20", 400_000), row("2023-08-25", 500_000),
            row("2024-08-19", 550_000)]
    out = build_yoy(rows, "08-18", "08-31")
    assert [r["period"] for r in out] == ["2023", "2024"]
    assert out[0]["median_price"] == 450_000
    assert out[0]["yoy_price_pct"] is None  # no prior year
    assert out[1]["yoy_price_pct"] == pytest.approx(22.2, abs=0.05)
    assert out[1]["median_ppsf"] == pytest.approx(275, abs=0.5)


def test_window_bounds():
    rows = [row("2024-08-17", 100_000), row("2024-08-18", 200_000),
            row("2024-08-31", 300_000), row("2024-09-01", 400_000)]
    (out,) = build_yoy(rows, "08-18", "08-31")
    assert out["n"] == 2  # boundary dates in, neighbors out


def test_exclusions_counted_not_dropped():
    rows = [
        row("2024-08-20", 500_000),                                # kept
        row("2024-08-20", 0),                                      # zero price
        row("2024-08-21", 500_000, n_parcels=3),                   # multi-parcel
        row("2024-08-22", 500_000, condsale="grantorrelative"),    # conditional
        row("2024-08-23", 500_000, valid="99 - RMS INVALID"),      # county-coded N
    ]
    (out,) = build_yoy(rows, "08-18", "08-31")
    assert out["n"] == 1
    assert out["n_excluded"] == 4


def test_uncoded_and_abstain_kept():
    """Pre-2014 rows are uncoded ('') and non-numeric codes are abstentions —
    both stay; only a numeric nonzero reason code excludes."""
    rows = [row("1995-08-20", 150_000, valid=""),
            row("2024-08-20", 500_000, valid="0 - VALID"),
            row("2024-08-21", 500_000, valid="Y - WF FLAG"),
            row("2024-08-22", 500_000, valid="1 - RELATED INDIV/CORP")]
    out = build_yoy(rows, "08-18", "08-31")
    by = {r["period"]: r for r in out}
    assert by["1995"]["n"] == 1
    assert by["2024"]["n"] == 2 and by["2024"]["n_excluded"] == 1


def test_wrap_window_assigns_january_to_prior_year():
    rows = [row("2023-12-28", 400_000), row("2024-01-03", 500_000),
            row("2024-12-22", 550_000)]
    out = build_yoy(rows, "12-20", "01-05")
    by = {r["period"]: r for r in out}
    assert by["2023"]["n"] == 2  # Dec 2023 + Jan 2024 = the 2023 window
    assert by["2024"]["median_price"] == 550_000
    assert by["2024"]["yoy_price_pct"] == pytest.approx(22.2, abs=0.05)


def test_gap_year_has_no_pct():
    rows = [row("2019-08-20", 300_000), row("2021-08-20", 400_000)]
    out = build_yoy(rows, "08-18", "08-31")
    assert out[1]["period"] == "2021"
    assert out[1]["yoy_price_pct"] is None  # 2020 missing — no adjacent delta


def test_missing_sqft_price_still_counts():
    (out,) = build_yoy([row("2024-08-20", 500_000, sqft=None)], "08-18", "08-31")
    assert out["n"] == 1
    assert out["median_price"] == 500_000
    assert out["median_ppsf"] is None

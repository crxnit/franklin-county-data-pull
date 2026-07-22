"""Tests for the append-only sales-history ledger."""

import sqlite3

from franklin_housing.history import history_path, record_sales

# 2024-06-15 / 2026-03-01 as epoch ms (what the GIS layer returns)
MS_2024 = 1718409600000
MS_2026 = 1772323200000


def _row(parcelid="273-000001", saledate=MS_2024, saleprice=500000.0, **kw):
    base = {
        "PARCELID": parcelid, "SALEDATE": saledate, "SALEPRICE": saleprice,
        "SITEADDRESS": "1 TEST ST", "NBHDCD": "00111000",
        "SCHLDSCRP": "DUBLIN CSD", "CLASSCD": "510",
        "RESFLRAREA_AG": 2000, "TOTVALUEBASE": 400000,
    }
    base.update(kw)
    return base


def _sales(db_path):
    conn = sqlite3.connect(str(history_path(db_path)))
    try:
        return conn.execute(
            "SELECT parcelid, sale_date, sale_price, source FROM sales"
            " ORDER BY parcelid, sale_date"
        ).fetchall()
    finally:
        conn.close()


def test_records_and_dedupes(tmp_path):
    db = tmp_path / "cache.sqlite"
    rows = [_row()]
    assert record_sales(db, rows, source="test") == 1
    # same sale observed again (the daily-refresh common case) -> no new row
    assert record_sales(db, rows, source="test") == 0
    assert len(_sales(db)) == 1


def test_resale_accumulates_both_sales(tmp_path):
    db = tmp_path / "cache.sqlite"
    record_sales(db, [_row(saledate=MS_2024, saleprice=500000.0)], source="test")
    # the layer overwrote the parcel's sale; the ledger keeps both
    assert record_sales(
        db, [_row(saledate=MS_2026, saleprice=560000.0)], source="test") == 1
    got = _sales(db)
    assert [(r[1], r[2]) for r in got] == [
        ("2024-06-15", 500000.0), ("2026-03-01", 560000.0)]


def test_never_sold_parcel_skipped(tmp_path):
    db = tmp_path / "cache.sqlite"
    assert record_sales(db, [_row(saledate=None)], source="test") == 0


def test_null_price_coerced_to_zero_and_stable(tmp_path):
    db = tmp_path / "cache.sqlite"
    assert record_sales(db, [_row(saleprice=None)], source="test") == 1
    # must not re-insert as a distinct NULL on the next observation
    assert record_sales(db, [_row(saleprice=None)], source="test") == 0
    assert _sales(db)[0][2] == 0.0


def test_history_db_override(tmp_path):
    src = tmp_path / "snapshots" / "webapp.baseline.sqlite"
    ledger = tmp_path / "sales_history.sqlite"
    assert record_sales(src, [_row()], source="backfill:test",
                        history_db=ledger) == 1
    assert ledger.exists()
    assert not history_path(src).exists()

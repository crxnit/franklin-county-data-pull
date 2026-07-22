"""Tests for the monthly bulk sales-history ingest."""

import csv
import io
import sqlite3
import zipfile

from franklin_housing.bulk_sales import (
    _needed_members,
    annotate_valid,
    ingest,
    map_valid,
)
from franklin_housing.cache import Cache

COLS = ["PARCEL ID", "MAP ROUTING", "SALEDT", "NOPAR", "INSTRUMENT",
        "INSTRUNO", "VALID", "SALETYPE", "PRICE", "ADJAMT", "ADJPRICE",
        "CONDSALE_GRANTORRELATIVE", "CONDSALE_LANDCONTRACT"]

# (parcel, date, nopar, instrument, valid, price, condsale_relative)
SALES = [
    ("273-000001-00", "05/03/1993", "1", "WD - (General) Warranty Deed",
     "", "288000", "N"),
    ("273-000001-00", "06/10/2025", "1", "GW - General Warranty Deed",
     "0 - VALID", "500000", "N"),
    ("273-000001-00", "01/01/0001", "1", "", "", "0", "N"),          # bad date
    ("273-000002-00", "02/02/2024", "3", "QC - Quit-Claim Deed",
     "17 - MULTIPLE PARCEL SALE", "0", "Y"),
    ("999-999999-00", "01/01/2020", "1", "WD", "", "100000", "N"),   # untracked
]


def _bundle(tmp_path, name="Sales020-277.txt"):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="\t")
    w.writerow(COLS)
    for p, d, nopar, inst, valid, price, rel in SALES:
        w.writerow([p, "", d, nopar, inst, "123", valid, "", price, "0",
                    price, rel, "N"])
    zp = tmp_path / "Tab-Delimited.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr(name, "\ufeff" + buf.getvalue())  # county files carry a BOM
    return zp


def _db(tmp_path):
    db = tmp_path / "webapp.sqlite"
    c = Cache(str(db))
    c.save([{"PARCELID": "273-000001", "SALEDATE": 1749513600000,  # 2025-06-10
             "SALEPRICE": 500000.0},
            {"PARCELID": "273-000002", "SALEDATE": None, "SALEPRICE": None}],
           "test")
    c.close()
    return db


def test_needed_members():
    names = ["Sales010.txt", "Sales020-277.txt", "Sales410-610.txt", "Parcel.txt"]
    assert _needed_members(names, {273, 590}) == ["Sales020-277.txt",
                                                  "Sales410-610.txt"]
    assert _needed_members(names, {10}) == ["Sales010.txt"]


def test_map_valid():
    assert map_valid("0 - VALID") == "Y"
    assert map_valid("99 - RMS INVALID") == "N"
    assert map_valid("17 - MULTIPLE PARCEL SALE") == "N"
    assert map_valid("Y - WF FLAG") is None      # non-numeric -> abstain
    assert map_valid("") is None
    assert map_valid(None) is None


def test_ingest_filters_normalizes_flags(tmp_path):
    db = _db(tmp_path)
    stats = ingest(db, zip_path=_bundle(tmp_path), extract_date="2026-07-15")
    assert stats["sales"] == 4                    # untracked 999- row dropped
    assert stats["parcels"] == 2
    assert stats["coded_valid"] == 2
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT parcelid, sale_date, flags, condsale FROM sales"
                        " ORDER BY parcelid, sale_date IS NULL, sale_date").fetchall()
    conn.close()
    assert rows[0] == ("273-000001", "1993-05-03", "", "")
    assert rows[1] == ("273-000001", "2025-06-10", "", "")
    # bad date: surfaced with NULL date + flag, not dropped
    assert rows[2][1] is None and "bad_date" in rows[2][2]
    # multi-parcel $0 conditional quit-claim: all three flags attached
    assert rows[3][0] == "273-000002"
    assert set(rows[3][2].split(",")) == {"zero_price", "multi_parcel",
                                          "conditional_sale"}
    assert rows[3][3] == "grantorrelative"


def test_ingest_rebuild_is_idempotent(tmp_path):
    db = _db(tmp_path)
    bundle = _bundle(tmp_path)
    ingest(db, zip_path=bundle, extract_date="2026-07-15")
    stats = ingest(db, zip_path=bundle, extract_date="2026-07-15")
    assert stats["sales"] == 4                    # replaced, not accumulated
    conn = sqlite3.connect(str(db))
    assert conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM sales_meta").fetchone()[0] == 2
    conn.close()


def test_annotate_valid_matches_latest_sale(tmp_path):
    db = _db(tmp_path)
    ingest(db, zip_path=_bundle(tmp_path), extract_date="2026-07-15")
    rows = [
        {"PARCELID": "273-000001", "SALEDATE": 1749513600000,
         "SALEPRICE": 500000.0, "VALID": None},                  # coded match
        {"PARCELID": "273-000001", "SALEDATE": 1749513600000,
         "SALEPRICE": 999999.0, "VALID": None},                  # price mismatch
        {"PARCELID": "273-000002", "SALEDATE": None,
         "SALEPRICE": None, "VALID": None},                      # never sold
    ]
    conn = sqlite3.connect(str(db))
    assert annotate_valid(rows, conn) == 1
    conn.close()
    assert rows[0]["VALID"] == "Y"
    assert rows[1]["VALID"] is None
    assert rows[2]["VALID"] is None


def test_annotate_valid_no_sales_table(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "empty.sqlite"))
    assert annotate_valid([{"PARCELID": "x", "SALEDATE": 1, "SALEPRICE": 1}],
                          conn) == 0
    conn.close()

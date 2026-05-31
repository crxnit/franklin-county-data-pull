"""Unit oracle for analyze.price_estimate — the Whigham case must yield the
size-matched anchor the CLI/report produced (~$523K)."""

import os
from datetime import date

import pytest

from franklin_housing.analyze import price_estimate, window
from franklin_housing.cache import Cache
from franklin_housing.clean import clean_records
from franklin_housing.config import Config

DB = "data/webapp.sqlite"


@pytest.mark.skipif(not os.path.exists(DB), reason="webapp.sqlite not seeded")
def test_whigham_anchor():
    recs = clean_records(Cache(DB).load(), Config())
    windowed = window(recs, months_back=24, today=date(2026, 5, 30))
    est = price_estimate(windowed, subject_sqft=1868, subject_assessed=417900,
                         nbhdcd="00111000", today=date(2026, 5, 30))
    assert 510_000 <= est["anchor"]["value"] <= 535_000
    assert est["anchor"]["low"] <= est["anchor"]["value"] <= est["anchor"]["high"]
    assert est["sanity"] and 1.1 <= est["sanity"] <= 1.4
    sm = next(v for v in est["views"] if v["label"] == "size_matched_all")
    assert sm["n"] >= 5


def test_no_subject_sqft_safe():
    est = price_estimate([], subject_sqft=None)
    assert est["anchor"]["value"] is None

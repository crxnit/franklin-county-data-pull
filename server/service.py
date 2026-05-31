"""Service layer: builds the report/comps payloads by composing the existing
franklin_housing.analyze functions. Routers stay thin."""

from __future__ import annotations

from franklin_housing import analyze
from franklin_housing.config import Config

from .repo import ReadRepo


def find_parcel(records: list[dict], *, parcelid=None, address=None) -> dict | None:
    if parcelid:
        for r in records:
            if r["parcelid"] == parcelid:
                return r
        return None
    if address:
        needle = address.strip().upper()
        matches = [r for r in records if r["address"] and needle in r["address"].upper()]
        if matches:
            # prefer an exact house-number + street match (shortest address wins)
            return min(matches, key=lambda r: len(r["address"]))
    return None


def build_report(repo: ReadRepo, *, parcelid=None, address=None, subject_sqft=None,
                 beds=None, baths=None, year_built=None, nbhdcd=None,
                 comp_count=10, size_band=0.15, months_back=24) -> dict:
    records = repo.records()
    subj_rec = find_parcel(records, parcelid=parcelid, address=address)

    # Seed subject attributes from the looked-up parcel, letting explicit
    # request values override (the comp-tuner passes overrides).
    def pick(override, key):
        return override if override is not None else (subj_rec.get(key) if subj_rec else None)

    s_sqft = pick(subject_sqft, "sqft")
    s_beds = pick(beds, "beds")
    s_baths = pick(baths, "baths")
    s_year = pick(year_built, "year_built")
    s_nbhd = pick(nbhdcd, "nbhdcd")
    s_assessed = subj_rec.get("assessed") if subj_rec else None

    windowed = analyze.window(records, months_back=months_back)

    cfg = Config().with_overrides(
        subject_address=address if subj_rec else None,
        subject_sqft=s_sqft, subject_beds=s_beds, subject_baths=s_baths,
        subject_year_built=s_year, subject_nbhdcd=s_nbhd)
    comp_rows, subj = analyze.comps(windowed, cfg, n=comp_count)

    estimate = analyze.price_estimate(
        windowed, subject_sqft=s_sqft, subject_assessed=s_assessed,
        nbhdcd=s_nbhd, band=size_band)

    nbhd_comps = [r for r in windowed if r["nbhdcd"] == s_nbhd] if s_nbhd else windowed
    summary = analyze.summary(nbhd_comps)

    meta = repo.meta()
    return {
        "subject": {
            "parcelid": subj_rec.get("parcelid") if subj_rec else None,
            "address": subj_rec.get("address") if subj_rec else address,
            "sqft": s_sqft, "beds": s_beds, "baths": s_baths,
            "year_built": s_year, "nbhdcd": s_nbhd, "assessed": s_assessed,
            "resolved": subj_rec is not None,
        },
        "estimate": estimate,
        "comps": comp_rows,
        "neighborhood_summary": summary,
        "best_anchor_sale": comp_rows[0] if comp_rows else None,
        "data_as_of": meta["last_pull"]["pulled_at"] if meta["last_pull"] else None,
        "valid_basis": "ratio_proxy",
    }

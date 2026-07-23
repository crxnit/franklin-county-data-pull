"""Sales-trend endpoint.

Serves slices of the trend report that the daily refresh materializes (with a
recompute fallback in ReadRepo). One report covers every dimension (overall,
school, neighborhood, price_tier, sqft_band) and granularity (sale_biweek,
sale_month, sale_quarter, sale_year); the query params pick the slice.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from franklin_housing.neighborhoods import label_for
from franklin_housing.trends import DIMENSIONS, GRANULARITIES
from franklin_housing.yoy import parse_window

from ..deps import get_repo
from ..repo import ReadRepo

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/dimensions")
def list_dimensions(repo: ReadRepo = Depends(get_repo)):
    """Available dimensions, their group values, and granularities — lets the
    UI populate dropdowns without hardcoding what's present in this pull."""
    report = repo.trends()
    dims = report.get("dimensions", {})

    def _dim(dim):
        groups = sorted(dims.get(dim, {}).keys())
        entry = {"key": dim, "groups": groups}
        # The neighborhood dimension groups by NBHDCD code; ship display labels
        # ("Name (code)") so the UI can label dropdowns without re-deriving the
        # mapping. The code keeps duplicate-named neighborhoods distinguishable.
        if dim == "neighborhood":
            entry["labels"] = {g: label_for(g) for g in groups}
        return entry

    return {
        "granularities": list(GRANULARITIES),
        "dimensions": [_dim(dim) for dim in DIMENSIONS],
    }


@router.get("/yoy")
def get_yoy(
    window: str = Query(description="calendar window, e.g. 08-18:08-31"),
    repo: ReadRepo = Depends(get_repo),
):
    """Same-period year-over-year medians from the bulk conveyance history
    (back to ~1986) — e.g. the last two weeks of August across every year.
    Empty `years` when the bulk sales table hasn't been ingested."""
    try:
        start, end = parse_window(window)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    meta = repo.sales_meta()
    return {
        "window": {"start": start, "end": end},
        "extract_date": meta["extract_date"] if meta else None,
        "years": repo.yoy(start, end),
    }


@router.get("")
def get_trend(
    dimension: str = Query(default="overall"),
    group: str | None = Query(default=None),
    granularity: str = Query(default="sale_month"),
    repo: ReadRepo = Depends(get_repo),
):
    if dimension not in DIMENSIONS:
        raise HTTPException(400, f"unknown dimension {dimension!r}")
    if granularity not in GRANULARITIES:
        raise HTTPException(400, f"unknown granularity {granularity!r}")

    report = repo.trends()
    groups = report.get("dimensions", {}).get(dimension, {})
    # `overall` has a single implicit group; otherwise a group is required.
    if dimension == "overall":
        group = "all"
    elif group is None:
        raise HTTPException(400, f"dimension {dimension!r} requires a group")
    if group not in groups:
        raise HTTPException(404, f"no trend for {dimension}/{group}")

    return {
        "dimension": dimension,
        "group": group,
        "granularity": granularity,
        "months_back": report.get("months_back"),
        "generated_at": report.get("generated_at"),
        "trend": groups[group].get(granularity, []),
    }

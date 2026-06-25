"""Sales-trend endpoint.

Serves slices of the trend report that the daily refresh materializes (with a
recompute fallback in ReadRepo). One report covers every dimension (overall,
school, neighborhood, price_tier, sqft_band) and granularity (sale_biweek,
sale_month, sale_quarter, sale_year); the query params pick the slice.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from franklin_housing.trends import DIMENSIONS, GRANULARITIES

from ..deps import get_repo
from ..repo import ReadRepo

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/dimensions")
def list_dimensions(repo: ReadRepo = Depends(get_repo)):
    """Available dimensions, their group values, and granularities — lets the
    UI populate dropdowns without hardcoding what's present in this pull."""
    report = repo.trends()
    dims = report.get("dimensions", {})
    return {
        "granularities": list(GRANULARITIES),
        "dimensions": [
            {"key": dim, "groups": sorted(dims.get(dim, {}).keys())}
            for dim in DIMENSIONS
        ],
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

import statistics
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query

from franklin_housing import analyze
from franklin_housing.neighborhoods import name_for

from ..deps import get_repo
from ..repo import ReadRepo

router = APIRouter(prefix="/neighborhoods", tags=["neighborhoods"])


def _med(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.median(vals), 2) if vals else None


@router.get("")
def list_neighborhoods(months_back: int = Query(default=24, ge=1, le=120),
                       repo: ReadRepo = Depends(get_repo)):
    windowed = analyze.window(repo.records(), months_back=months_back)
    groups: dict[str, list] = defaultdict(list)
    for r in windowed:
        if r["nbhdcd"] and r["is_comp"]:
            groups[r["nbhdcd"]].append(r)
    out = [{
        "nbhdcd": nb,
        "name": name_for(nb),
        "n_sales": len(rows),
        "median_ppsf": _med([r["price_per_sqft"] for r in rows]),
        "median_price": _med([r["price"] for r in rows]),
    } for nb, rows in groups.items()]
    out.sort(key=lambda x: -x["n_sales"])
    return out


@router.get("/{nbhdcd}")
def neighborhood(nbhdcd: str, months_back: int = Query(default=24, ge=1, le=120),
                 recent: int = Query(default=25, ge=1, le=200),
                 repo: ReadRepo = Depends(get_repo)):
    windowed = analyze.window(repo.records(), months_back=months_back)
    rows = [r for r in windowed if r["nbhdcd"] == nbhdcd]
    if not rows:
        raise HTTPException(404, f"no sales in neighborhood {nbhdcd} for window")
    comps = [r for r in rows if r["is_comp"]]
    return {
        "nbhdcd": nbhdcd,
        "name": name_for(nbhdcd),
        "summary": analyze.summary(rows),
        "trend": analyze.trend(rows, by="sale_month"),
        "histogram": analyze.histogram(rows),
        "recent_sales": sorted(comps, key=lambda r: r["sale_date"] or "", reverse=True)[:recent],
        "scatter": [{"sqft": r["sqft"], "price": r["price"],
                     "price_per_sqft": r["price_per_sqft"], "address": r["address"],
                     "sale_date": r["sale_date"]} for r in comps],
    }

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_repo
from ..repo import ReadRepo
from ..service import find_parcel

router = APIRouter(prefix="/address", tags=["address"])

_FIELDS = ("parcelid", "address", "zip", "nbhdcd", "sqft", "beds", "baths", "year_built")


@router.get("/search")
def search(q: str = Query(min_length=2), limit: int = Query(default=10, ge=1, le=50),
           repo: ReadRepo = Depends(get_repo)):
    needle = q.strip().upper()
    hits = [r for r in repo.records() if r["address"] and needle in r["address"].upper()]
    # prefix matches (house number start) rank first, then by address length
    hits.sort(key=lambda r: (not r["address"].upper().startswith(needle), len(r["address"])))
    return [{k: r.get(k) for k in _FIELDS} for r in hits[:limit]]


@router.get("/{parcelid}")
def by_parcel(parcelid: str, repo: ReadRepo = Depends(get_repo)):
    rec = find_parcel(repo.records(), parcelid=parcelid)
    if not rec:
        raise HTTPException(404, "parcel not found")
    return rec

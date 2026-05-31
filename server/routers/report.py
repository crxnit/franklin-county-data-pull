from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_repo
from ..repo import ReadRepo
from ..service import build_report

router = APIRouter(tags=["report"])


@router.get("/report")
def report(address: str | None = Query(default=None),
           parcelid: str | None = Query(default=None),
           comps: int = Query(default=10, ge=1, le=50),
           months_back: int = Query(default=24, ge=1, le=120),
           repo: ReadRepo = Depends(get_repo)):
    if not address and not parcelid:
        raise HTTPException(400, "provide ?address= or ?parcelid=")
    result = build_report(repo, address=address, parcelid=parcelid,
                          comp_count=comps, months_back=months_back)
    if not result["subject"]["resolved"]:
        raise HTTPException(404, f"no parcel matched {address or parcelid!r}")
    return result

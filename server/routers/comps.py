from fastapi import APIRouter, Depends

from ..deps import get_repo
from ..models import CompsRequest
from ..repo import ReadRepo
from ..service import build_report

router = APIRouter(tags=["comps"])


@router.post("/comps")
def comps(req: CompsRequest, repo: ReadRepo = Depends(get_repo)):
    """Live re-estimate engine for the comp tuner. Shares build_report with the
    report endpoint, so the same subject yields the same anchor."""
    result = build_report(
        repo, parcelid=req.parcelid, address=req.address,
        subject_sqft=req.subject_sqft, beds=req.beds, baths=req.baths,
        year_built=req.year_built, nbhdcd=req.nbhdcd,
        comp_count=req.comp_count, size_band=req.size_band,
        months_back=req.months_back)
    return {"subject": result["subject"], "comps": result["comps"],
            "estimate": result["estimate"], "summary": result["neighborhood_summary"]}

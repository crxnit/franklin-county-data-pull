from fastapi import APIRouter, Depends

from ..deps import get_repo
from ..repo import ReadRepo

router = APIRouter(tags=["meta"])


@router.get("/meta")
def meta(repo: ReadRepo = Depends(get_repo)):
    return repo.meta()

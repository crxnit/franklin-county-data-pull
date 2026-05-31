"""Request/response schemas. Responses are plain dicts built from the
clean_records shape (FastAPI serializes them); only inputs are strictly typed."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompsRequest(BaseModel):
    parcelid: str | None = None
    address: str | None = None
    subject_sqft: int = Field(gt=0)
    beds: int | None = None
    baths: int | None = None
    year_built: int | None = None
    nbhdcd: str | None = None
    comp_count: int = Field(default=10, ge=1, le=50)
    size_band: float = Field(default=0.15, gt=0, le=1.0)
    months_back: int = Field(default=24, ge=1, le=120)

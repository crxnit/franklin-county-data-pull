"""Configuration for the Franklin County housing pull-and-analyze pipeline.

Everything that scopes *what* we pull and *how* we judge a sale lives here so the
target area / hygiene thresholds can be changed in one place.

Data-source note (verified 2026-05-30): we use the canonical Franklin County
Auditor hosting layer, NOT the Hilliard mirror named in the original spec. The
mirror leaves the entire CAMA/appraisal block (floor area, assessed value) null,
which makes $/sqft impossible. See CLAUDE.md for the full field-population audit.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

# --- ArcGIS endpoint -------------------------------------------------------

ENDPOINT = (
    "https://gis.franklincountyohio.gov/hosting/rest/services/"
    "ParcelFeatures/Parcel_Features/MapServer/0/query"
)

# Server caps each request at 10000 rows; stay well under it per page.
PAGE_SIZE = 2000

# Fields we pull. Names are the *canonical* layer names (longer than the
# mirror's 10-char-truncated names — e.g. RESFLRAREA_AG, TOTVALUEBASE,
# SITEADDRESS). VALID/CNVYNAME are null on this layer but pulled anyway so the
# optional enrichment step has a column to populate.
OUT_FIELDS = [
    "PARCELID",
    "SITEADDRESS",
    "ZIPCD",
    "SCHLDSCRP",
    "NBHDCD",
    "CLASSCD",
    "CLASSDSCRP",
    "SALEDATE",
    "SALEPRICE",
    "RESFLRAREA_AG",   # above-grade floor area -> $/sqft denominator
    "RESYRBLT",
    "ROOMS",
    "BEDRMS",
    "BATHS",
    "HBATHS",
    "STATEDAREA",      # legal acres (lot size)
    "ACRES",
    "TOTVALUEBASE",    # assessed total value -> sale-to-assessment ratio
    "LNDVALUEBASE",
    "BLDVALUEBASE",
    "X_COORD",
    "Y_COORD",
    "CNVYNAME",        # null on this layer; here for completeness/enrichment
    "VALID",           # null on this layer; populated only by enrich step
]

# The $/sqft denominator. Above-grade is the deliberate default (finished
# basements inflate total floor area).
SQFT_FIELD = "RESFLRAREA_AG"


@dataclass(frozen=True)
class Config:
    # --- target area ---
    school_district: str | None = "DUBLIN CSD"   # most meaningful boundary
    zips: tuple[str, ...] = ()                    # e.g. ("43016", "43017"); empty = ignore
    class_codes: tuple[str, ...] = ("510",)       # 510 = single-family dwelling
    cnvyname: str | None = None                   # subdivision (null on this layer; for future)
    nbhdcd: str | None = None                     # appraiser neighborhood code

    # --- time / price window ---
    months_back: int = 24
    saleprice_min: float = 1.0                    # exclude $0 / nominal placeholder rows

    # --- hygiene thresholds (sale-to-assessment ratio is the VALID proxy) ---
    # Ratio = SALEPRICE / TOTVALUEBASE. Arms-length sales cluster near ~1.0+;
    # values far outside this band are flagged (NOT dropped) for review.
    ratio_low: float = 0.50
    ratio_high: float = 3.0
    # Plausible residential $/sqft band; outside -> flagged.
    ppsf_low: float = 40.0
    ppsf_high: float = 700.0
    # A real arms-length sale almost never prices below this.
    arms_length_price_floor: float = 10_000.0

    # --- subject property (for comp generation); leave as placeholders ---
    subject_address: str | None = None            # e.g. "1234 SOME ST" (substring match)
    subject_nbhdcd: str | None = None
    subject_sqft: int | None = None
    subject_beds: int | None = None
    subject_baths: int | None = None
    subject_year_built: int | None = None

    # --- storage ---
    db_path: str = "data/franklin_housing.sqlite"

    def sale_cutoff(self, today: date | None = None) -> date:
        """First day of the window, `months_back` months before today."""
        today = today or date.today()
        m = today.month - 1 - self.months_back
        year = today.year + m // 12
        month = m % 12 + 1
        return date(year, month, 1)

    def where_clause(self, today: date | None = None, sales_only: bool = True) -> str:
        """Build the ArcGIS SQL `where` for the pull.

        Kept deliberately broad on attributes we clean later (we do NOT require
        RESFLRAREA_AG>0 here, so rows with missing sqft are still pulled and
        surfaced rather than silently excluded server-side).

        `sales_only=True` (CLI default) restricts to priced sales in the recent
        window. `sales_only=False` (webapp) pulls every parcel in the target
        area regardless of sale, so any address can be looked up; comp math then
        windows to recent sales in code (see analyze.window).
        """
        clauses = []
        if sales_only:
            clauses.append(f"SALEPRICE >= {self.saleprice_min}")
            cutoff = self.sale_cutoff(today).isoformat()
            clauses.append(f"SALEDATE >= DATE '{cutoff}'")
        if self.school_district:
            clauses.append(f"SCHLDSCRP = '{_q(self.school_district)}'")
        if self.zips:
            joined = ", ".join(f"'{_q(z)}'" for z in self.zips)
            clauses.append(f"ZIPCD IN ({joined})")
        if self.class_codes:
            joined = ", ".join(f"'{_q(c)}'" for c in self.class_codes)
            clauses.append(f"CLASSCD IN ({joined})")
        if self.cnvyname:
            clauses.append(f"CNVYNAME = '{_q(self.cnvyname)}'")
        if self.nbhdcd:
            clauses.append(f"NBHDCD = '{_q(self.nbhdcd)}'")
        return " AND ".join(clauses) if clauses else "1=1"

    def with_overrides(self, **kw) -> Config:
        return replace(self, **{k: v for k, v in kw.items() if v is not None})


def _q(value: str) -> str:
    """Escape single quotes for an ArcGIS SQL string literal."""
    return value.replace("'", "''")

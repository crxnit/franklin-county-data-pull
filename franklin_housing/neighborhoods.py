"""Appraiser-neighborhood code -> human-readable name lookup.

The county GIS layer publishes only `NBHDCD` (an 8-char appraiser-area *code*);
it has no neighborhood-name field. These names were derived by point-in-polygon
joining every Dublin parcel against the county "Subdiv and Condo Bndy" layer
(`Parcel_Features/MapServer/1`) and curating the dominant subdivision per code
(see `nbhd_names.csv` for parcels/purity/basis behind each name).

`nbhd_names.csv` is the editable source of truth — edit a `name` there and it
flows through clean -> API -> UI with no code change. Lives in the zero-dep core
so both the CLI and the server can use it; ships in the Docker image (the
Dockerfile copies `franklin_housing/`).
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

_CSV = Path(__file__).with_name("nbhd_names.csv")
_log = logging.getLogger(__name__)


def _load() -> dict[str, str]:
    names: dict[str, str] = {}
    try:
        with _CSV.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                code = (row.get("nbhdcd") or "").strip()
                name = (row.get("name") or "").strip()
                if code and name:
                    names[code] = name
    except (OSError, csv.Error) as e:
        # A missing or malformed table (this file is hand-editable) must not
        # crash import — degrade gracefully: callers fall back to the bare code.
        _log.warning("neighborhood name table unreadable (%s); using codes", e)
    return names


# code -> name (only codes with a non-empty curated name)
NBHD_NAMES: dict[str, str] = _load()


def name_for(code: str | None) -> str | None:
    """Curated neighborhood name for an `NBHDCD`, or None if unmapped."""
    if not code:
        return None
    return NBHD_NAMES.get(str(code).strip())


def label_for(code: str | None) -> str | None:
    """"Name (code)" for display, falling back to the bare code, or None."""
    if not code:
        return None
    code = str(code).strip()
    name = NBHD_NAMES.get(code)
    return f"{name} ({code})" if name else code

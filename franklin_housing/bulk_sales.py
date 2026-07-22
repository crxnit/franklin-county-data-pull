"""Monthly bulk sales-history ingest — the parcel 1:many conveyance history.

The GIS layer carries only the LATEST sale per parcel, but the Auditor also
publishes a monthly "Appraisal" extract at
https://apps.franklincountyauditor.com/outside_user_files/<year>/<YYYY-MM-DD> Appraisal/
whose Sales* files carry one row per CONVEYANCE back to ~1980 — including the
county's own VALID arms-length coding, which is null in every GIS feed
(verified 2026-07-22: Dublin 273- alone = 54k sale rows / 12.5k parcels, 94%
with >1 sale). This module downloads the Tab-Delimited bundle, filters to the
parcels we track, and rebuilds a `sales` table (+ `sales_meta`) alongside
`parcels` in the same cache DB — a true one-to-many join on PARCELID.

It also back-annotates parcels.VALID from the county coding (annotate_valid),
which the existing clean.py precedence then honors over the ratio proxy. The
annotation happens at read time (ReadRepo) because the daily GIS refresh
rewrites parcels rows with VALID null.

Per project ethos, suspect rows are FLAGGED, never dropped (bad dates, $0
transfers, multi-parcel conveyances all stay).

Stdlib only — lives in the zero-dep core.

Run:  python -m franklin_housing.bulk_sales   (defaults to data/webapp.sqlite)
"""

from __future__ import annotations

import csv
import io
import logging
import re
import shutil
import sqlite3
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .clean import _epoch_ms_to_date, _num

log = logging.getLogger(__name__)

BULK_ROOT = "https://apps.franklincountyauditor.com/outside_user_files/"
BUNDLE_NAME = "Tab-Delimited.zip"
_UA = {"User-Agent": "franklin-housing/1.0 (housing analysis; stdlib urllib)"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sales (
  parcelid     TEXT NOT NULL,   -- normalized GIS id; joins parcels.PARCELID
  parcelid_raw TEXT NOT NULL,   -- as published, e.g. 273-003074-00
  sale_date    TEXT,            -- ISO; NULL when unparseable (see flags)
  price        REAL,
  adj_price    REAL,
  valid_code   TEXT,            -- county coding verbatim ('' = uncoded)
  instrument   TEXT,
  instruno     TEXT,
  n_parcels    INTEGER,
  condsale     TEXT,            -- comma-joined CONDSALE_* reasons set to Y
  flags        TEXT,            -- hygiene flags (surfaced, never dropped)
  extract_date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bulk_sales_parcel ON sales (parcelid);
CREATE TABLE IF NOT EXISTS sales_meta (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ingested_at  TEXT NOT NULL,
  extract_date TEXT NOT NULL,
  source_url   TEXT NOT NULL,
  row_count    INTEGER NOT NULL
);
"""


# --- extract discovery ------------------------------------------------------

def _hrefs(url: str) -> list[str]:
    with urllib.request.urlopen(urllib.request.Request(url, headers=_UA),
                                timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    return re.findall(r'<A HREF="([^"]+)"', html, flags=re.I)

def latest_extract() -> tuple[str, str]:
    """(extract_date, folder_url) of the newest 'YYYY-MM-DD Appraisal' folder."""
    years = sorted(h.rstrip("/").rsplit("/", 1)[-1]
                   for h in _hrefs(BULK_ROOT) if re.search(r"/\d{4}/$", h))
    if not years:
        raise RuntimeError(f"no year folders under {BULK_ROOT}")
    dates = []
    for h in _hrefs(f"{BULK_ROOT}{years[-1]}/"):
        m = re.search(r"/(\d{4}-\d{2}-\d{2})%20Appraisal/$",
                      urllib.parse.quote(h, safe="/%"))
        if m:
            dates.append(m.group(1))
    if not dates:
        raise RuntimeError(f"no Appraisal folders under {BULK_ROOT}{years[-1]}/")
    d = max(dates)
    return d, f"{BULK_ROOT}{years[-1]}/{d}%20Appraisal/"


def _needed_members(names: list[str], districts: set[int]) -> list[str]:
    """The Sales*.txt bundle members whose district range overlaps ours
    (files are named Sales010.txt / Sales020-277.txt / Sales410-610.txt)."""
    out = []
    for n in names:
        m = re.fullmatch(r"Sales(\d+)(?:-(\d+))?\.txt", n)
        if not m:
            continue
        lo = int(m.group(1))
        hi = int(m.group(2) or m.group(1))
        if any(lo <= d <= hi for d in districts):
            out.append(n)
    return out


# --- parsing ----------------------------------------------------------------

def _norm_pid(raw: str) -> str:
    """Site/bulk id '273-003074-00' -> GIS id '273-003074'.

    Deliberately collapses EVERY suffix, so a non-00 sub-card's conveyances
    (e.g. a condo split '273-003074-01') attribute to the base parcel. Rare
    for the SFR (510) parcels we track; parcelid_raw is kept as the audit
    trail when a history row looks off."""
    return "-".join(raw.split("-")[:2])

def _parse_date(s: str) -> tuple[str | None, str | None]:
    """MM/DD/YYYY -> (iso, flag). Unparseable/implausible years are flagged."""
    try:
        d = datetime.strptime(s.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None, "bad_date"
    if not 1900 <= d.year <= date.today().year + 1:
        return None, "bad_date"
    return d.isoformat(), None

def parse_sales(fh, keep_ids: set[str], extract_date: str):
    """Yield normalized sale tuples for rows whose parcel we track."""
    for row in csv.DictReader(fh, delimiter="\t"):
        raw = (row.get("PARCEL ID") or "").strip()
        pid = _norm_pid(raw)
        if pid not in keep_ids:
            continue
        iso, flag = _parse_date(row.get("SALEDT") or "")
        flags = [flag] if flag else []
        price = _num(row.get("PRICE"))
        if not price:
            flags.append("zero_price")
        n_parcels = int(_num(row.get("NOPAR")) or 0)
        if n_parcels > 1:
            flags.append("multi_parcel")
        condsale = ",".join(
            k[len("CONDSALE_"):].lower() for k, v in row.items()
            if k.startswith("CONDSALE_") and (v or "").strip().upper() == "Y")
        if condsale:
            flags.append("conditional_sale")
        yield (pid, raw, iso, price, _num(row.get("ADJPRICE")),
               (row.get("VALID") or "").strip(), (row.get("INSTRUMENT") or "").strip(),
               (row.get("INSTRUNO") or "").strip(), n_parcels, condsale,
               ",".join(flags), extract_date)


# --- VALID mapping / annotation --------------------------------------------

def map_valid(code: str | None) -> str | None:
    """County coding -> clean.py's VALID convention ('Y'/'N'), abstaining (None)
    on uncoded or unrecognized values. Coding is '<num> - <label>' where 0 is a
    valid arms-length sale and any nonzero numeric code is an invalidity
    reason. Non-numeric codes (e.g. 'Y - WF FLAG') are unmapped — abstain."""
    head = (code or "").split("-", 1)[0].strip()
    if not head.isdigit():
        return None
    return "Y" if int(head) == 0 else "N"


def annotate_valid(rows: list[dict], conn: sqlite3.Connection) -> int:
    """Set row['VALID'] on raw parcel rows by matching each parcel's latest GIS
    sale (SALEDATE/SALEPRICE) to its coded bulk-sale row. Returns # annotated.
    No-ops (0) if the sales table doesn't exist yet. Matching mirrors
    enrich._match_transfer discipline: same parcel, price equal, date within
    10 days; abstain rather than mislabel."""
    try:
        cur = conn.execute("SELECT parcelid, sale_date, price, valid_code FROM sales"
                           " WHERE valid_code != ''")
    except sqlite3.Error:
        return 0
    by_pid: dict[str, list] = {}
    for pid, iso, price, code in cur:
        if iso:
            by_pid.setdefault(pid, []).append((date.fromisoformat(iso), price, code))
    n = 0
    for r in rows:
        d = _epoch_ms_to_date(r.get("SALEDATE"))
        price = r.get("SALEPRICE")
        if d is None or price is None:
            continue
        for sd, sp, code in by_pid.get(r.get("PARCELID"), ()):
            if sp == price and abs(sd - d) <= timedelta(days=10):
                v = map_valid(code)
                if v is not None:
                    r["VALID"] = v
                    n += 1
                break
    return n


# --- ingest -----------------------------------------------------------------

def _download_bundle() -> tuple[Path, str, str]:
    """Download the newest extract's bundle to a temp file the CALLER must
    unlink. Returns (bundle_path, extract_date, url). Cleans up after itself
    if the download dies partway."""
    extract_date, folder = latest_extract()
    url = folder + BUNDLE_NAME
    log.info("downloading %s (extract %s)", url, extract_date)
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=_UA), timeout=600) as r, tmp:
            shutil.copyfileobj(r, tmp)
    except BaseException:
        Path(tmp.name).unlink(missing_ok=True)
        raise
    return Path(tmp.name), extract_date, url


def ingest(db_path: str | Path = "data/webapp.sqlite",
           zip_path: str | Path | None = None,
           extract_date: str | None = None) -> dict:
    """Rebuild the `sales` table from the newest bulk extract (or a local
    bundle when zip_path is given — used by tests/offline runs)."""
    conn = sqlite3.connect(str(db_path))
    try:
        # Wait out the daily-refresh writer instead of failing with
        # "database is locked" if the two ever overlap (same as Cache).
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_SCHEMA)
        keep_ids = {r[0] for r in conn.execute('SELECT "PARCELID" FROM parcels')}
        if not keep_ids:
            raise RuntimeError(f"no parcels in {db_path} — seed it first")
        districts = {int(p[:3]) for p in keep_ids if p[:3].isdigit()}

        tmp = None
        if zip_path is None:
            tmp, extract_date, url = _download_bundle()
            zip_path = tmp
        else:
            url = str(zip_path)
            extract_date = extract_date or "local"

        try:
            rows, members = [], []
            with zipfile.ZipFile(zip_path) as zf:
                members = _needed_members(zf.namelist(), districts)
                for name in members:
                    with zf.open(name) as raw:
                        fh = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                        rows.extend(parse_sales(fh, keep_ids, extract_date))
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)

        # Rebuild atomically — the extract is a monthly snapshot, so replace
        # (idempotent) rather than accumulate.
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with conn:
            conn.execute("DELETE FROM sales")
            conn.executemany(
                "INSERT INTO sales (parcelid, parcelid_raw, sale_date, price,"
                " adj_price, valid_code, instrument, instruno, n_parcels,"
                " condsale, flags, extract_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                rows)
            conn.execute(
                "INSERT INTO sales_meta (ingested_at, extract_date, source_url,"
                " row_count) VALUES (?,?,?,?)", (ts, extract_date, url, len(rows)))
        parcels = len({r[0] for r in rows})
        coded = sum(1 for r in rows if r[5])
        log.info("ingested %d sales / %d parcels (%d county-coded) from %s",
                 len(rows), parcels, coded, ", ".join(members))
        return {"extract_date": extract_date, "sales": len(rows),
                "parcels": parcels, "coded_valid": coded, "members": members}
    finally:
        conn.close()


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db = argv[0] if argv else "data/webapp.sqlite"
    stats = ingest(db)
    print("bulk sales ingest:", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

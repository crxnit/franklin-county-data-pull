"""Optional true/derived VALID enrichment (default OFF).

The arms-length `VALID` flag is null across every Franklin County GIS feed, so
the pipeline's default hygiene is the sale-to-assessment ratio proxy (clean.py).
This module attempts to do better, with two backends:

  backend="property_site"  (default, real but fragile)
      Scrapes the public Auditor property site
      (https://property.franklincountyauditor.com/_web) — an ASP.NET WebForms
      "Vanguard" app. Flow per parcel:
        1. GET the parcel-ID search page (for a fresh __VIEWSTATE + session cookie)
        2. POST inpParid -> lands on the parcel's profile datalet (session-bound)
        3. GET the sales_summary datalet -> parse the Sales Summary / Transfer
           History table (Date | Grantee | Convey No | Inst Type | #Parcels | Price)
      The site exposes NO literal VALID code, so validity is DERIVED from the
      instrument type + parcel count + price.

  backend="mobile_api"  (currently inert)
      https://audr-api.franklincountyohio.gov — returns empty anonymously
      (credential-gated as of 2026-05-30). Kept as a hook.

Two hard safety guards make this trustworthy despite the site's quirks:
  * ADDRESS guard — the scraped parcel's address must match the GIS row
    (house number + first street word), else we abstain (`address_mismatch`).
  * SALE-MATCH guard — we only stamp VALID for the *specific* GIS sale, found
    in the transfer history by date (±`MATCH_DAYS`) and/or exact price. The
    public history lags GIS (a just-recorded sale may be absent), so when the
    GIS sale isn't present we ABSTAIN (`sale_not_posted`) rather than mislabel
    it with a different transfer's validity.

Nothing here ever crashes the pipeline; on any failure it abstains and logs.
"""

from __future__ import annotations

import html as _html
import http.cookiejar
import logging
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# -- property site ----------------------------------------------------------

SITE = "https://property.franklincountyauditor.com/_web"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
POLITE_DELAY = 0.6          # seconds between parcels (be kind to the county server)
MATCH_DAYS = 10             # GIS vs site sale-date tolerance

# Instrument-type codes that are NOT market sales (pure death / non-conveyance
# instruments that should never carry a real sale price). Everything else —
# warranty deeds (WD/GW/SW/LW), survivorship deeds (SU), fiduciary/executor
# deeds (FD/ED), etc. — is treated as a sale when single-parcel and priced.
#
# Calibrated empirically against 250 matched priced single-family Dublin sales
# (scripts/calibrate_instruments.py, 2026-05): instrument type proved to have
# essentially NO predictive power for non-arms-length status — every observed
# type (SU 68%, GW 28%, WD/FD/TD/ED/AM) had a median sale-to-assessment ratio
# ~1.2 and ZERO sales below 0.7. The single observed TD ("transfer on death")
# was at full market value, so TD/SO were REMOVED from the blacklist to avoid
# false-invalids. The genuine non-arms-length signal in the data is the
# MULTI-PARCEL conveyance (handled below via n_parcels), not the deed code.
NON_SALE_INSTRUMENTS = {"AF", "CT"}  # affidavit, certificate of transfer (death)

_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


class PropertySiteClient:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj))
        self.op.addheaders = [("User-Agent", UA)]

    def _open(self, url: str, data: dict | None = None) -> str:
        body = urllib.parse.urlencode(data).encode() if data else None
        with self.op.open(urllib.request.Request(url, data=body), timeout=self.timeout) as r:
            return r.read().decode("utf-8", "replace")

    @staticmethod
    def _hidden(html: str) -> dict:
        out = {}
        for m in re.finditer(r'<input[^>]+type="hidden"[^>]*>', html, re.I):
            tag = m.group(0)
            n = re.search(r'name="([^"]+)"', tag)
            v = re.search(r'value="([^"]*)"', tag)
            if n:
                out[n.group(1)] = v.group(1) if v else ""
        return out

    @staticmethod
    def _cells(tr: str) -> list[str]:
        return [_html.unescape(re.sub(r"<[^>]+>", " ", c)).strip()
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]

    def fetch(self, parcelid: str) -> dict:
        """Return {'address': str|None, 'transfers': [ {date,grantee,convey_no,
        inst_type,n_parcels,price}, ... ]}. Raises on transport failure."""
        # 1) search page -> viewstate + session cookie
        search_url = SITE + "/search/commonsearch.aspx?mode=parid"
        form = self._hidden(self._open(search_url))
        # 2) POST the parcel id (dashed GIS form works and maps 1:1 to the site
        #    parcel, e.g. 273-005244 -> site card 273-005244-00)
        form.update({"mode": "parid", "inpParid": parcelid,
                     "hdAction": "Search", "btSearch": "Search"})
        profile = self._open(search_url, form)
        address = self._parse_address(profile)
        # 3) sales_summary datalet (session-bound to the parcel just searched)
        sales_html = self._open(
            SITE + "/Datalets/Datalet.aspx?mode=sales_summary&sIndex=0&idx=1&LMparent=20")
        return {"address": address, "transfers": self._parse_transfers(sales_html)}

    @staticmethod
    def _parse_address(html: str) -> str | None:
        t = _html.unescape(re.sub(r"<[^>]+>", " ", html))
        m = re.search(r"(Location Address|Property Address|Site \(Property\) Address)\s+"
                      r"([0-9]{1,6}\s+[A-Z0-9 ]{2,40})", t)
        return m.group(2).strip() if m else None

    def _parse_transfers(self, html: str) -> list[dict]:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I)
        out = []
        for tr in rows:
            cc = self._cells(tr)
            if len(cc) < 6:
                continue
            date = self._parse_date(cc[0])
            if not date:
                continue
            price = self._parse_price(cc[5])
            n_parcels = self._parse_int(cc[4])
            out.append({
                "date": date,
                "grantee": cc[1],
                "convey_no": cc[2],
                "inst_type": cc[3].upper(),
                "n_parcels": n_parcels,
                "price": price,
            })
        return out

    @staticmethod
    def _parse_date(s: str):
        m = re.match(r"([A-Z]{3})-(\d{1,2})-(\d{4})", s.strip().upper())
        if m and m.group(1) in _MONTHS:
            return datetime(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)),
                            tzinfo=timezone.utc).date()
        return None

    @staticmethod
    def _parse_price(s: str):
        digits = re.sub(r"[^\d.]", "", s)
        return float(digits) if digits else None

    @staticmethod
    def _parse_int(s: str):
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else None


def derive_valid(transfer: dict, price_floor: float) -> str:
    """Map a transfer to 'Y' (arms-length market sale) or 'N'."""
    if (transfer.get("n_parcels") in (1, None)
            and (transfer.get("price") or 0) >= price_floor
            and transfer.get("inst_type") not in NON_SALE_INSTRUMENTS):
        return "Y"
    return "N"


def _addr_key(addr: str | None):
    """(house_number, first_street_word) — robust across LP/LOOP, RD/ROAD, etc."""
    if not addr:
        return None
    parts = addr.upper().split()
    nums = [p for p in parts if p.isdigit()]
    words = [p for p in parts if not p.isdigit()]
    return (nums[0] if nums else None, words[0] if words else None)


def _match_transfer(transfers: list[dict], sale_date, sale_price):
    """Find the transfer corresponding to the GIS sale, or None."""
    best = None
    for tr in transfers:
        price_ok = (sale_price is not None and tr["price"] is not None
                    and abs(tr["price"] - sale_price) < 1.0)
        date_ok = (sale_date is not None and tr["date"] is not None
                   and abs((tr["date"] - sale_date).days) <= MATCH_DAYS)
        if price_ok and (date_ok or sale_date is None):
            return tr
        if date_ok and best is None:
            best = tr            # date-only fallback
    return best


def enrich_valid(cache, backend: str = "property_site", limit: int | None = 25,
                 price_floor: float = 10_000.0) -> dict:
    """Populate cache.VALID for parcels, newest-sale first. Returns status counts.

    Defaults to a small `limit` because each parcel costs ~3 polite HTTP
    requests to the county server — enrich your comp set, not all 900 rows.
    """
    if backend == "mobile_api":
        return _enrich_mobile(cache, limit)

    rows = cache.load()
    # newest sales first so a capped run enriches the most relevant parcels
    rows.sort(key=lambda r: r.get("SALEDATE") or 0, reverse=True)
    stats = {"attempted": 0, "valid_y": 0, "valid_n": 0,
             "address_mismatch": 0, "sale_not_posted": 0, "error": 0}

    for r in rows[: limit or len(rows)]:
        pid = r.get("PARCELID")
        if not pid:
            continue
        stats["attempted"] += 1
        try:
            # Fresh session per parcel: the sales_summary datalet is bound to
            # the session's search-result pointer (sIndex=0&idx=1), so reusing
            # one session would return the first-searched parcel's history for
            # every parcel. A new cookie jar makes idx=1 the just-searched one.
            data = PropertySiteClient().fetch(pid)
        except Exception as exc:                      # transport / parse — abstain
            log.debug("enrich fetch failed for %s: %s", pid, exc)
            stats["error"] += 1
            time.sleep(POLITE_DELAY)
            continue

        # ADDRESS guard
        if _addr_key(data["address"]) != _addr_key(r.get("SITEADDRESS")):
            log.debug("address mismatch %s: gis=%r site=%r",
                      pid, r.get("SITEADDRESS"), data["address"])
            stats["address_mismatch"] += 1
            time.sleep(POLITE_DELAY)
            continue

        # SALE-MATCH guard
        sale_date = _epoch_to_date(r.get("SALEDATE"))
        sale_price = _to_float(r.get("SALEPRICE"))
        match = _match_transfer(data["transfers"], sale_date, sale_price)
        if not match:
            stats["sale_not_posted"] += 1
            time.sleep(POLITE_DELAY)
            continue

        valid = derive_valid(match, price_floor)
        cache.update_valid(pid, valid)
        stats["valid_y" if valid == "Y" else "valid_n"] += 1
        log.info("enriched %s: %s (%s $%s, %s parcel[s])", pid, valid,
                 match["inst_type"], match["price"], match["n_parcels"])
        time.sleep(POLITE_DELAY)

    if stats["valid_y"] + stats["valid_n"] == 0:
        log.warning("property-site enrichment stamped 0 parcels "
                    "(attempted %d; sale_not_posted=%d, address_mismatch=%d, error=%d). "
                    "Falling back to the ratio proxy.",
                    stats["attempted"], stats["sale_not_posted"],
                    stats["address_mismatch"], stats["error"])
    return stats


# -- mobile API backend (inert; kept as a hook) -----------------------------

def _enrich_mobile(cache, limit):
    api = "https://audr-api.franklincountyohio.gov"
    rows = cache.load()
    attempted = updated = 0
    for r in rows[: limit or len(rows)]:
        pid = r.get("PARCELID")
        if not pid:
            continue
        attempted += 1
        url = api + "/v1/parcels/ByParcelNumber?" + urllib.parse.urlencode(
            {"parcelNumber": pid})
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "application/json"})
            import json
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            results = payload.get("Results") or []
        except Exception:
            results = []
        if results:
            updated += 1   # extraction hook left for when access is granted
    log.warning("mobile_api enrichment updated %d/%d (gated source returns empty "
                "anonymously)", updated, attempted)
    return {"attempted": attempted, "updated": updated}


def _epoch_to_date(ms):
    if ms in (None, ""):
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date()


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

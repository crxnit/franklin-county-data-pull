"""One-time calibration: tally instrument types vs sale-to-assessment ratios.

Scrapes the property site for a few hundred *older* (already-posted) Dublin
sales, matches each to its GIS sale, and records the conveyance instrument type
alongside the GIS sale-to-assessment ratio (SALEPRICE / TOTVALUEBASE). The goal
is to learn empirically which instrument codes correlate with non-arms-length
sales, so the VALID-derivation blacklist in enrich.py can be calibrated rather
than guessed.

Streams every probed parcel to data/calibration_sample.csv (resumable-ish:
re-running re-scrapes, but the CSV is the durable artifact for re-tallying).

Run:  PYTHONPATH=. python3 scripts/calibrate_instruments.py
"""

import csv
import sqlite3
import time
from collections import defaultdict
from statistics import mean, median

from franklin_housing.enrich import (
    PropertySiteClient,
    _addr_key,
    _epoch_to_date,
    _match_transfer,
)

DB = "data/franklin_housing.sqlite"
OUT = "data/calibration_sample.csv"
TARGET_MATCHED = 250      # stop once we have this many matched sales
MAX_ATTEMPTS = 420        # hard cap on parcels probed
DELAY = 0.3               # politeness delay between parcels


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        'SELECT "PARCELID","SITEADDRESS","SALEDATE","SALEPRICE","TOTVALUEBASE" '
        'FROM parcels WHERE "SALEPRICE" > 0 AND "SALEDATE" IS NOT NULL'
    ).fetchall()
    # oldest sales first — most likely already posted to the public site
    rows = sorted(rows, key=lambda r: r["SALEDATE"])

    matched = []   # (inst_type, ratio, n_parcels, site_price, gis_price)
    attempts = 0
    status_counts = defaultdict(int)

    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["parcelid", "address", "gis_date", "gis_price", "assessed",
                    "ratio", "match_date", "inst_type", "n_parcels",
                    "site_price", "status"])

        for r in rows:
            if len(matched) >= TARGET_MATCHED or attempts >= MAX_ATTEMPTS:
                break
            attempts += 1
            pid = r["PARCELID"]
            sd = _epoch_to_date(r["SALEDATE"])
            sp = float(r["SALEPRICE"])
            assessed = r["TOTVALUEBASE"]
            ratio = (sp / float(assessed)) if assessed else None

            try:
                data = PropertySiteClient().fetch(pid)
            except Exception:
                status_counts["error"] += 1
                w.writerow([pid, r["SITEADDRESS"], sd, sp, assessed, "", "", "",
                            "", "", "error"])
                time.sleep(DELAY)
                continue

            if _addr_key(data["address"]) != _addr_key(r["SITEADDRESS"]):
                status_counts["address_mismatch"] += 1
                w.writerow([pid, r["SITEADDRESS"], sd, sp, assessed, "", "", "",
                            "", "", "address_mismatch"])
                time.sleep(DELAY)
                continue

            m = _match_transfer(data["transfers"], sd, sp)
            if not m:
                status_counts["sale_not_posted"] += 1
                w.writerow([pid, r["SITEADDRESS"], sd, sp, assessed, "", "", "",
                            "", "", "sale_not_posted"])
                time.sleep(DELAY)
                continue

            status_counts["matched"] += 1
            matched.append((m["inst_type"], ratio, m["n_parcels"], m["price"], sp))
            w.writerow([pid, r["SITEADDRESS"], sd, sp, assessed,
                        round(ratio, 3) if ratio else "", m["date"],
                        m["inst_type"], m["n_parcels"], m["price"], "matched"])
            fh.flush()
            time.sleep(DELAY)

    print(f"\nattempts={attempts}  " +
          "  ".join(f"{k}={v}" for k, v in sorted(status_counts.items())))
    tally(matched)


def tally(matched):
    by = defaultdict(list)
    for inst, ratio, n_parcels, site_price, _gis_price in matched:
        by[inst].append({"ratio": ratio, "n_parcels": n_parcels,
                         "price": site_price})

    print(f"\nmatched sales: {len(matched)}")
    print(f"{'inst':<5} {'n':>4} {'med_ratio':>9} {'mean_ratio':>10} "
          f"{'ratio<0.7':>9} {'multi_parcel':>12} {'med_price':>11}")
    print("-" * 70)
    for inst in sorted(by, key=lambda k: -len(by[k])):
        grp = by[inst]
        ratios = [g["ratio"] for g in grp if g["ratio"] is not None]
        low = sum(1 for x in ratios if x < 0.7)
        multi = sum(1 for g in grp if (g["n_parcels"] or 1) > 1)
        prices = [g["price"] for g in grp if g["price"]]
        print(f"{inst:<5} {len(grp):>4} "
              f"{(median(ratios) if ratios else 0):>9.3f} "
              f"{(mean(ratios) if ratios else 0):>10.3f} "
              f"{low:>4}/{len(ratios):<4} "
              f"{multi:>12} "
              f"{(median(prices) if prices else 0):>11,.0f}")


if __name__ == "__main__":
    main()

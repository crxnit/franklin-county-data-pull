# Franklin County (Dublin, OH) Housing Sales — pull & analyze

Pulls residential sales from the **Franklin County Auditor** parcel layer,
caches them locally in SQLite, and runs comparable-sales / price-per-square-foot
analysis — so you can price a home off the raw county data instead of Zillow.

Defaults: **Dublin City School District**, single-family (`CLASSCD 510`), sales
in the **last 24 months**, `SALEPRICE > 0`.

## Quick start

No dependencies required — pure Python 3.10+ standard library. (`matplotlib` is
optional, only for `--plots`.)

```bash
# 1) Confirm the source / fields with a tiny raw sample (prints raw JSON)
python -m franklin_housing --sample 5 --zip 43017

# 2) Full run: pulls (first time), caches, analyzes, writes data/cleaned_sales.csv
python -m franklin_housing

# 3) Comps for your house (seed by attributes and/or address substring)
python -m franklin_housing \
    --address "1234 SOMERSET" \
    --subject-sqft 2600 --beds 4 --baths 3 --year 1994 \
    --subject-nbhd 00136000 --comps 8 --plots

# Force a fresh pull (otherwise the local cache is reused)
python -m franklin_housing --refresh
```

## Data source

Canonical FCA hosting layer (layer 0 = Tax Parcel):

```
https://gis.franklincountyohio.gov/hosting/rest/services/ParcelFeatures/Parcel_Features/MapServer/0/query
```

> **Why not the Hilliard mirror?** The mirror named in the original spec
> (`maps.hilliardohio.gov/...`) serves the same schema but leaves the entire
> CAMA/appraisal block (`RESFLRAREA*`, `*VALUEBA*`) **null**, so $/sqft and
> assessment checks are impossible against it. This tool uses the canonical
> layer, which populates them. See `CLAUDE.md` for the field-population audit.

## What it computes

- **`price_per_sqft`** = `SALEPRICE / RESFLRAREA_AG` (above-grade floor area —
  finished basements don't inflate it).
- **`sale_to_assessment`** = `SALEPRICE / TOTVALUEBASE`.
- **Summary**: median/mean $/sqft, median/mean price, counts.
- **Trend**: median $/sqft and price by month.
- **Comps**: the N closest sales to your home by sqft / beds / baths / year,
  restricted to your appraiser neighborhood (`NBHDCD`) when known.
- **Distribution**: $/sqft histogram (ASCII, plus PNGs with `--plots`).

## Hygiene — flagged, never silently dropped

The arms-length **`VALID`** flag is **null in every county GIS feed**, so the
default arms-length test is a proxy:

- sale price below `arms_length_price_floor` → `below_price_floor`
- sale-to-assessment ratio outside `[ratio_low, ratio_high]` → `ratio_outlier`
- implausible $/sqft → `ppsf_outlier`; missing sqft/price → `missing_*`

Flagged rows stay in the dataset (with a `flags` column) and are excluded only
from the $/sqft *comp* aggregates. Thresholds live in `franklin_housing/config.py`.

### Optional VALID enrichment (`--enrich`)

Derives a real arms-length flag by scraping the public Auditor **property site**
(`property.franklincountyauditor.com`). The site exposes no literal VALID code,
so validity is derived from each transfer's **instrument type + parcel count +
price**: a single-parcel, non-zero conveyance that isn't a non-sale instrument
(affidavit `AF`, certificate of transfer `CT`) → `Y`, else `N`.

The derivation was **calibrated empirically** against 250 matched single-family
Dublin sales (`scripts/calibrate_instruments.py`): instrument type turned out to
carry almost no signal — survivorship deeds `SU` are 68% of sales and entirely
arms-length, and every observed type had a median sale-to-assessment ratio ~1.2
with none below 0.7. The real non-arms-length signal is the **multi-parcel
conveyance** (one price spanning several parcels, which distorts per-parcel
$/sqft) — those are marked `N`. Re-run the calibration script to re-tally.

```bash
python -m franklin_housing --enrich --enrich-limit 25   # scrapes 25 newest comps
python -m franklin_housing --enrich --enrich-backend mobile_api   # inert (gated)
```

It is **fragile by nature** and built with two safety guards so it never
mislabels a sale:

- **Address guard** — the scraped parcel's address must match the GIS row, else
  the parcel is skipped (`address_mismatch`).
- **Sale-match guard** — VALID is stamped only for the *specific* GIS sale,
  located in the transfer history by date (±10 days) / exact price. The public
  history **lags GIS** (a just-recorded sale often isn't posted yet), so recent
  sales typically come back `sale_not_posted` and are left to the ratio proxy
  rather than mislabeled.

Cost: ~3 HTTP requests per parcel (a fresh session each, with a polite delay),
so `--enrich-limit` defaults to 25 — enrich your comp set, not all ~900 rows.
The `mobile_api` backend is credential-gated (returns empty anonymously) and
kept only as a hook. See `franklin_housing/enrich.py`.

## Layout

```
franklin_housing/
  config.py   target area + hygiene thresholds + where-clause builder
  client.py   paginated ArcGIS REST client (urllib, retry/backoff)
  cache.py    SQLite store of raw pulls (+ pull metadata)
  clean.py    hygiene flags + computed $/sqft and sale-to-assessment ratio
  analyze.py  summary / trend / comps / distribution
  enrich.py   optional true-VALID enrichment (default off)
  cli.py      command-line entry point
```

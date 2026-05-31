# Task: Build a pull-and-analyze pipeline for Franklin County (Dublin, OH) housing sales

Build a Python tool that pulls residential sales data from the Franklin County Auditor parcel layer (via the Hilliard ArcGIS mirror), caches it locally, and runs comparable-sales / price-per-square-foot analysis for my area. I'm preparing to list my Dublin home and want to analyze the data myself rather than rely on Zillow.

## Data source

ArcGIS REST feature layer (Franklin County Auditor parcel data, served via Hilliard's mirror — this is the full countywide layer, not just Hilliard):

```
https://maps.hilliardohio.gov/arcgis/rest/services/Reference/Franklin_County_Auditor/MapServer/0/query
```

Key behaviors:
- Supports `where`, `outFields`, `orderByFields`, `returnDistinctValues`, server-side statistics, and pagination.
- `MaxRecordCount` is 10000 per request — paginate with `resultOffset` / `resultRecordCount` until exhausted.
- Request `f=json` (or `f=geojson` if you want geometry). Use `outSR=4326` if returning coordinates.
- Layer refreshes Mon–Fri ~7:00 PM ET. Treat data as recent but verify `LASTUPDATE`.

## Fields and their meaning

Sale transaction:
- `SALEPRICE` (double) — sale price (numerator)
- `SALEDATE` (date) — sale date (time filter)
- `VALID` (string) — arms-length validity flag. CRITICAL hygiene filter. Pull a sample of raw records FIRST to confirm the actual values (likely 'Y'/'N' but verify) before assuming.

Living area (denominator — choose deliberately):
- `RESFLRAREA` (int) — above-grade floor area. DEFAULT denominator for $/sqft.
- `RESFLRAR_1` (int) — below-grade floor area
- `RESFLRAR_2` (int) — total floor area. Do NOT use as default; finished basements inflate it.

Location / comp filtering:
- `SITEADDRES` — site address
- `ZIPCD` — ZIP (Dublin: 43016, 43017, parts of 43065)
- `CNVYNAME` — subdivision/condo name (best "same neighborhood" key)
- `NBHDCD` — appraiser neighborhood code (tightest comp grouping)
- `SCHLDSCRP` — school district description (filter for Dublin City School District — more meaningful than city boundary)
- `CLASSCD` / `CLASSDSCRP` — property class (isolate single-family residential)

House characteristics:
- `RESYRBLT` (year built), `ROOMS`, `BEDRMS`, `BATHS`, `HBATHS`, `COND` (condition), `GRADE` (quality grade), `BASEMENT`, `AIRCOND`, `FIREPLC`, `ACRES`, `STATEDAREA` (lot size)

Assessed value (for sale-to-assessment sanity checks):
- `TOTVALUEBA` (base total value), `LNDVALUEBA` (land), `BLDVALUEBA` (building)
- Sale-to-assessment ratio (`SALEPRICE / TOTVALUEBA`) is a quick tell for non-arms-length sales.

Geo:
- `X_COORD` / `Y_COORD` — for distance-based comps if wanted
- `LASTUPDATE` — record freshness

## Requirements

1. **Config-driven pull.** Parameterize the target area at the top (default: Dublin City School District, single-family residential, sales in the last 24 months, `SALEPRICE > 0`). Make ZIP / subdivision / school-district / date-range easy to change.

2. **Robust ArcGIS client.**
   - Paginate correctly via `resultOffset` until fewer than `resultRecordCount` rows return.
   - Handle HTTP errors, timeouts, and partial pages with retries and backoff.
   - URL-encode `where` clauses properly (date literals use ArcGIS syntax: `SALEDATE > DATE '2024-01-01'`).
   - Log how many records pulled per page and total.

3. **Local cache.** Write raw results to SQLite (and/or Parquet) so re-runs don't re-hit the API. Include a `--refresh` flag to force a re-pull. Store the pull timestamp.

4. **Cleaning / hygiene layer.**
   - Filter to valid arms-length sales (confirm `VALID` values empirically first).
   - Drop or flag rows with missing/zero `RESFLRAREA` or `SALEPRICE`.
   - Flag outliers (e.g. sale-to-assessment ratio far from 1.0, implausible $/sqft) rather than silently dropping — I want to see them.
   - Compute `price_per_sqft = SALEPRICE / RESFLRAREA` (above-grade default).

5. **Analysis outputs.**
   - Summary stats for the target area: median/mean $/sqft, median sale price, count, by month and by year.
   - Trend over time (monthly/quarterly median $/sqft and median price) to inform "is the market still near a top."
   - Comp set generator: given my parcel's `CNVYNAME` / `NBHDCD` / bed/bath/sqft/year-built, return the closest N comparable sales with their $/sqft.
   - Distribution view ($/sqft histogram, price vs. sqft scatter).

6. **Usability.** CLI with sensible flags. Print a clean summary table to stdout and write a CSV/Parquet of the cleaned comp set. Keep it modular (client / cache / clean / analyze) so I can extend it.

## First steps before writing the full pipeline

1. Hit the endpoint with a tiny query (`resultRecordCount=5`, my ZIP) and dump raw JSON so we can confirm field presence, the real `VALID` values, and date formatting.
2. Confirm my parcel appears: query `SITEADDRES LIKE '%<my street>%'`. (I'll supply my address — leave it as a placeholder/config value, don't hardcode.)
3. Note my `CNVYNAME` and `NBHDCD` from that record and use them to seed the comp query.

## Stack notes
- Python, `requests`, `pandas`, `sqlite3` (stdlib) or `duckdb`/Parquet — your call, keep deps light.
- Make it a clean repo I can drop into my existing tooling. Violations/outliers surfaced explicitly, not hidden.

Start with step 1 (the small sample pull) and show me the raw output before building the rest.

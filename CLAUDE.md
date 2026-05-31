# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Implemented and working (built 2026-05-30). The `franklin_housing/` package pulls, caches, cleans, and analyzes; `cc-housing-data-prompt.md` is the original spec. The **CLI core is zero third-party deps** — Python 3.10+ stdlib only (`urllib`, `sqlite3`, `csv`, `statistics`); `matplotlib` optional for `--plots`.

A **hosted webapp** (added 2026-05-31) wraps the same library: FastAPI backend in `server/` + React/Vite/Recharts SPA in `frontend/`. See **WEBAPP.md** for architecture, dev/run commands, the API contract, and deploy (`deploy/`). Key points: the webapp pulls ALL Dublin SFR parcels (`Config.where_clause(sales_only=False)`, ~13.7k) into `data/webapp.sqlite` so any address is lookup-able, and comp math windows to recent sales via `analyze.window()`; the county API is hit only by `server/jobs/refresh.py`; `analyze.price_estimate()` (the size-matched valuation) is the shared core, oracle-tested on the Whigham case (~$523K). Backend deps live in a project `.venv` (`server/requirements.txt`); tests `pytest server/tests franklin_housing/tests`; lint `ruff check` (config in `ruff.toml`).

## Goal

A Python CLI that pulls residential sales from the Franklin County (OH) Auditor parcel layer, caches it locally, and runs comparable-sales / price-per-square-foot analysis to help the owner price a Dublin home. The owner wants outliers and non-arms-length sales **surfaced, not silently dropped**.

## Commands

```bash
python -m franklin_housing --sample 5 --zip 43017   # step-1 raw JSON dump, then exit
python -m franklin_housing                           # pull (first run) + analyze; writes data/cleaned_sales.csv
python -m franklin_housing --refresh                 # force re-pull (else cache is reused)
python -m franklin_housing --address "1234 ST" --subject-sqft 2600 --beds 4 --baths 3 --year 1994 --comps 8
python -m franklin_housing --enrich                  # optional true-VALID lookup (currently no-op, see below)
python -m franklin_housing -v                        # INFO logging (per-page pull progress)
```

No build/lint/test tooling exists yet. Smoke-test by running the commands above; the cache lives at `data/franklin_housing.sqlite`.

## Architecture

Modular by concern (`franklin_housing/`), each independently extendable:

- **config.py** — `Config` dataclass (target area + hygiene thresholds), `where_clause()` builder, `OUT_FIELDS`, `SQFT_FIELD`. Change defaults here.
- **client.py** — `ArcGISClient`: paginated query via `resultOffset`, retry/backoff, treats HTTP-200 `error` payloads as failures.
- **cache.py** — `Cache`: SQLite, one row per `PARCELID` (this layer carries only the latest sale per parcel), plus a `pull_meta` table.
- **clean.py** — `clean_records()`: computes `price_per_sqft` + `sale_to_assessment`, attaches `flags` (never drops), decides `arms_length`/`is_comp`.
- **analyze.py** — summary, monthly `trend`, `comps` (similarity-ranked, neighborhood-restricted), `histogram`, optional `save_plots`.
- **enrich.py** — optional true-`VALID` enrichment (default off).
- **cli.py** — argparse entry; orchestrates pull→clean→analyze, prints tables, writes CSV.

## Data source

**Use the canonical Franklin County Auditor hosting layer** (verified 2026-05-30, layer 0 = "Tax Parcel", ~494k records):

```
https://gis.franklincountyohio.gov/hosting/rest/services/ParcelFeatures/Parcel_Features/MapServer/0/query
```

**Do NOT use the Hilliard mirror** (`maps.hilliardohio.gov/.../Franklin_County_Auditor/MapServer/0`) that the original spec named. It serves the same schema but **leaves the entire CAMA/appraisal block null** — `RESFLRAREA*`, `VALID`, all `*VALUEBA*` are 0-of-493,872 there, so $/sqft and assessment checks are impossible against it. The canonical hosting layer populates them.

- `MaxRecordCount` is 10000/request. Paginate with `resultOffset` / `resultRecordCount` until a page returns fewer rows than requested. `exceededTransferLimit: true` signals more pages.
- Request `f=json` (or `f=geojson` for geometry); set `returnGeometry=false` for data pulls (smaller payload). Coords (`X_COORD`/`Y_COORD`, geometry) are **State Plane Ohio South ft (wkid 102723)**, not lat/lon — pass `outSR=4326` if you need lat/lon.
- `SALEDATE` / `LASTUPDATE` return as **epoch milliseconds UTC** in `f=json`. In `where` clauses use ArcGIS literal syntax: `SALEDATE > DATE '2024-01-01'`. URL-encode `where`.
- Use `returnCountOnly=true` for cheap field-population / size probes.

### Field-name differences from the spec (canonical layer)

The spec's field names come from the truncated mirror. On the canonical layer the names are longer — **use these**:

| Purpose | Canonical field | Spec/mirror name |
|---|---|---|
| Above-grade floor area ($/sqft denominator) | `RESFLRAREA_AG` | `RESFLRAREA` |
| Below-grade / total floor area | `RESFLRAREA_BG` / `RESFLRAREA` | `RESFLRAR_1` / `RESFLRAR_2` |
| Assessed total / land / building value | `TOTVALUEBASE` / `LNDVALUEBASE` / `BLDVALUEBASE` | `TOTVALUEBA` / `LNDVALUEBA` / `BLDVALUEBA` |
| Site address | `SITEADDRESS` | `SITEADDRES` |

## Critical gotchas

- **`VALID` is null everywhere** — the arms-length flag is not published in any GIS feed (0 of 494k; distinct value = `[None]`). Default hygiene is the **sale-to-assessment ratio `SALEPRICE / TOTVALUEBASE`** proxy, plus a price floor. A real (fragile) `--enrich` backend (`enrich.py`) derives VALID by scraping the property site — see below.
- **Property-site scraper (`enrich.py`) hard-won facts:** it's an ASP.NET WebForms "Vanguard" app at `property.franklincountyauditor.com/_web`. Flow: GET `commonsearch.aspx?mode=parid` (viewstate + session cookie) → POST `inpParid` (dashed GIS id like `273-005244` maps 1:1 to the site card `…-00`) → GET `Datalets/Datalet.aspx?mode=sales_summary&sIndex=0&idx=1`. **Use a fresh session per parcel** — the datalet is bound to the session's result pointer (`idx=1`), so a reused session returns the first-searched parcel's history for everyone. No literal VALID column exists; derive it from `Inst Type` + `# Parcels` + `Sale Price`. **Calibrated empirically** (`scripts/calibrate_instruments.py`, n=250): instrument type has ~no predictive power — `SU` survivorship is 68% of sales and fully arms-length, every observed type sits at ratio ~1.2, and `TD` appeared at market — so the blacklist is only `{AF, CT}` (death/non-conveyance). The real non-arms-length signal is the **multi-parcel conveyance** (`n_parcels>1`), not the deed code. The public history **lags GIS**, so recent GIS sales are often absent — match the specific sale by date(±10d)/price and abstain (`sale_not_posted`) rather than mislabel.
- **Mobile API** (`audr-api.franklincountyohio.gov`) is credential-gated — returns `TotalCount:0` anonymously. Inert hook only.
- **`CNVYNAME`, `COND`, `GRADE` are also null** on this layer. `NBHDCD` (appraiser neighborhood) is populated and is the tightest comp key available. Subdivision boundaries exist as a separate spatial layer (`Parcel_Features/MapServer/1`, "Subdiv and Condo Bndy") if a subdivision key is needed — spatial join, not an attribute.
- **$/sqft denominator:** default to `RESFLRAREA_AG` (above-grade, ~419k populated). `RESFLRAREA` (total) and `RESFLRAREA_BG` are null here anyway.
- **Comp grouping keys**, tightest first: `NBHDCD` > `SCHLDSCRP` (e.g. `'DUBLIN CSD'` — more meaningful than city/ZIP). Isolate single-family via `CLASSCD='510'`.
- The owner's home address is config/placeholder — never hardcode it.

## Required first step

Before building the full pipeline: hit the endpoint with a tiny query (`resultRecordCount=5`, owner's ZIP), dump raw JSON, and confirm field presence, real `VALID` values, and date formatting. Show that raw output before writing the rest.

## CLI / cache behavior

- `--refresh` flag forces a re-pull instead of using cache; store the pull timestamp.
- Print a clean summary table to stdout; write a cleaned comp-set CSV/Parquet.
- Log records pulled per page and total.

## Session log — 2026-05-31: hosted webapp build

State: webapp **complete and verified at every layer** — `price_estimate` oracle, 10 pytest passing, ruff clean, local uvicorn+SPA, and the production Docker container (built via Colima; authed report smoke returns the Whigham $522,732 anchor). All 8 build tasks done.

Decisions made this session:
- Stack: **FastAPI + React/Vite/Recharts**, hosted, **gated by a shared secret** (`FH_AUTH_SECRET`; no user accounts). SPA uses JSX (not TS) to keep the toolchain lean.
- Webapp data = **all Dublin SFR parcels** (`where_clause(sales_only=False)`, ~13.7k) so any address is lookup-able; comp math windows to recent sales via `analyze.window()`. Stored in `data/webapp.sqlite` (separate from the CLI's `data/franklin_housing.sqlite`).
- County API hit **only** by `server/jobs/refresh.py` (daily host-cron); requests serve read-only from SQLite (WAL) via `ReadRepo`, memoized on `pull_meta` id.
- Enrichment worker, ETag response-cache, and area-broadening were deliberately **deferred to fast-follows** (v1 uses the ratio proxy; `valid_basis: "ratio_proxy"`).
- Docker: single hardened container; **matplotlib excluded** from the server image (Recharts renders charts) — `franklin_housing.save_plots` stays CLI-only.

Known issues / TODOs:
- Bundle is ~553 kB (Recharts) — fine for v1; code-split later if needed.
- `_mount_spa` catch-all serves index for unknown paths but isn't exercised by tests.
- Backend runtime deps live in `.venv` (`server/requirements.txt`); the CLI core remains zero-dep.

Next steps / open questions:
- Wire the JJOC `ci-cd-pipeline` skill to a real VPS (needs server/domain details).
- Fast-follows: throttled true-VALID enrichment worker surfaced in the UI; ETag/Cache-Control on hot endpoints; optional broadening beyond Dublin CSD (switch to per-neighborhood lazy cleaning + FTS5 if going all-Franklin ~291k).
- Env note: Docker here runs via **Colima** (`colima start`), not Docker Desktop.

See **WEBAPP.md** (dev/run, API contract) and **deploy/README.md** (hosting).

## Session log — 2026-05-30: frontend UI/QA pass + GitHub push

State: ran `/ui-qa-review` over `frontend/` and **resolved every finding** (1 High, 10 Medium, 9 Low) in three phases. Production build (`npm run build` in `frontend/`) passes; CSS shrank slightly after the dead-rule prune. Merged to `main` (ff) and pushed.

Changes made:
- **a11y (the High + most Mediums):** `AddressSearch` now a real combobox — keyboard nav (arrows/Enter/Esc), `role=listbox/option`, `aria-activedescendant`, and labelable via new `id`/`ariaLabel` props; all view `<label>`s associated to inputs via `htmlFor`/`id`; password gate input got `aria-label`/`autoComplete`.
- **New `frontend/src/theme.js`** — single source for Recharts colors (`COLORS`, mirrors CSS `:root`) + shared `TOOLTIP_STYLE`; `charts.jsx` no longer hardcodes/duplicates the palette. Recharts can't read CSS vars, so theme.js and `styles.css :root` must be kept in sync by hand.
- **Render safety:** optional-chained reachable null derefs (`EstimateCard` anchor, `ReportView` band) and falsy-`0` chart guards.
- **Cleanup:** removed dead code (`usd0`, `.good`/`--good`, orphaned `a{}`/`:disabled` CSS, unused `getToken` import); `CompTunerView` now coerces `subject_sqft` at the handler (consistent numeric form state) and drops `address` from the request body; `App.jsx` `VIEWS` stores component refs not pre-instantiated elements; `api.js` query limits hoisted to named constants.

Repo: now pushed to **private GitHub repo `crxnit/franklin-county-data-pull`** (remote `origin`, `main` tracks `origin/main`). First time this project had a remote.

Open: ~555 kB Recharts bundle still unsplit (pre-existing TODO, untouched). No new TODOs.

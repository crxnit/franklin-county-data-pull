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
- ~~Wire the JJOC `ci-cd-pipeline` skill to a real VPS~~ **DONE 2026-05-31** — live at https://7518.jjocapps.com (see session log below).
- Fast-follows: throttled true-VALID enrichment worker surfaced in the UI; ETag/Cache-Control on hot endpoints; optional broadening beyond Dublin CSD (switch to per-neighborhood lazy cleaning + FTS5 if going all-Franklin ~291k).
- Env note: Docker here runs via **Colima** (`colima start`), not Docker Desktop.

See **WEBAPP.md** (dev/run, API contract) and **deploy/README.md** (hosting).

## Session log — 2026-05-31: deployed the webapp (JJOC push-to-deploy)

State: **LIVE at https://7518.jjocapps.com** — password-gated, valid LE cert, 13,667 Dublin SFR parcels seeded, daily refresh cron (07:00 UTC). Push-to-deploy pipeline fully green end-to-end.

Pipeline (files added): `.github/workflows/{ci,deploy}.yml`, `.githooks/pre-push` (ruff+pytest; activate with `git config --local core.hooksPath .githooks`), `.trivyignore`, `deploy/vps-deploy.sh`, `deploy/traefik/7518.jjocapps.com.yml`. Flow: push `main` → ruff+pytest → build+push **linux/arm64** to GHCR → Trivy HIGH/CRITICAL → locked-down SSH → `deploy.sh` (sed-pins `:sha-<short>`, compose pull+up) → `/api/health` smoke.

VPS: `webproxy.ai.jjocllc.com:4321`, user `john` (passwordless sudo, NOT in docker group → use `sudo`). App dir `/srv/portal-apps/franklin-housing` (root:root 0750 — `sudo` to cd). `FH_AUTH_SECRET`/`FH_CORS_ORIGINS` in root-owned `.env` (mode 0600). GHCR pull auth already present on the host (other crxnit apps). Deploy key `~/.ssh/franklin-housing-deploy` (command-restricted in authorized_keys + sudoers `franklin-housing-deploy`); lockdown verified (no shell, injection rejected). GH secrets set: `VPS_HOST/PORT/SSH_KEY/KNOWN_HOSTS`.

Three gotchas hit (now fixed — see memory `deploy-pipeline.md`):
- **arm64 build hung ~1h** under QEMU on the Node/Vite stage. Fix: `FROM --platform=$BUILDPLATFORM node:20-alpine` for the web stage (npm/Vite run native amd64; dist/ is arch-independent). Build → ~75s.
- **Actions blocked** (every job fails ~2s, no steps/logs) = Free-tier private-repo minutes/spending-limit exhausted. Fix: made the repo **PUBLIC** (Actions free; app stays gated). Confirmed no secrets in git first. *(Repo was private before this session — flip back only after raising the Actions limit.)*
- **Traefik on this VPS uses the FILE provider, not docker** → `traefik.*` compose labels are silently ignored; container was healthy but Traefik served its default self-signed cert. Fix: dynamic route YAML in `/srv/portal/traefik/dynamic/` (repo copy at `deploy/traefik/7518.jjocapps.com.yml`) → Host `7518.jjocapps.com` → `franklin-housing-app-1:8000` on the `traefik` net, TLS `letsencrypt` (HTTP-01). Compose keeps `traefik` network membership but no labels.

Decisions: no backups (`webapp.sqlite` is a derived cache the refresh job rebuilds). Oracle smoke confirmed live: authed `/api/report?address=7518+whigham+ct` → anchor **$522,732**.

Open: repo is now public (revisit if privacy wanted); gate secret is a random base64 string — rotate via VPS `.env` + `docker compose up -d app` if a typeable one is preferred.

## Session log — 2026-05-30: frontend UI/QA pass + GitHub push

State: ran `/ui-qa-review` over `frontend/` and **resolved every finding** (1 High, 10 Medium, 9 Low) in three phases. Production build (`npm run build` in `frontend/`) passes; CSS shrank slightly after the dead-rule prune. Merged to `main` (ff) and pushed.

Changes made:
- **a11y (the High + most Mediums):** `AddressSearch` now a real combobox — keyboard nav (arrows/Enter/Esc), `role=listbox/option`, `aria-activedescendant`, and labelable via new `id`/`ariaLabel` props; all view `<label>`s associated to inputs via `htmlFor`/`id`; password gate input got `aria-label`/`autoComplete`.
- **New `frontend/src/theme.js`** — single source for Recharts colors (`COLORS`, mirrors CSS `:root`) + shared `TOOLTIP_STYLE`; `charts.jsx` no longer hardcodes/duplicates the palette. Recharts can't read CSS vars, so theme.js and `styles.css :root` must be kept in sync by hand.
- **Render safety:** optional-chained reachable null derefs (`EstimateCard` anchor, `ReportView` band) and falsy-`0` chart guards.
- **Cleanup:** removed dead code (`usd0`, `.good`/`--good`, orphaned `a{}`/`:disabled` CSS, unused `getToken` import); `CompTunerView` now coerces `subject_sqft` at the handler (consistent numeric form state) and drops `address` from the request body; `App.jsx` `VIEWS` stores component refs not pre-instantiated elements; `api.js` query limits hoisted to named constants.

Repo: now pushed to **private GitHub repo `crxnit/franklin-county-data-pull`** (remote `origin`, `main` tracks `origin/main`). First time this project had a remote.

Open: ~555 kB Recharts bundle still unsplit (pre-existing TODO, untouched). No new TODOs.

## Session log — 2026-06-11: data refresh + snapshot/diff tooling

Refreshed both local caches from the county API (webapp.sqlite 13,667→13,668 parcels; CLI franklin_housing.sqlite re-pulled, 898 comps) — current through sale date 2026-06-10.

Added before/after diff tooling so refreshes report a true added/removed/changed report (a refresh replaces rows in place, so a baseline copy is required):
- **`franklin_housing/snapshot.py`** (stdlib-only) — `snapshot_db()` / `snapshot_path()`; backs a DB up to `data/snapshots/<stem>.baseline.sqlite` via the sqlite backup API. Lives in the **zero-dep core** (next to `cache.py`) so both the CLI and the server can call it without `franklin_housing` depending on `server` (wrong direction) — and it still ships in the image (Dockerfile copies `franklin_housing/`).
- **`server/jobs/refresh.py`** (webapp, upsert) snapshots before `cache.save()` (only on a successful, non-empty pull). **`franklin_housing/cli.py`** (`--refresh`, clear+save) snapshots before `cache.clear()`. Both wrap it in try/except — a snapshot failure is logged, never blocks the refresh.
- **`scripts/db_diff.py`** — `snapshot` (manual baseline for both DBs) and `diff` (added/removed/changed by PARCELID; itemizes new/re-priced sales via SALEDATE-or-SALEPRICE deltas, tallies other field changes). Imports the shared `franklin_housing.snapshot` so writer/reader agree on the baseline path.
- `data/snapshots/` is gitignored (`*.sqlite`). Verified end-to-end: both refresh paths log the baseline line; clean diff = 0; positive test (perturbed baseline) surfaces price-only + valuation changes; real CLI `--refresh` diff caught +3 new parcels (898→901, 24-mo window); ruff clean; 8 server tests pass.

Workflow: `python -m server.jobs.refresh` (or `python -m franklin_housing --refresh`) then `python -m scripts.db_diff diff`.

Also (2026-06-12): pushed the above to `main` (live deploy green, oracle health OK), plus two infra fixes:
- **Pre-push hook** (`.githooks/pre-push`): ran `.venv/bin/pytest` directly, which died on a stale console-script shebang after the repo moved paths (`bad interpreter`). Fixed to `.venv/bin/python -m pytest` (path-independent, like the native ruff binary). Ruff was unaffected because it's a native binary, not a shebang script.
- **GitHub Actions Node 20 deprecations** — bumped all flagged actions to current Node 24-native majors: checkout v4→v6, setup-python v5→v6, docker/login-action v3→v4, ssh-agent v0.9.0→v0.10.0, docker setup-qemu/buildx v3→v4, metadata v5→v6, build-push v6→v7 (trivy@v0.36.0 already latest). Removed the `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` env from both workflows — it forced Node 24 but never suppressed the annotation, and was masking that the docker actions were still Node 20 (removing it exposed them; they're now bumped). Verified: full pipeline green on the new versions, zero deprecation annotations remaining (only a harmless transient binfmt cache-reservation notice).

## Session log — 2026-06-17: local data refresh + how to check the live DB

Refreshed both **local** caches from the county API (current through sale date 2026-06-16). No code changes; working tree clean (refresh only writes gitignored `data/`).
- webapp.sqlite: 13,668 parcels; diff = 49 changed rows (38 new/changed sales incl. fresh 2026-06-16 sales like 3273 RAVELLO DR $1.15M; several `$0` non-market transfers), 10 SITEADDRESS fixes, 2 valuation tweaks. 0 added/removed.
- CLI franklin_housing.sqlite: 901 comps, 5-in/5-out of the rolling 24-mo window. `$/sqft` still clusters $202–300.
- Note: `python` isn't on PATH here — use `.venv/bin/python` for `server.jobs.refresh` / `franklin_housing --refresh` / `scripts.db_diff`.

**How to check when the LIVE DB (7518.jjocapps.com) was last updated** — it's rebuilt by the daily 07:00 UTC refresh cron, independent of any local refresh. Three ways, all reading the same `pull_meta` row:
- `GET /api/meta` (auth-gated) → `last_pull.pulled_at`; every `/api/report` also carries it as `data_as_of`. Token: `FH_AUTH_SECRET` from the VPS `.env`. No-SSH: `curl -s https://7518.jjocapps.com/api/meta -H "Authorization: Bearer $FH_AUTH_SECRET" | jq`.
- Over SSH, query the DB in the container. **Gotcha: the hardened image has no `sqlite3` CLI** — use the stdlib python instead, and the live DB path is **`/data/webapp.sqlite`** (not `/app/data/`):
  ```
  ssh -p 4321 john@webproxy.ai.jjocllc.com "sudo docker exec franklin-housing-app-1 python -c \"import sqlite3; print(sqlite3.connect('/data/webapp.sqlite').execute('SELECT pulled_at,row_count FROM pull_meta ORDER BY id DESC LIMIT 1').fetchone())\""
  ```
- Verified live this session: `pulled_at = 2026-06-17T07:00:16+00:00`, 13,667 parcels — cron healthy. (Live 13,667 vs local 13,668 is normal independent-pull drift.)

## Session log — 2026-06-25: sales-trend analysis, regenerated on every pull

Added a full sales-trend feature across CLI + webapp, built on the **existing** `analyze.trend`/`analyze.window` (unchanged) via one shared zero-dep engine. Every data-pull path now (re)produces trends, so they're always current as of the latest pull. Tests green (22 pytest), ruff clean, frontend builds.

- **`franklin_housing/trends.py`** (new, stdlib-only core) — `GRANULARITIES` (`sale_biweek`/`sale_month`/`sale_quarter`/`sale_year`), `price_tier`/`sqft_band` segment helpers, `DIMENSIONS` (overall, school, neighborhood, price_tier, sqft_band), `build_report(records, months_back=24, today=None)` → nested `{dimensions:{dim:{group:{granularity:[{period,n,median_ppsf,median_price}]}}}}`, and `flatten()` → long-format rows. Trends are comps-only (inherited from `analyze.trend`); windows once via `analyze.window`.
- **Bi-weekly bucket**: added `sale_biweek` to `clean.clean_records` — a 14-day **block-start ISO date** anchored on Monday `1970-01-05` (`_biweek_start`), so labels sort chronologically and `analyze.trend(by="sale_biweek")` works with no changes to `analyze`.
- **CLI** (`cli.py`): every run writes `data/sales_trends.json` (full) + `data/sales_trends.csv` (flat) next to `cleaned_sales.csv` via `_write_trends()`.
- **Server materialization**: `cache.py` got a `trend_cache(pull_id PK, computed_at, report_json)` table + `latest_pull_id()`/`save_trends()`/`load_trends()` (and `clear()` wipes it). `server/jobs/refresh.py` materializes the report after `cache.save()`, keyed on the new pull id, wrapped in try/except (a trend failure never blocks the refresh — same discipline as the snapshot step).
- **API**: `server/routers/trends.py` → `GET /api/trends/dimensions` (UI discovery) and `GET /api/trends?dimension=&group=&granularity=`. `ReadRepo.trends()` reads the materialized blob memoized on `pull_meta.id`, **falling back** to `build_report(self.records())` when the table is empty/stale. Registered in `main.py`.
- **Frontend**: new `TrendAnalysisView.jsx` ("Sales trends" tab in `App.jsx`) with Breakdown/Group/Granularity dropdowns; `TrendChart` extended with optional `title` + `showPrice` (second right-axis median-price line) — backward compatible with the NeighborhoodView call. `api.trend`/`api.trendDimensions` added.

Gotcha hit (fixed): **`ReadRepo.trends()` deadlocked** — it held the non-reentrant `self._lock` and then called `self.records()`, which re-acquires the same lock (single API test hung forever). Fix: compute the records() fallback *before* taking `_lock`; only the memo assignment is locked. Mirror this if adding more memoized repo methods.

Verified end-to-end: CLI artifacts (25 monthly rows, all 5 dims, 901 comps); materialization writes `trend_cache` for pull_id 4 and `ReadRepo.trends()` serves it (54 biweekly blocks); `/api/trends` slices match `/api/neighborhoods/{nbhdcd}` on shared months; `npm run build` clean. Note: `python` isn't on PATH — use `.venv/bin/python`. Not yet committed/deployed.

## Session log — 2026-06-25: neighborhood code→name mapping

Added human-readable neighborhood names. The county GIS layer publishes only `NBHDCD` (an 8-char appraiser-area **code**, alias "Appr. Neigh Code") — there is **no neighborhood-name field anywhere in any feed** (verified against the layer's field list; `NBHDCD` carries no coded-value domain either). Names were derived, not published.

- **Derivation (one-time, scripted):** point-in-polygon join of all 13,566 geocoded Dublin parcels against the county **"Subdiv and Condo Bndy"** layer (`Parcel_Features/MapServer/1`, polygons, same wkid 102723 as `X_COORD`/`Y_COORD`). 99% of parcels matched a subdivision (1,806 exterior rings). Collapsing subdivision *sections* (`SEC 1`/`PH 2`/`PT 4`) to base names, **39 of 64 codes are ≥80% a single named subdivision**; the rest span a coherent family (`cluster`) or genuinely distinct neighborhoods (`mixed`, given a compound `A / B` label). Pure stdlib (urllib + ray-casting PIP); join script was throwaway (scratchpad), not committed.
- **`franklin_housing/nbhd_names.csv`** (new, checked-in **source of truth**) — 64 rows: `nbhdcd,name,parcels,purity_pct,basis,notes`. `basis ∈ {clean,cluster,mixed,unmapped}` flags trust per row. 62 named; the 2 single-parcel junk codes (`X0103000`,`00800000`) left blank → fall back to the bare code. **Edit a `name` here and it flows through clean→API→UI with no code change.**
- **`franklin_housing/neighborhoods.py`** (new, zero-dep core) — loads the CSV at import via `Path(__file__).with_name(...)`; `name_for(code)` / `label_for(code)` ("Name (code)"). Missing CSV is non-fatal (returns None). Lives in the core (next to `clean.py`) so CLI + server share it; ships in the image (Dockerfile copies `franklin_housing/`).
- **Wiring:** `clean.clean_records` attaches `nbhd_name` to every record (next to `nbhdcd`). `server/routers/neighborhood.py` adds `name` to both list + detail responses. `server/routers/trends.py` `/dimensions` adds a `labels` map for the **neighborhood** dimension only (group values stay the codes; labels are display-only, computed live via `name_for` — no trend-cache regen needed). Frontend shows `Name (code)`: Neighborhoods dropdown, Sales-trends group dropdown + chart title, and the address Report's "Neighborhood" row (reuses the already-fetched `nbhd.name`).

Verified: 22 pytest pass, ruff clean, `npm run build` clean; end-to-end against local `webapp.sqlite` the neighborhood list renders names (e.g. `Dublinshire / Wyndham Village (00111000) — 80 sales`). Note: `python` isn't on PATH — use `.venv/bin/python`.

**Shipped live** across three commits (all CI+Deploy green; live at 7518.jjocapps.com — names show immediately, applied at read time from the image-baked CSV, no refresh needed):
- `feat` — the feature above.
- `refactor` (quality-review follow-up) — **duplicate-name fix:** three NBHDCD pairs share a name (`Shannon Park` = 00117000/00140000; `Wyandotte Woods` = 00120000/00120001; `Riverside Green South` = 02614000/02610000), so the trends group dropdown labeled by name-only rendered indistinguishable options. Fix: the `/trends/dimensions` `labels` map now uses `label_for` ("Name (code)") instead of `name_for`, disambiguating them (and putting the previously-unused `label_for` to work). Also extracted the duplicated `"Name (code)"` formatting into `frontend/src/format.js` `nbhdLabel(name, code)`.
- `harden` (security-review follow-up) — `neighborhoods._load()` ran at import catching only `OSError`; a malformed CSV (`csv.Error`) would propagate and crash `franklin_housing` import (server + CLI down). Since `nbhd_names.csv` is hand-editable, broadened the catch to `(OSError, csv.Error)` + a `logging.warning`, degrading to bare codes instead of failing startup. Tested: malformed CSV → warns, returns {}, no raise.

Open: none specific to this feature. Future tweaks to a name = edit `franklin_housing/nbhd_names.csv` and push (no data re-pull). The 25 `cluster`/`mixed`-basis codes (purity <80% in the CSV) are the rows most worth a human eyeball if a name ever looks off.

## Session log — 2026-06-27: local data refresh

Refreshed both **local** caches from the county API (current through sale date 2026-06-26). No code changes; working tree clean (refresh only writes gitignored `data/`). Standard workflow: `.venv/bin/python -m server.jobs.refresh` + `... -m franklin_housing --refresh`, then `... -m scripts.db_diff diff`.
- webapp.sqlite: 13,668 → 13,672 parcels (+4). 57 parcels with a new/changed sale (e.g. 2472 Dunstan Dr $449,900, 4779 Belfield Ct $799,900, 6482 Ringsend Ct $769,500; several `$0` non-market transfers), 266 SITEADDRESS fixes, 2 valuation tweaks. Trends materialized for pull #5.
- CLI franklin_housing.sqlite: 901 → 923 comps (+22), 24-mo window; 2 newly-priced comps (4779 Belfield Ct $799,900, 2218 Otter Ln $446,000). `$/sqft` still clusters $202–300; June 2026 median ~$268/sqft / $569K.
- Reminder: this is **local only**; the live site rebuilds independently via the 07:00 UTC refresh cron.

## Session log — 2026-06-28: mobile usability retrofit (shipped live)

Ran `/mobile-usability-audit` over `frontend/` then implemented the plan across all phases. **Shipped live** (commit `4d14e52`, CI+Deploy green, live bundle hash confirmed at 7518.jjocapps.com). Mobile changes apply on container swap — no data re-pull. Desktop (≥641px) is byte-identical: **every** layout rule lives in one `@media (max-width: 640px)` block in `frontend/src/styles.css`.

- **Audit finding:** plain React 18 + Vite + vanilla CSS (no Tailwind). Viewport meta was already correct; the app shipped **zero media queries** (desktop-first). Three real P0s: header overflow → page horizontal scroll, 8-col comp table overflow, and 14px inputs (iOS focus-zoom).
- **P0 fixes:** `header.top` + `nav` now `flex-wrap` (tabs drop to their own line); inputs/selects → 16px on mobile; comp/estimate `<table>`s reflow to **one card per row** via `data-label` attrs (`thead{display:none}`, `td` flex with `::before` labels) — full tables return at desktop. No horizontal scroll on any view at 375/390/412px.
- **P1/P2:** `min-height:44px` touch targets (nav buttons, `.primary`, inputs/selects, autocomplete `li`) mobile-only; `-webkit-tap-highlight-color:transparent` (global); `prefers-reduced-motion` honored on histogram/scatter via a `usePrefersReducedMotion()` matchMedia hook (Recharts animates in JS, so CSS can't suppress it; `TrendChart` already never animated).
- **Recharts code-split:** `charts.jsx` is now a thin **lazy facade** (`React.lazy`) over new `components/chartsImpl.jsx`; one `<Suspense>` in `App.jsx`. **No view imports changed.** Main JS **557kB → 160kB** (gzip 159→51); the 398kB charts chunk loads on first chart render, off the landing critical path.

Verification (this session's `/verify`): drove the **real app** with Playwright (installed locally, then reverted from `package.json`) against a local `uvicorn` backend serving `webapp.sqlite` + built `dist`. Confirmed empirically at 375/390/412/1024px: no horizontal scroll (16/16 checks), `td` flex↔table-cell flip, input 16px↔14px, nav wrap, 44px targets exact, tap-highlight transparent, and 3 chart SVGs render with 0 page errors under both `reducedMotion: reduce` and `no-preference`.

Gotchas / env notes:
- Backend runs **open (no auth)** when `FH_AUTH_SECRET` is unset (`env -u FH_AUTH_SECRET`) — easiest way to drive the SPA without the password gate. Set `FH_AUTH_SECRET=...` to exercise the gate (login with that value as the Bearer token).
- **`.venv` lacked `pytest`** (only had CLI/zero-dep + the runtime deps I added: `fastapi uvicorn slowapi pydantic-settings`). The pre-push hook (`.venv/bin/python -m pytest`) blocked the first push with `No module named pytest`. Fix: `pip install pytest httpx` into `.venv`, then push (22 tests pass). All now installed locally (gitignored).
- ESM driver scripts must live in `frontend/` (next to `node_modules`) — Node resolves imports from the script's dir, not cwd.

Open: none for this feature. The full audit plan (P0/P1/P2 + perf) is complete. Future copy/name tweaks unaffected.

## Session log — 2026-07-07: local data refresh

Refreshed both **local** caches from the county API (current through sale date 2026-07-06). No code changes; working tree clean (refresh only writes gitignored `data/`). Standard workflow: `.venv/bin/python -m server.jobs.refresh` + `... -m franklin_housing --refresh`, then `... -m scripts.db_diff diff`.
- webapp.sqlite: 13,672 → 13,675 parcels (+3; all new on Wolf Ridge Dr). 46 parcels with a new/changed sale (e.g. 3288 Wolf Ridge Dr $1.05M, 7756 Fulmar Dr $625K, 7155 Wellington Ct $670K, 5903 Newbridge Dr $681K, 7631 W Kestrel Wy $950K; several `$0` non-market transfers), 152 SITEADDRESS fixes, 2 valuation tweaks. Trends materialized for pull #6.
- CLI franklin_housing.sqlite: 923 → 902 comps in the rolling 24-mo window (16 in / 37 out as older sales aged out). `$/sqft` still clusters $197–290; June 2026 median ~$268/sqft / $569K, early July ~$247/sqft.
- Reminder: this is **local only**; the live site rebuilds independently via the 07:00 UTC refresh cron.

## Session log — 2026-07-11: local data refresh

Refreshed both **local** caches from the county API (current through sale date 2026-07-10). No code changes; working tree clean (refresh only writes gitignored `data/`). Standard workflow: `.venv/bin/python -m server.jobs.refresh` + `... -m franklin_housing --refresh`, then `... -m scripts.db_diff diff`.
- webapp.sqlite: 13,675 → 13,678 parcels (+3; new on Deer Bluff Pl, Wolf Ridge Dr, Clover Ln). 33 parcels with a new/changed sale (e.g. 9083 N Moors Pl $840K, 8212 Shannon Glen Blvd $800K, 7616 Worsley Pl $668K, 5410 Haverhill Dr $605K, 3109 Brightington Dr $429K; several `$0` non-market transfers), 2 valuation tweaks (TOTVALUEBASE/BLDVALUEBASE). Trends materialized for pull #7.
- CLI franklin_housing.sqlite: 902 → 909 comps in the rolling 24-mo window (+7, 0 removed). `$/sqft` still clusters $197–290; June 2026 median ~$268/sqft / $569K, early July ~$254/sqft / $602K.
- Reminder: this is **local only**; the live site rebuilds independently via the 07:00 UTC refresh cron.

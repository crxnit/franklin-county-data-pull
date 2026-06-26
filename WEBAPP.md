# Franklin Housing webapp

A hosted, multi-user web version of the CLI: enter a Dublin address, get a
comp-based valuation; tune comps interactively; explore neighborhoods. FastAPI
backend (reusing the `franklin_housing` library) + React/Vite SPA (Recharts).

## Architecture

- **Read path is offline-safe.** The county ArcGIS API is hit *only* by
  `server/jobs/refresh.py` on a schedule. Requests serve read-only from a
  SQLite cache (`data/webapp.sqlite`) of **all** Dublin SFR parcels (~13.7k),
  cleaned once and memoized on the latest `pull_meta` id.
- **Library reuse.** Endpoints compose existing `franklin_housing.analyze`
  functions (`summary`, `trend`, `comps`, `histogram`, `price_estimate`,
  `window`); `server/` adds only the HTTP layer.
- **Comp math windows in code.** The cache holds every parcel (so any address
  is lookup-able); `analyze.window(records, months_back)` restricts to recent
  priced sales for comp/estimate math.
- **Gated** by a shared secret (`FH_AUTH_SECRET`); per-IP rate limiting.

```
server/
  main.py        app factory (auth gate, rate limit, CORS, SPA mount)
  settings.py    FH_*-prefixed env settings
  repo.py        ReadRepo: read-only SQLite + clean_records, memoized
  service.py     build_report() shared by /report and /comps
  models.py      request schemas
  deps.py        get_repo + require_auth
  routers/       address, report, comps, neighborhood, meta
  jobs/refresh.py   scheduled county re-pull (the only writer)
frontend/        React + Vite + Recharts SPA (Report / Comp tuner / Neighborhoods)
```

## Local development

```bash
# 1. backend deps (project venv)
.venv/bin/pip install -r server/requirements.txt

# 2. seed the parcel cache (one-time; pulls all Dublin SFR parcels)
PYTHONPATH=. .venv/bin/python -m server.jobs.refresh

# 3. run API (no auth in dev: leave FH_AUTH_SECRET unset)
PYTHONPATH=. .venv/bin/uvicorn server.main:app --reload --port 8000

# 4. run the SPA dev server (proxies /api -> :8000)
cd frontend && npm install && npm run dev   # http://localhost:5173
```

To serve the built SPA from the API directly (prod-like):
```bash
cd frontend && npm run build && cd ..
PYTHONPATH=. FH_SPA_DIR=frontend/dist .venv/bin/uvicorn server.main:app --port 8000
# http://localhost:8000
```

## Tests & lint

```bash
PYTHONPATH=. .venv/bin/python -m pytest server/tests franklin_housing/tests -q
.venv/bin/ruff check server franklin_housing scripts
```
The Whigham case (7518 Whigham Ct → ~$523K) is the correctness oracle for both
`price_estimate` and the `/api/report` endpoint.

## API (all under /api, gated except /api/health)

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | liveness (open) |
| `GET /api/meta` | data freshness + counts |
| `GET /api/address/search?q=` | address autocomplete |
| `GET /api/report?address=` | pricing report (estimate + comps + charts data) |
| `POST /api/comps` | live re-estimate for the comp tuner |
| `GET /api/neighborhoods` | neighborhood list with medians (+ `name` per code) |
| `GET /api/neighborhoods/{nbhdcd}` | trend, histogram, scatter, recent sales (+ `name`) |
| `GET /api/trends/dimensions` | available breakdowns, group values, granularities (for the UI dropdowns); the `neighborhood` dimension also carries a `labels` map of `code → "Name (code)"` |
| `GET /api/trends?dimension=&group=&granularity=` | one sales-trend slice (median $/sqft + price per period) |

The trend report is materialized by the refresh job into a `trend_cache` table
(keyed on `pull_meta.id`) and read by `ReadRepo.trends()`; if the table is
empty/stale it recomputes from records, so the endpoint is always current as of
the latest pull. Dimensions: `overall`, `school`, `neighborhood`, `price_tier`,
`sqft_band`. Granularities: `sale_biweek`, `sale_month`, `sale_quarter`,
`sale_year`. The shared engine is `franklin_housing/trends.py` (zero-dep), also
used by the CLI to write `data/sales_trends.{json,csv}` on every run.

## Deploy

See `deploy/README.md` (single hardened container, host-cron refresh, JJOC
push-to-deploy pipeline).

## Fast-follows (per the plan)

Throttled property-site enrichment worker (true VALID), ETag response-cache
layer, optional area broadening beyond Dublin CSD.

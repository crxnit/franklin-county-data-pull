# Deploying the Franklin Housing webapp

Single hardened container serving the FastAPI API + the built React SPA. The
county API is hit only by the scheduled refresh job; requests serve read-only
from a SQLite cache on a host volume.

## Build & run locally (Docker)

```bash
docker build -t franklin-housing:dev .
mkdir -p deploy/data
# seed the parcel cache (first boot) — pulls all Dublin SFR parcels
docker run --rm -v "$PWD/deploy/data:/data" franklin-housing:dev \
  python -m server.jobs.refresh
# run
docker run --rm -p 8000:8000 -v "$PWD/deploy/data:/data" \
  -e FH_AUTH_SECRET=changeme franklin-housing:dev
# open http://localhost:8000  (password = FH_AUTH_SECRET)
```

## Production (VPS)

Use `deploy/docker-compose.prod.yml`. Required env in `/srv/portal-apps/franklin-housing/.env` (mode 0600):

```
FH_AUTH_SECRET=<the shared password>
FH_CORS_ORIGINS=https://7518.jjocapps.com
```

- The `./data` dir must be `chown 1000:1000` and seeded once: `docker compose run --rm app python -m server.jobs.refresh`.
- Routing/TLS is handled by the host's existing **Traefik**, which on this VPS uses
  the **file provider** (not the docker provider) — so container labels are ignored.
  Install `deploy/traefik/7518.jjocapps.com.yml` into Traefik's dynamic dir
  (`/srv/portal/traefik/dynamic/`); it routes Host `7518.jjocapps.com` →
  `franklin-housing-app-1:8000` over the shared `traefik` network, TLS via the
  `letsencrypt` resolver (HTTP-01). The container publishes no host port.

### Daily data refresh (host cron)

County data updates Mon–Fri ~7pm ET. Refresh at ~03:00 ET:

```
# /etc/cron.d/franklin-refresh
0 7 * * * deploy  cd /srv/portal-apps/franklin-housing && docker compose exec -T app python -m server.jobs.refresh >> /var/log/franklin-refresh.log 2>&1
```

A failed pull keeps the last-good data (upsert, no clear); the API memoization
invalidates automatically when `pull_meta` advances.

Before each successful pull, the refresh job copies the current DB to
`data/snapshots/<db>.baseline.sqlite` (sqlite backup API; see
`server/jobs/snapshot.py`). To see exactly what a refresh changed
(added / removed / changed parcels, new & re-priced sales):

```
python -m scripts.db_diff diff
```

The baseline is overwritten on every refresh, so `diff` always reflects the
most recent pull. A snapshot failure is logged but never blocks the refresh.

## CI/CD

Push-to-deploy is **wired** (JJOC pipeline): `.github/workflows/{ci,deploy}.yml`
→ GHCR → locked-down SSH (`deploy/vps-deploy.sh` installed as `deploy.sh`) →
Trivy HIGH/CRITICAL gate → `curl /api/health` smoke test. CI runs
`ruff check && pytest`. The image builds for **linux/arm64** (this VPS is arm64;
GitHub runners are amd64, so QEMU is used). No backups: `webapp.sqlite` is a
derived cache the refresh job rebuilds from the county API nightly.

Post-deploy smoke (beyond `/api/health`) — assert the pricing math still works:

```bash
curl -fsS -H "Authorization: Bearer $FH_AUTH_SECRET" \
  "https://7518.jjocapps.com/api/report?address=7518+whigham+ct" \
  | python3 -c "import sys,json; a=json.load(sys.stdin)['estimate']['anchor']['value']; assert 480000<=a<=560000, a; print('ok', a)"
```

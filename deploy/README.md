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
FH_CORS_ORIGINS=https://your-domain
```

- The `./data` dir must be `chown 1000:1000` and seeded once: `docker compose run --rm app python -m server.jobs.refresh`.
- Front the container with a TLS reverse proxy (Traefik/Caddy/nginx); it listens on 127.0.0.1:8000.

### Daily data refresh (host cron)

County data updates Mon–Fri ~7pm ET. Refresh at ~03:00 ET:

```
# /etc/cron.d/franklin-refresh
0 7 * * * deploy  cd /srv/portal-apps/franklin-housing && docker compose exec -T app python -m server.jobs.refresh >> /var/log/franklin-refresh.log 2>&1
```

A failed pull keeps the last-good data (upsert, no clear); the API memoization
invalidates automatically when `pull_meta` advances.

## CI/CD

Wire push-to-deploy with the **`ci-cd-pipeline` skill** (JJOC pipeline): GitHub
Actions → GHCR → locked-down SSH → `deploy.sh` → Trivy HIGH/CRITICAL gate →
`curl /api/health` smoke test. Adapt the CI step to run `ruff check && pytest`.
Add the restic-to-S3 backup section for the stateful SQLite DB (snapshot via
`sqlite3 .backup` for a consistent copy under WAL).

Post-deploy smoke (beyond `/api/health`) — assert the pricing math still works:

```bash
curl -fsS -H "Authorization: Bearer $FH_AUTH_SECRET" \
  "https://your-domain/api/report?address=7518+whigham+ct" \
  | python3 -c "import sys,json; a=json.load(sys.stdin)['estimate']['anchor']['value']; assert 480000<=a<=560000, a; print('ok', a)"
```

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
- Routing/TLS is handled by the host's existing **Traefik** instance via labels in
  the compose file (router `franklin-housing`, Host `7518.jjocapps.com`, entrypoint
  `websecure`, certresolver `letsencrypt`, network `traefik`). The container
  publishes no host port.

### Daily data refresh (host cron)

County data updates Mon–Fri ~7pm ET. Refresh at ~03:00 ET:

```
# /etc/cron.d/franklin-refresh
0 7 * * * deploy  cd /srv/portal-apps/franklin-housing && docker compose exec -T app python -m server.jobs.refresh >> /var/log/franklin-refresh.log 2>&1
```

A failed pull keeps the last-good data (upsert, no clear); the API memoization
invalidates automatically when `pull_meta` advances.

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

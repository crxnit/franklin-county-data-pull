# --- stage 1: build the React SPA ------------------------------------------
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- stage 2: python runtime serving API + built SPA ------------------------
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

# library core + backend (no matplotlib, no node in runtime image)
COPY franklin_housing/ ./franklin_housing/
COPY server/ ./server/
COPY --from=web /web/dist ./frontend/dist

# non-root; data dir is a mounted writable volume (root FS can be read-only)
RUN useradd -u 1000 -m app && mkdir -p /data && chown -R 1000:1000 /data /app
USER 1000
ENV FH_DB_PATH=/data/webapp.sqlite FH_SPA_DIR=frontend/dist

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=4s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').read() else 1)"

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]

"""Runtime settings (env-driven). Prefix: FH_  e.g. FH_AUTH_SECRET=...."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FH_", env_file=".env", extra="ignore")

    # SQLite cache of ALL Dublin SFR parcels (webapp pull). Separate from the
    # CLI's data/franklin_housing.sqlite so the two don't collide.
    db_path: str = "data/webapp.sqlite"

    # Shared-secret gate. If empty, the API is open (dev only).
    auth_secret: str = ""

    # Analysis window for comps (months of sale history).
    months_back: int = 24

    # CORS + rate limiting.
    cors_origins: str = "*"          # comma-separated; "*" in dev
    rate_limit: str = "120/minute"   # default per-IP limit on read endpoints
    rate_limit_search: str = "300/minute"

    # Where the built SPA lives (mounted as static when present).
    spa_dir: str = "frontend/dist"


@lru_cache
def get_settings() -> Settings:
    return Settings()

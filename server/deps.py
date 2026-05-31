"""Shared dependencies: the singleton repo and the shared-secret auth gate."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request

from .repo import ReadRepo
from .settings import Settings, get_settings


def get_repo(request: Request) -> ReadRepo:
    return request.app.state.repo


def require_auth(authorization: str | None = Header(default=None),
                 settings: Settings = Depends(get_settings)) -> None:
    """Gate all /api routes (except health) behind a shared bearer secret.
    If FH_AUTH_SECRET is unset, the API is open (dev convenience)."""
    secret = settings.auth_secret
    if not secret:
        return
    expected = f"Bearer {secret}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="missing or invalid token")

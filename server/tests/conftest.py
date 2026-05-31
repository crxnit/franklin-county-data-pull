import os

import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from server.settings import Settings

DB = "data/webapp.sqlite"


@pytest.fixture(autouse=True)
def _need_db():
    if not os.path.exists(DB):
        pytest.skip("data/webapp.sqlite not seeded (run: python -m server.jobs.refresh)")


@pytest.fixture
def client():
    return TestClient(create_app(Settings(db_path=DB, auth_secret="", spa_dir="__none__")))


@pytest.fixture
def auth_client():
    return TestClient(create_app(Settings(db_path=DB, auth_secret="s3cret", spa_dir="__none__")))

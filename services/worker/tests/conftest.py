"""Postgres fixtures for queue tests (TABFORGE_TEST_DATABASE_URL; `db` tests skip without it).

The schema is owned by services/api: it is created by running the API's Alembic migrations.
"""

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

TEST_DB_ENV = "TABFORGE_TEST_DATABASE_URL"
API_DIR = Path(__file__).resolve().parents[2] / "api"
TABLES = "sessions, login_tokens, jobs, tab_revisions, tabs, audio_assets, users"


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get(TEST_DB_ENV)
    if not url:
        pytest.skip(f"{TEST_DB_ENV} not set")
    env = {**os.environ, "TABFORGE_DATABASE_URL": url}
    for target in ("downgrade base", "upgrade head"):
        subprocess.run(  # noqa: S603 (fixed command, test-only)
            ["uv", "run", "--frozen", "alembic", *target.split()],  # noqa: S607
            cwd=API_DIR,
            env=env,
            check=True,
            capture_output=True,
        )
    return url


@pytest.fixture
def conn(database_url: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(database_url, autocommit=True) as connection:
        yield connection
        connection.execute(f"TRUNCATE {TABLES} CASCADE")

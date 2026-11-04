"""Fixtures for tests against a real Postgres (TABFORGE_TEST_DATABASE_URL).

Tests marked `db` are skipped when the variable is unset; CI sets it.
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text

from tabforge_api.main import create_app
from tabforge_api.settings import Settings
from tabforge_api.storage import ObjectInfo

TEST_DB_ENV = "TABFORGE_TEST_DATABASE_URL"
TABLES = "jobs, tab_revisions, tabs, audio_assets, users"


@dataclass
class FakeStore:
    """In-memory ObjectStore; `put` plays the role of the browser's pre-signed PUT."""

    objects: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    presigned: list[tuple[str, str, int, int]] = field(default_factory=list)

    def presign_put(self, key: str, content_type: str, content_length: int, expires_s: int) -> str:
        self.presigned.append((key, content_type, content_length, expires_s))
        return f"https://s3.test/{key}?signed"

    def head(self, key: str) -> ObjectInfo | None:
        obj = self.objects.get(key)
        return None if obj is None else ObjectInfo(len(obj[0]), obj[1])

    def read_prefix(self, key: str, length: int) -> bytes:
        return self.objects[key][0][:length]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)


def _settings(url: str, **overrides: object) -> Settings:  # shared with other tests
    return Settings(database_url=url, dev_auth=True, **overrides)  # type: ignore[arg-type]


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get(TEST_DB_ENV)
    if not url:
        pytest.skip(f"{TEST_DB_ENV} not set")
    return url


@pytest.fixture(scope="session")
def migrated_engine(database_url: str) -> Iterator[Engine]:
    settings = _settings(database_url)
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = settings.sqlalchemy_url
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(settings.sqlalchemy_url)
    yield engine
    engine.dispose()


@pytest.fixture
def engine(migrated_engine: Engine) -> Iterator[Engine]:
    yield migrated_engine
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} CASCADE"))


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def client(engine: Engine, database_url: str, store: FakeStore) -> TestClient:
    return TestClient(create_app(_settings(database_url), store=store))

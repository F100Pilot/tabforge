import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tabforge_api.main import create_app
from tabforge_api.settings import Settings


def make_settings() -> Settings:
    return Settings(database_url="postgresql://u:p@localhost:5432/db")  # type: ignore[arg-type]


def test_health_returns_ok() -> None:
    client = TestClient(create_app(make_settings()))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_reject_invalid_database_url() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="not-a-dsn")  # type: ignore[arg-type]

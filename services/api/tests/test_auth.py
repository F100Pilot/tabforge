import pytest
from conftest import FakeStore
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tabforge_api.main import create_app
from tabforge_api.settings import Settings

URL = "postgresql://u:p@localhost:5432/db"


def test_without_dev_auth_every_v1_route_is_401() -> None:
    settings = Settings(database_url=URL, dev_auth=False)  # type: ignore[arg-type]
    client = TestClient(create_app(settings, store=FakeStore()))
    resp = client.post(
        "/v1/uploads", json={"content_type": "audio/wav", "size_bytes": 10, "source_kind": "mix"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"
    assert client.get("/v1/jobs/00000000-0000-0000-0000-000000000000").status_code == 401


@pytest.mark.parametrize("env", ["test", "prod"])
def test_dev_auth_refused_outside_dev(env: str) -> None:
    with pytest.raises(ValidationError, match="dev_auth"):
        Settings(database_url=URL, env=env, dev_auth=True)  # type: ignore[arg-type]


def test_presign_ttl_capped_at_five_minutes() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url=URL, presign_ttl_s=301)  # type: ignore[arg-type]


def test_sqlalchemy_url_selects_psycopg_driver() -> None:
    settings = Settings(database_url=URL)  # type: ignore[arg-type]
    assert settings.sqlalchemy_url.startswith("postgresql+psycopg://")


def test_app_refuses_to_start_outside_dev_without_smtp() -> None:
    settings = Settings(database_url=URL, env="prod")  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        create_app(settings, store=FakeStore())


def test_cors_allows_credentials_and_csrf_header_for_listed_origin() -> None:
    settings = Settings(database_url=URL, cors_origins=["http://localhost:3000"])  # type: ignore[arg-type]
    client = TestClient(create_app(settings, store=FakeStore()))
    resp = client.options(
        "/v1/me",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "content-type, x-csrf-token",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert resp.headers["access-control-allow-credentials"] == "true"
    assert "x-csrf-token" in resp.headers["access-control-allow-headers"].lower()
    assert "DELETE" in resp.headers["access-control-allow-methods"]


def test_cors_wildcard_origin_refused() -> None:
    settings = Settings(database_url=URL, cors_origins=["*"])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="explicit origins"):
        create_app(settings, store=FakeStore())

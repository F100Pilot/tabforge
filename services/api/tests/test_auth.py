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

"""env=desktop (ADR-0008) against Postgres: launch-token login, then the whole upload journey."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_desktop import API, TOKEN, WAV, desktop_settings

from tabforge_api.auth import CSRF_HEADER, SESSION_COOKIE
from tabforge_api.local_storage import key_path
from tabforge_api.main import create_app
from tabforge_api.routes.auth import DESKTOP_USER_EMAIL

pytestmark = pytest.mark.db


@pytest.fixture
def desktop(engine: Engine, database_url: str, tmp_path: Path) -> TestClient:
    """The app exactly as the launcher builds it: settings only, real LocalObjectStore."""
    return TestClient(
        create_app(desktop_settings(tmp_path, database_url=database_url)), base_url=API
    )


def _login(client: TestClient) -> str:
    resp = client.post("/v1/auth/desktop", json={"token": TOKEN})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["email"] == DESKTOP_USER_EMAIL
    csrf: str = body["csrf_token"]
    return csrf


def test_launch_token_opens_a_normal_session(desktop: TestClient, engine: Engine) -> None:
    resp = desktop.post("/v1/auth/desktop", json={"token": TOKEN})
    assert resp.status_code == 200
    cookie = resp.headers["set-cookie"].lower()
    assert f"{SESSION_COOKIE}=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    body = resp.json()
    session = desktop.get("/v1/auth/session").json()
    assert session == body
    with engine.connect() as conn:
        users = conn.execute(text("SELECT email FROM users")).scalars().all()
        sessions = conn.execute(text("SELECT count(*) FROM sessions")).scalar_one()
    assert users == [DESKTOP_USER_EMAIL]
    assert sessions == 1


def test_relaunch_reuses_the_local_user_and_replaces_the_session(
    desktop: TestClient, engine: Engine
) -> None:
    first = desktop.post("/v1/auth/desktop", json={"token": TOKEN}).json()
    second = desktop.post("/v1/auth/desktop", json={"token": TOKEN}).json()
    assert first["user"]["id"] == second["user"]["id"]
    assert first["csrf_token"] != second["csrf_token"]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM sessions")).scalar_one() == 1


def test_csrf_still_guards_writes_in_desktop(desktop: TestClient) -> None:
    _login(desktop)
    body = {"content_type": "audio/wav", "size_bytes": len(WAV), "source_kind": "guitar_stem"}
    resp = desktop.post("/v1/uploads", json=body)
    assert resp.status_code == 403
    assert resp.json()["code"] == "csrf_failed"


def test_without_login_desktop_routes_are_401(desktop: TestClient) -> None:
    assert desktop.get("/v1/tabs").status_code == 401


def test_upload_journey_in_desktop(desktop: TestClient, tmp_path: Path, engine: Engine) -> None:
    csrf = _login(desktop)
    headers = {CSRF_HEADER: csrf}
    created = desktop.post(
        "/v1/uploads",
        json={"content_type": "audio/wav", "size_bytes": len(WAV), "source_kind": "guitar_stem"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    ticket = created.json()
    assert ticket["upload_url"].startswith(f"{API}/v1/local-storage/audio/")
    assert ticket["expires_in_s"] <= 300

    # What apps/web does: PUT with exactly the returned headers, no cookie or CSRF needed.
    put = TestClient(desktop.app, base_url=API).put(
        ticket["upload_url"], content=WAV, headers=ticket["headers"]
    )
    assert put.status_code == 200, put.text

    done = desktop.post(f"/v1/uploads/{ticket['audio_id']}/complete", headers=headers)
    assert done.status_code == 201, done.text
    assert done.json()["status"] == "queued"
    with engine.connect() as conn:
        key = conn.execute(
            text("SELECT storage_key FROM audio_assets WHERE id = :id"), {"id": ticket["audio_id"]}
        ).scalar_one()
    stored = key_path(tmp_path, key)
    assert stored.read_bytes() == WAV

    # Account deletion goes through the same port and removes the file.
    assert desktop.delete("/v1/me", headers=headers).status_code == 204
    assert not stored.exists()


def test_content_mismatch_deletes_the_local_file(
    desktop: TestClient, tmp_path: Path, engine: Engine
) -> None:
    csrf = _login(desktop)
    headers = {CSRF_HEADER: csrf}
    fake = b"\x00" * len(WAV)
    ticket = desktop.post(
        "/v1/uploads",
        json={"content_type": "audio/wav", "size_bytes": len(fake)},
        headers=headers,
    ).json()
    assert (
        desktop.put(ticket["upload_url"], content=fake, headers=ticket["headers"]).status_code
        == 200
    )
    resp = desktop.post(f"/v1/uploads/{ticket['audio_id']}/complete", headers=headers)
    assert resp.status_code == 415
    assert not any(p.is_file() for p in tmp_path.rglob("*"))

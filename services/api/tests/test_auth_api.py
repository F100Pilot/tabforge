"""US-07 over HTTP against Postgres: magic link, sessions, CSRF, logout, account deletion."""

import hashlib
import re
import uuid
from dataclasses import dataclass

import pytest
from conftest import FakeMailer, FakeStore, _settings
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tabforge_api.auth import SESSION_COOKIE
from tabforge_api.main import create_app

pytestmark = pytest.mark.db

WAV = b"RIFF\x24\x08\x00\x00WAVEfmt " + b"\x00" * 52
LINK = re.compile(r"http://localhost:3000/login/verify#token=([A-Za-z0-9_-]+)")


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture
def auth_client(
    engine: Engine, database_url: str, store: FakeStore, mailer: FakeMailer
) -> TestClient:
    """No dev_auth: only the session cookie authenticates. Plain-http test server."""
    settings = _settings(database_url, dev_auth=False, session_cookie_secure=False)
    return TestClient(create_app(settings, store=store, mailer=mailer))


def _request_link(client: TestClient, mailer: FakeMailer, email: str) -> str:
    resp = client.post("/v1/auth/magic-link", json={"email": email})
    assert resp.status_code == 202, resp.text
    match = LINK.search(mailer.sent[-1][2])
    assert match is not None
    return match.group(1)


@dataclass
class Login:
    user_id: str
    csrf: str
    cookie: str


def _login(client: TestClient, mailer: FakeMailer, email: str = "ana@example.com") -> Login:
    token = _request_link(client, mailer, email)
    resp = client.post("/v1/auth/verify", json={"token": token})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return Login(body["user"]["id"], body["csrf_token"], client.cookies[SESSION_COOKIE])


# --- magic link -------------------------------------------------------------------------------


def test_magic_link_sends_fragment_link_and_stores_only_the_hash(
    auth_client: TestClient, mailer: FakeMailer, engine: Engine
) -> None:
    resp = auth_client.post("/v1/auth/magic-link", json={"email": " Ana@Example.com "})
    assert resp.status_code == 202
    assert resp.json() == {}
    (to, subject, body) = mailer.sent[0]
    assert to == "ana@example.com"
    assert "TabForge" in subject
    match = LINK.search(body)
    assert match is not None
    token = match.group(1)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT email, token_hash, used_at, "
                "extract(epoch FROM expires_at - created_at) FROM login_tokens"
            )
        ).all()
    assert len(rows) == 1
    email, token_hash, used_at, ttl = rows[0]
    assert (email, token_hash, used_at) == ("ana@example.com", _sha(token), None)
    assert 899 <= float(ttl) <= 901


@pytest.mark.parametrize("email", ["", "ana", "ana@example", "a@b.c\r\nBcc: x@y.z", "x" * 300])
def test_magic_link_rejects_invalid_email_with_422(
    auth_client: TestClient, mailer: FakeMailer, email: str
) -> None:
    resp = auth_client.post("/v1/auth/magic-link", json={"email": email})
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"
    assert mailer.sent == []


def test_magic_link_rate_limited_per_email_case_insensitive(auth_client: TestClient) -> None:
    for i in range(5):
        email = "ana@example.com" if i % 2 else "ANA@example.com"
        assert auth_client.post("/v1/auth/magic-link", json={"email": email}).status_code == 202
    resp = auth_client.post("/v1/auth/magic-link", json={"email": "ana@example.com"})
    assert resp.status_code == 429
    assert resp.json()["code"] == "rate_limited"
    assert int(resp.headers["Retry-After"]) > 0
    other = auth_client.post("/v1/auth/magic-link", json={"email": "rui@example.com"})
    assert other.status_code == 202


def test_magic_link_rate_limited_per_ip(auth_client: TestClient) -> None:
    for i in range(20):
        resp = auth_client.post("/v1/auth/magic-link", json={"email": f"u{i}@example.com"})
        assert resp.status_code == 202
    resp = auth_client.post("/v1/auth/magic-link", json={"email": "new@example.com"})
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_magic_link_mail_failure_is_503(auth_client: TestClient, mailer: FakeMailer) -> None:
    mailer.fail = True
    resp = auth_client.post("/v1/auth/magic-link", json={"email": "ana@example.com"})
    assert resp.status_code == 503
    assert resp.json()["code"] == "mail_unavailable"


# --- verify -----------------------------------------------------------------------------------


def test_verify_opens_session_with_hardened_cookie(
    auth_client: TestClient, mailer: FakeMailer, engine: Engine
) -> None:
    token = _request_link(auth_client, mailer, "ana@example.com")
    resp = auth_client.post("/v1/auth/verify", json={"token": token})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "ana@example.com"
    uuid.UUID(body["user"]["id"])
    assert len(body["csrf_token"]) >= 43
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    attrs = {a.strip().split("=")[0].lower() for a in cookie.split(";")[1:]}
    assert {"httponly", "max-age", "path", "samesite"} <= attrs
    assert "Max-Age=2592000" in cookie
    assert "Path=/" in cookie
    assert "SameSite=lax" in cookie
    assert "secure" not in attrs  # turned off for this plain-http client
    value = auth_client.cookies[SESSION_COOKIE]
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT token_hash, csrf_token FROM sessions")).one()
    assert tuple(stored) == (_sha(value), body["csrf_token"])


def test_cookie_is_secure_by_default(
    engine: Engine, database_url: str, store: FakeStore, mailer: FakeMailer
) -> None:
    client = TestClient(
        create_app(_settings(database_url, dev_auth=False), store=store, mailer=mailer),
        base_url="https://testserver",
    )
    token = _request_link(client, mailer, "ana@example.com")
    resp = client.post("/v1/auth/verify", json={"token": token})
    assert "; secure" in resp.headers["set-cookie"].lower()


def test_verify_token_is_single_use(auth_client: TestClient, mailer: FakeMailer) -> None:
    token = _request_link(auth_client, mailer, "ana@example.com")
    assert auth_client.post("/v1/auth/verify", json={"token": token}).status_code == 200
    again = auth_client.post("/v1/auth/verify", json={"token": token})
    assert again.status_code == 400
    assert again.json()["code"] == "invalid_token"


def test_verify_rejects_expired_token(
    auth_client: TestClient, mailer: FakeMailer, engine: Engine
) -> None:
    token = _request_link(auth_client, mailer, "ana@example.com")
    with engine.begin() as conn:
        conn.execute(text("UPDATE login_tokens SET expires_at = now() - interval '1 second'"))
    resp = auth_client.post("/v1/auth/verify", json={"token": token})
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_token"
    assert SESSION_COOKIE not in auth_client.cookies


@pytest.mark.parametrize("token", ["", "nope", "x" * 5000])
def test_verify_rejects_unknown_token(auth_client: TestClient, token: str) -> None:
    resp = auth_client.post("/v1/auth/verify", json={"token": token})
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_token"


def test_same_email_any_case_is_the_same_user(
    auth_client: TestClient, mailer: FakeMailer, engine: Engine
) -> None:
    first = _login(auth_client, mailer, "ana@example.com")
    second = _login(auth_client, mailer, "ANA@Example.COM")
    assert first.user_id == second.user_id
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
        # A new login replaced the old session (no fixation, no pile-up on one browser).
        assert conn.execute(text("SELECT count(*) FROM sessions")).scalar_one() == 1


# --- session ----------------------------------------------------------------------------------


def test_session_returns_user_and_csrf(auth_client: TestClient, mailer: FakeMailer) -> None:
    login = _login(auth_client, mailer)
    resp = auth_client.get("/v1/auth/session")
    assert resp.status_code == 200
    assert resp.json() == {
        "user": {"id": login.user_id, "email": "ana@example.com"},
        "csrf_token": login.csrf,
    }


def test_session_without_cookie_is_401(auth_client: TestClient) -> None:
    resp = auth_client.get("/v1/auth/session")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


def test_unknown_cookie_is_401(auth_client: TestClient) -> None:
    auth_client.cookies.set(SESSION_COOKIE, "forged")
    assert auth_client.get("/v1/auth/session").status_code == 401
    assert auth_client.get("/v1/tabs").status_code == 401


def test_expired_session_is_401(
    auth_client: TestClient, mailer: FakeMailer, engine: Engine
) -> None:
    _login(auth_client, mailer)
    with engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET expires_at = now() - interval '1 second'"))
    assert auth_client.get("/v1/auth/session").status_code == 401


def test_dev_auth_without_cookie_returns_dev_user_without_csrf(client: TestClient) -> None:
    resp = client.get("/v1/auth/session")
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "dev@tabforge.local"
    assert resp.json()["csrf_token"] is None


def test_cookie_wins_over_dev_auth(
    engine: Engine, database_url: str, store: FakeStore, mailer: FakeMailer
) -> None:
    settings = _settings(database_url, dev_auth=True, session_cookie_secure=False)
    client = TestClient(create_app(settings, store=store, mailer=mailer))
    login = _login(client, mailer, "ana@example.com")
    body = client.get("/v1/auth/session").json()
    assert body["user"]["id"] == login.user_id
    assert body["csrf_token"] == login.csrf


# --- CSRF -------------------------------------------------------------------------------------


def _create_upload(client: TestClient, csrf: str | None) -> int:
    headers = {"X-CSRF-Token": csrf} if csrf is not None else {}
    payload = {"content_type": "audio/wav", "size_bytes": len(WAV), "source_kind": "mix"}
    status: int = client.post("/v1/uploads", json=payload, headers=headers).status_code
    return status


def test_unsafe_request_with_cookie_needs_csrf_header(
    auth_client: TestClient, mailer: FakeMailer
) -> None:
    login = _login(auth_client, mailer)
    resp = auth_client.post(
        "/v1/uploads", json={"content_type": "audio/wav", "size_bytes": 10, "source_kind": "mix"}
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "csrf_failed"
    assert _create_upload(auth_client, "wrong") == 403
    assert _create_upload(auth_client, login.csrf) == 201
    assert auth_client.get("/v1/jobs").status_code == 200  # safe methods need no token


def test_dev_auth_without_cookie_skips_csrf(client: TestClient) -> None:
    assert _create_upload(client, None) == 201


# --- logout -----------------------------------------------------------------------------------


def test_logout_needs_csrf_then_ends_the_session(
    auth_client: TestClient, mailer: FakeMailer, engine: Engine
) -> None:
    login = _login(auth_client, mailer)
    refused = auth_client.post("/v1/auth/logout")
    assert refused.status_code == 403
    assert refused.json()["code"] == "csrf_failed"
    resp = auth_client.post("/v1/auth/logout", headers={"X-CSRF-Token": login.csrf})
    assert resp.status_code == 204
    assert f'{SESSION_COOKIE}=""' in resp.headers["set-cookie"]
    assert "Max-Age=0" in resp.headers["set-cookie"]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM sessions")).scalar_one() == 0
    auth_client.cookies.set(SESSION_COOKIE, login.cookie)  # a stolen copy no longer works
    assert auth_client.get("/v1/auth/session").status_code == 401


def test_logout_without_session_is_204(auth_client: TestClient) -> None:
    assert auth_client.post("/v1/auth/logout").status_code == 204
    auth_client.cookies.set(SESSION_COOKIE, "stale")
    assert auth_client.post("/v1/auth/logout").status_code == 204


# --- account deletion (RGPD art. 17) ----------------------------------------------------------


def _seed_content(client: TestClient, store: FakeStore, engine: Engine, csrf: str) -> str:
    """One completed upload (object + job) and one tab with a revision; returns the key."""
    headers = {"X-CSRF-Token": csrf}
    payload = {"content_type": "audio/wav", "size_bytes": len(WAV), "source_kind": "mix"}
    created = client.post("/v1/uploads", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    key = store.presigned[-1][0]
    store.put(key, WAV, "audio/wav")
    done = client.post(f"/v1/uploads/{created.json()['audio_id']}/complete", headers=headers)
    assert done.status_code == 201, done.text
    user_id = key.split("/")[1]
    with engine.begin() as conn:
        tab_id = conn.execute(
            text("INSERT INTO tabs (owner_id, title) VALUES (:u, 't') RETURNING id"),
            {"u": user_id},
        ).scalar_one()
        rev = conn.execute(
            text(
                "INSERT INTO tab_revisions (tab_id, score, source) "
                "VALUES (:t, '{}'::jsonb, 'ai') RETURNING id"
            ),
            {"t": tab_id},
        ).scalar_one()
        conn.execute(
            text("UPDATE tabs SET current_revision_id = :r WHERE id = :t"), {"r": rev, "t": tab_id}
        )
        conn.execute(text("UPDATE jobs SET tab_id = :t"), {"t": tab_id})
    return key


def _counts(engine: Engine, email: str) -> dict[str, int]:
    tables = ["users", "audio_assets", "jobs", "tabs", "tab_revisions", "sessions"]
    with engine.connect() as conn:
        counts = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in tables}  # noqa: S608
        counts["login_tokens"] = conn.execute(
            text("SELECT count(*) FROM login_tokens WHERE email = :e"), {"e": email}
        ).scalar_one()
    return counts


def test_delete_me_removes_audio_rows_and_session(
    auth_client: TestClient, mailer: FakeMailer, store: FakeStore, engine: Engine
) -> None:
    login = _login(auth_client, mailer)
    key = _seed_content(auth_client, store, engine, login.csrf)
    assert all(n >= 1 for n in _counts(engine, "ana@example.com").values())

    assert auth_client.delete("/v1/me").status_code == 403  # CSRF applies
    resp = auth_client.delete("/v1/me", headers={"X-CSRF-Token": login.csrf})
    assert resp.status_code == 204
    assert "Max-Age=0" in resp.headers["set-cookie"]
    assert key not in store.objects
    assert set(_counts(engine, "ana@example.com").values()) == {0}
    assert auth_client.get("/v1/auth/session").status_code == 401


def test_delete_me_leaves_other_users_alone(
    auth_client: TestClient, mailer: FakeMailer, store: FakeStore, engine: Engine
) -> None:
    other = _login(auth_client, mailer, "rui@example.com")
    other_key = _seed_content(auth_client, store, engine, other.csrf)
    login = _login(auth_client, mailer, "ana@example.com")
    resp = auth_client.delete("/v1/me", headers={"X-CSRF-Token": login.csrf})
    assert resp.status_code == 204
    assert other_key in store.objects
    counts = _counts(engine, "rui@example.com")
    assert counts["users"] == 1
    assert counts["tabs"] == 1
    assert counts["login_tokens"] == 1


@dataclass
class BrokenStore(FakeStore):
    def delete(self, key: str) -> None:
        raise OSError("s3 down")


def test_delete_me_storage_failure_deletes_nothing(
    engine: Engine, database_url: str, mailer: FakeMailer
) -> None:
    store = BrokenStore()
    client = TestClient(
        create_app(
            _settings(database_url, dev_auth=False, session_cookie_secure=False),
            store=store,
            mailer=mailer,
        )
    )
    login = _login(client, mailer)
    _seed_content(client, store, engine, login.csrf)
    before = _counts(engine, "ana@example.com")
    resp = client.delete("/v1/me", headers={"X-CSRF-Token": login.csrf})
    assert resp.status_code == 503
    assert resp.json()["code"] == "storage_unavailable"
    assert _counts(engine, "ana@example.com") == before
    assert client.get("/v1/auth/session").status_code == 200  # still logged in, can retry

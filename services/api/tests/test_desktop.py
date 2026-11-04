"""env=desktop (ADR-0008) without a database: settings, route gating, TrustedHost, signed PUT."""

from pathlib import Path
from typing import Any
from urllib.parse import unquote

import pytest
from conftest import FakeMailer, FakeStore
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tabforge_api.local_storage import LocalObjectStore, key_path, upload_signature
from tabforge_api.mailer import DisabledMailer, build_mailer
from tabforge_api.main import create_app
from tabforge_api.settings import Settings

URL = "postgresql://u:p@localhost:5432/db"
TOKEN = "t" * 43
SECRET = "s" * 43
API = "http://127.0.0.1:47801"
WEB = "http://127.0.0.1:47800"
KEY = "audio/u1/a1"
WAV = b"RIFF\x24\x08\x00\x00WAVEfmt " + b"\x00" * 52


def desktop_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": URL,
        "env": "desktop",
        "storage_backend": "local",
        "local_storage_dir": tmp_path,
        "desktop_launch_token": TOKEN,
        "local_upload_secret": SECRET,
        "session_cookie_secure": False,
        "cors_origins": [WEB],
        **overrides,
    }
    return Settings(**values)


class Clock:
    def __init__(self, now: float = 1_800_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def local_store(tmp_path: Path, clock: Clock) -> LocalObjectStore:
    return LocalObjectStore(tmp_path, SECRET.encode(), API, clock=clock)


@pytest.fixture
def desktop(tmp_path: Path, local_store: LocalObjectStore) -> TestClient:
    return TestClient(create_app(desktop_settings(tmp_path), store=local_store), base_url=API)


# --- settings ---------------------------------------------------------------------------------


def test_desktop_settings_are_valid(tmp_path: Path) -> None:
    settings = desktop_settings(tmp_path)
    assert (settings.env, settings.storage_backend) == ("desktop", "local")


def test_online_defaults_are_unchanged() -> None:
    settings = Settings(database_url=URL)  # type: ignore[arg-type]
    assert settings.storage_backend == "s3"
    assert settings.local_storage_dir is None
    assert str(settings.api_public_url) == "http://127.0.0.1:47801/"


def test_desktop_settings_from_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "ENV": "desktop",
        "DATABASE_URL": URL,
        "STORAGE_BACKEND": "local",
        "LOCAL_STORAGE_DIR": str(tmp_path),
        "DESKTOP_LAUNCH_TOKEN": TOKEN,
        "LOCAL_UPLOAD_SECRET": SECRET,
        "API_PUBLIC_URL": "http://localhost:47801",
    }.items():
        monkeypatch.setenv(f"TABFORGE_{name}", value)
    settings = Settings()  # type: ignore[call-arg]
    assert settings.local_storage_dir == tmp_path
    assert settings.desktop_launch_token is not None
    assert settings.desktop_launch_token.get_secret_value() == TOKEN


def test_desktop_requires_local_storage(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="storage_backend=local"):
        desktop_settings(tmp_path, storage_backend="s3")


@pytest.mark.parametrize(
    "missing", ["local_storage_dir", "desktop_launch_token", "local_upload_secret"]
)
def test_desktop_requires_every_local_setting(tmp_path: Path, missing: str) -> None:
    with pytest.raises(ValidationError, match=missing):
        desktop_settings(tmp_path, **{missing: None})


@pytest.mark.parametrize("env", ["dev", "prod"])
def test_local_storage_refused_online(tmp_path: Path, env: str) -> None:
    with pytest.raises(ValidationError, match="storage_backend=local"):
        Settings(
            database_url=URL,  # type: ignore[arg-type]
            env=env,  # type: ignore[arg-type]
            storage_backend="local",
            local_storage_dir=tmp_path,
            local_upload_secret=SECRET,  # type: ignore[arg-type]
        )


def test_local_storage_allowed_in_test_env_with_its_settings(tmp_path: Path) -> None:
    Settings(
        database_url=URL,  # type: ignore[arg-type]
        env="test",
        storage_backend="local",
        local_storage_dir=tmp_path,
        local_upload_secret=SECRET,  # type: ignore[arg-type]
    )
    with pytest.raises(ValidationError, match="local_upload_secret"):
        Settings(database_url=URL, env="test", storage_backend="local")  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["desktop_launch_token", "local_upload_secret"])
def test_short_secrets_refused(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValidationError, match=f"{name} must have at least 32"):
        desktop_settings(tmp_path, **{name: "x" * 31})


def test_desktop_refuses_non_loopback_upload_url(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="loopback"):
        desktop_settings(tmp_path, api_public_url="http://192.168.1.5:47801")


def test_dev_auth_refused_in_desktop(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="dev_auth"):
        desktop_settings(tmp_path, dev_auth=True)


def test_desktop_needs_no_smtp_and_sends_no_email(tmp_path: Path) -> None:
    mailer = build_mailer(desktop_settings(tmp_path))
    assert isinstance(mailer, DisabledMailer)
    with pytest.raises(RuntimeError, match="disabled"):
        mailer.send("a@b.c", "s", "b")
    create_app(desktop_settings(tmp_path))  # no SMTP, no injected store: starts


def test_local_backend_refuses_a_non_local_store(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="LocalObjectStore"):
        create_app(desktop_settings(tmp_path), store=FakeStore())


# --- route gating -----------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/v1/auth/magic-link", "/v1/auth/verify"])
def test_email_login_is_404_in_desktop(desktop: TestClient, path: str) -> None:
    resp = desktop.post(path, json={"email": "a@b.co", "token": "x"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.parametrize("env", ["dev", "prod"])
def test_desktop_login_is_404_online(env: str) -> None:
    settings = Settings(database_url=URL, env=env)  # type: ignore[arg-type]
    client = TestClient(create_app(settings, store=FakeStore(), mailer=FakeMailer()))
    resp = client.post("/v1/auth/desktop", json={"token": TOKEN})
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


def test_desktop_login_with_wrong_token_is_403(desktop: TestClient) -> None:
    for token in ("wrong", TOKEN[:-1], TOKEN + "x", "", "é"):
        resp = desktop.post("/v1/auth/desktop", json={"token": token})
        assert resp.status_code == 403
        assert resp.json()["code"] == "invalid_launch_token"
        assert "set-cookie" not in resp.headers


def test_desktop_login_is_rate_limited(desktop: TestClient) -> None:
    for _ in range(10):
        assert desktop.post("/v1/auth/desktop", json={"token": "wrong"}).status_code == 403
    resp = desktop.post("/v1/auth/desktop", json={"token": TOKEN})
    assert resp.status_code == 429
    assert resp.json()["code"] == "rate_limited"
    assert int(resp.headers["retry-after"]) > 0


def test_local_storage_route_absent_with_s3() -> None:
    client = TestClient(create_app(Settings(database_url=URL), store=FakeStore()))  # type: ignore[arg-type]
    assert client.put(f"/v1/local-storage/{KEY}", content=b"x").status_code == 404


# --- TrustedHost ------------------------------------------------------------------------------


@pytest.mark.parametrize("base", [API, "http://localhost:47801", "http://127.0.0.1"])
def test_desktop_accepts_loopback_hosts(tmp_path: Path, base: str) -> None:
    client = TestClient(create_app(desktop_settings(tmp_path)), base_url=base)
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize(
    "host", ["evil.example", "127.0.0.1.evil.example", "localhost.evil.example", "192.168.1.5"]
)
def test_desktop_refuses_other_hosts(desktop: TestClient, host: str) -> None:
    resp = desktop.get("/health", headers={"Host": host})
    assert resp.status_code == 400


def test_online_does_not_restrict_hosts() -> None:
    client = TestClient(create_app(Settings(database_url=URL), store=FakeStore()))  # type: ignore[arg-type]
    assert client.get("/health", headers={"Host": "api.tabforge.example"}).status_code == 200


# --- signed PUT -------------------------------------------------------------------------------


def _put(
    client: TestClient, url: str, body: bytes, content_type: str = "audio/wav", **headers: str
) -> Any:
    return client.put(url, content=body, headers={"Content-Type": content_type, **headers})


def test_put_with_signed_url_stores_the_file(
    desktop: TestClient, local_store: LocalObjectStore, tmp_path: Path
) -> None:
    url = local_store.presign_put(KEY, "audio/wav", len(WAV), 300)
    resp = _put(desktop, url, WAV)
    assert resp.status_code == 200
    assert resp.content == b""
    assert key_path(tmp_path, KEY).read_bytes() == WAV


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda u: u.replace("sig=", "sig=0"), "invalid_signature"),
        (lambda u: u[:-1] + ("0" if u[-1] != "0" else "1"), "invalid_signature"),
        (lambda u: u.split("&sig=")[0], "invalid_signature"),
        (lambda u: u.replace("audio/u1/a1", "audio/u1/a2"), "invalid_signature"),
    ],
    ids=["malformed", "tampered", "missing", "other-key"],
)
def test_put_with_bad_signature_is_403(
    desktop: TestClient, local_store: LocalObjectStore, tmp_path: Path, mutate: Any, code: str
) -> None:
    url = mutate(local_store.presign_put(KEY, "audio/wav", len(WAV), 300))
    resp = _put(desktop, url, WAV)
    assert resp.status_code == 403
    assert resp.json()["code"] == code
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


def test_put_after_expiry_is_403(
    desktop: TestClient, local_store: LocalObjectStore, clock: Clock
) -> None:
    url = local_store.presign_put(KEY, "audio/wav", len(WAV), 60)
    clock.now += 61
    resp = _put(desktop, url, WAV)
    assert resp.status_code == 403
    assert resp.json()["code"] == "upload_url_expired"


def test_put_with_other_content_type_is_403(
    desktop: TestClient, local_store: LocalObjectStore
) -> None:
    url = local_store.presign_put(KEY, "audio/wav", len(WAV), 300)
    for ctype in ("audio/flac", "audio/wav; charset=utf-8", "audio/WAV"):
        resp = _put(desktop, url, WAV, content_type=ctype)
        assert resp.status_code == 403
        assert resp.json()["code"] == "invalid_signature"


def test_put_with_other_length_is_403(
    desktop: TestClient, local_store: LocalObjectStore, tmp_path: Path
) -> None:
    url = local_store.presign_put(KEY, "audio/wav", len(WAV), 300)
    resp = _put(desktop, url, WAV + b"x")
    assert resp.status_code == 403
    assert resp.json()["code"] == "invalid_signature"
    assert not key_path(tmp_path, KEY).exists()


@pytest.mark.parametrize("extra", [b"x", b""], ids=["overflow", "short"])
def test_body_not_matching_the_signed_length_is_400_and_leaves_no_file(
    desktop: TestClient, local_store: LocalObjectStore, tmp_path: Path, extra: bytes
) -> None:
    # The Content-Length header is the signed one; the body itself is longer or shorter.
    declared = len(WAV) if extra else len(WAV) + 10
    url = local_store.presign_put(KEY, "audio/wav", declared, 300)
    resp = _put(desktop, url, WAV + extra, **{"Content-Length": str(declared)})
    assert resp.status_code == 400
    assert resp.json()["code"] == "upload_size_mismatch"
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


def test_put_without_content_length_is_411(
    desktop: TestClient, local_store: LocalObjectStore
) -> None:
    url = local_store.presign_put(KEY, "audio/wav", len(WAV), 300)
    resp = desktop.put(url, content=iter([WAV]), headers={"Content-Type": "audio/wav"})
    assert resp.status_code == 411
    assert resp.json()["code"] == "length_required"


@pytest.mark.parametrize(
    "raw_key",
    [
        "audio/%2E%2E/%2E%2E/escape",
        "audio%5C..%5Cescape",
        "audio/x%00y",
        "audio/x:y",
        "audio//x",
    ],
)
def test_put_with_unsafe_key_is_400_even_when_signed(
    desktop: TestClient, tmp_path: Path, clock: Clock, raw_key: str
) -> None:
    key = unquote(raw_key)
    expires = int(clock.now) + 60
    sig = upload_signature(SECRET.encode(), "PUT", key, expires, "audio/wav", len(WAV))
    resp = _put(desktop, f"{API}/v1/local-storage/{raw_key}?expires={expires}&sig={sig}", WAV)
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_key"
    assert not any(p.is_file() for p in tmp_path.parent.rglob("escape"))


def test_put_cors_preflight_allows_the_web_origin(
    desktop: TestClient, local_store: LocalObjectStore
) -> None:
    url = local_store.presign_put(KEY, "audio/wav", len(WAV), 300)
    resp = desktop.options(
        url,
        headers={
            "Origin": WEB,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == WEB
    assert "PUT" in resp.headers["access-control-allow-methods"]
    put = _put(desktop, url, WAV, Origin=WEB)
    assert put.status_code == 200
    assert put.headers["access-control-allow-origin"] == WEB


def test_online_cors_still_does_not_allow_put() -> None:
    settings = Settings(database_url=URL, cors_origins=["http://localhost:3000"])  # type: ignore[arg-type]
    client = TestClient(create_app(settings, store=FakeStore()))
    resp = client.options(
        "/v1/uploads",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "PUT"},
    )
    assert resp.status_code == 400

import pytest
from conftest import FakeStore, _settings
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tabforge_api.limits import SlidingWindowLimiter
from tabforge_api.main import create_app


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_allows_up_to_max_then_reports_retry_after() -> None:
    clock = Clock()
    limiter = SlidingWindowLimiter(max_events=3, window_s=60, clock=clock)
    key = "u1"
    assert [limiter.hit(key) for _ in range(3)] == [None, None, None]
    retry = limiter.hit(key)
    assert retry is not None and 0 < retry <= 60


def test_limiter_window_slides() -> None:
    clock = Clock()
    limiter = SlidingWindowLimiter(max_events=2, window_s=10, clock=clock)
    limiter.hit("u")
    clock.now += 6
    limiter.hit("u")
    assert limiter.hit("u") is not None
    clock.now += 5  # first hit is now 11 s old
    assert limiter.hit("u") is None


def test_limiter_keys_are_independent() -> None:
    limiter = SlidingWindowLimiter(max_events=1, window_s=60, clock=Clock())
    assert limiter.hit("a") is None
    assert limiter.hit("b") is None
    assert limiter.hit("a") is not None


WAV = b"RIFF\x24\x08\x00\x00WAVEfmt " + b"\x00" * 52


def _create(client: TestClient) -> int:
    body = {"content_type": "audio/wav", "size_bytes": len(WAV), "source_kind": "guitar_stem"}
    status: int = client.post("/v1/uploads", json=body).status_code
    return status


@pytest.mark.db
def test_write_rate_limit_returns_429_with_retry_after(engine: Engine, database_url: str) -> None:
    app = create_app(_settings(database_url, write_rate_per_minute=2), store=FakeStore())
    client = TestClient(app)
    assert [_create(client), _create(client)] == [201, 201]
    resp = client.post(
        "/v1/uploads", json={"content_type": "audio/wav", "size_bytes": 10, "source_kind": "mix"}
    )
    assert resp.status_code == 429
    assert resp.json()["code"] == "rate_limited"
    assert int(resp.headers["retry-after"]) >= 1


@pytest.mark.db
def test_daily_upload_quota(engine: Engine, database_url: str) -> None:
    app = create_app(_settings(database_url, daily_upload_limit=2), store=FakeStore())
    client = TestClient(app)
    assert [_create(client), _create(client)] == [201, 201]
    resp = client.post(
        "/v1/uploads", json={"content_type": "audio/wav", "size_bytes": 10, "source_kind": "mix"}
    )
    assert resp.status_code == 429
    assert resp.json()["code"] == "quota_exceeded"


@pytest.mark.db
def test_quota_ignores_rejected_and_old_uploads(engine: Engine, database_url: str) -> None:
    app = create_app(_settings(database_url, daily_upload_limit=1), store=FakeStore())
    client = TestClient(app)
    assert _create(client) == 201
    with engine.begin() as conn:
        conn.execute(text("UPDATE audio_assets SET created_at = now() - interval '25 hours'"))
    assert _create(client) == 201
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE audio_assets SET status = 'rejected' "
                "WHERE created_at > now() - interval '1 hour'"
            )
        )
    assert _create(client) == 201

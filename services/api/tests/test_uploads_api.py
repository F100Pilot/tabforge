import uuid
from typing import Any

import pytest
from conftest import FakeStore
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

pytestmark = pytest.mark.db

WAV = b"RIFF\x24\x08\x00\x00WAVEfmt " + b"\x00" * 52
MAX = 50 * 1024 * 1024


def _create(client: TestClient, **body: Any) -> Any:
    payload = {"content_type": "audio/wav", "size_bytes": len(WAV), "source_kind": "guitar_stem"}
    payload.update(body)
    return client.post("/v1/uploads", json=payload)


def _upload(client: TestClient, store: FakeStore, data: bytes = WAV) -> uuid.UUID:
    resp = _create(client, size_bytes=len(data))
    assert resp.status_code == 201, resp.text
    key = store.presigned[-1][0]
    store.put(key, data, "audio/wav")
    return uuid.UUID(resp.json()["audio_id"])


def test_create_upload_signs_type_length_and_short_expiry(
    client: TestClient, store: FakeStore
) -> None:
    resp = _create(client, content_type="audio/x-wav")
    assert resp.status_code == 201
    body = resp.json()
    assert body["method"] == "PUT"
    assert body["headers"] == {"Content-Type": "audio/wav"}
    assert body["expires_in_s"] <= 300
    key, ctype, length, ttl = store.presigned[-1]
    assert key.endswith(body["audio_id"])
    assert (ctype, length, ttl) == ("audio/wav", len(WAV), body["expires_in_s"])


def test_create_upload_rejects_oversize_with_413(client: TestClient) -> None:
    resp = _create(client, size_bytes=MAX + 1)
    assert resp.status_code == 413
    assert resp.headers["content-type"] == "application/problem+json"
    assert resp.json()["code"] == "file_too_large"


def test_create_upload_rejects_unsupported_type_with_415(client: TestClient) -> None:
    resp = _create(client, content_type="video/mp4")
    assert resp.status_code == 415
    assert resp.json()["code"] == "unsupported_media_type"


def test_create_upload_validates_body(client: TestClient) -> None:
    resp = _create(client, size_bytes=0, source_kind="bass")
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_complete_creates_queued_job(client: TestClient, store: FakeStore, engine: Engine) -> None:
    audio_id = _upload(client, store)
    resp = client.post(f"/v1/uploads/{audio_id}/complete")
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert (job["status"], job["stage"], job["attempts"]) == ("queued", None, 0)
    with engine.connect() as conn:
        status, expires = conn.execute(
            text("SELECT status, expires_at FROM audio_assets WHERE id = :id"), {"id": audio_id}
        ).one()
    assert status == "uploaded"
    assert expires is not None

    assert client.get(f"/v1/jobs/{job['id']}").json()["status"] == "queued"


def test_complete_rejects_content_not_matching_declared_type(
    client: TestClient, store: FakeStore, engine: Engine
) -> None:
    fake = b"%PDF-1.7\n" + b"\x00" * 50
    audio_id = _upload(client, store, fake)
    resp = client.post(f"/v1/uploads/{audio_id}/complete")
    assert resp.status_code == 415
    assert resp.json()["code"] == "content_type_mismatch"
    assert store.objects == {}  # nothing kept (US-01)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 0
        status = conn.execute(
            text("SELECT status FROM audio_assets WHERE id = :id"), {"id": audio_id}
        ).scalar_one()
    assert status == "rejected"


def test_complete_before_upload_is_409(client: TestClient) -> None:
    audio_id = _create(client).json()["audio_id"]
    resp = client.post(f"/v1/uploads/{audio_id}/complete")
    assert resp.status_code == 409
    assert resp.json()["code"] == "upload_incomplete"


def test_complete_twice_is_409(client: TestClient, store: FakeStore) -> None:
    audio_id = _upload(client, store)
    assert client.post(f"/v1/uploads/{audio_id}/complete").status_code == 201
    resp = client.post(f"/v1/uploads/{audio_id}/complete")
    assert resp.status_code == 409
    assert resp.json()["code"] == "upload_already_completed"


def test_other_users_upload_and_job_are_not_found(
    client: TestClient, store: FakeStore, engine: Engine
) -> None:
    audio_id = _upload(client, store)
    job_id = client.post(f"/v1/uploads/{audio_id}/complete").json()["id"]
    with engine.begin() as conn:  # hand both to another user (threat model T2)
        other = conn.execute(
            text("INSERT INTO users (email) VALUES ('other@example.com') RETURNING id")
        ).scalar_one()
        conn.execute(text("UPDATE audio_assets SET user_id = :u"), {"u": other})
    assert client.get(f"/v1/jobs/{job_id}").status_code == 404
    assert client.post(f"/v1/uploads/{audio_id}/complete").status_code == 404


def test_unknown_ids_are_404_problem(client: TestClient) -> None:
    for path in (f"/v1/jobs/{uuid.uuid4()}", f"/v1/tabs/{uuid.uuid4()}"):
        resp = client.get(path)
        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"

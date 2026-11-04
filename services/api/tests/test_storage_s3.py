"""S3ObjectStore against a real S3 API (versitygw in dev/CI). Needs TABFORGE_TEST_S3_ENDPOINT."""

import os
import uuid

import httpx
import pytest

from tabforge_api.settings import Settings
from tabforge_api.storage import S3ObjectStore

pytestmark = pytest.mark.s3

ENDPOINT_ENV = "TABFORGE_TEST_S3_ENDPOINT"
WAV = b"RIFF\x24\x08\x00\x00WAVEfmt " + b"\x00" * 20


@pytest.fixture
def s3_store() -> S3ObjectStore:
    endpoint = os.environ.get(ENDPOINT_ENV)
    if not endpoint:
        pytest.skip(f"{ENDPOINT_ENV} not set")
    settings = Settings(
        database_url="postgresql://u:p@localhost/db",  # type: ignore[arg-type]
        s3_endpoint_url=endpoint,  # type: ignore[arg-type]
        s3_bucket=f"test-{uuid.uuid4().hex[:12]}",
        s3_access_key=os.environ.get("TABFORGE_TEST_S3_ACCESS_KEY", "tabforge"),  # type: ignore[arg-type]
        s3_secret_key=os.environ.get("TABFORGE_TEST_S3_SECRET_KEY", "tabforge-dev-secret"),  # type: ignore[arg-type]
    )
    store = S3ObjectStore(settings)
    store.ensure_bucket(["http://localhost:3000"])
    return store


def test_presigned_put_head_read_delete(s3_store: S3ObjectStore) -> None:
    key = f"audio/u/{uuid.uuid4()}"
    url = s3_store.presign_put(key, "audio/wav", len(WAV), 60)

    assert (
        httpx.put(url, content=WAV + b"x", headers={"Content-Type": "audio/wav"}).status_code == 403
    )
    assert httpx.put(url, content=WAV, headers={"Content-Type": "audio/mpeg"}).status_code == 403
    assert httpx.put(url, content=WAV, headers={"Content-Type": "audio/wav"}).status_code == 200

    info = s3_store.head(key)
    assert info is not None
    assert info.size_bytes == len(WAV)
    assert s3_store.read_prefix(key, 12) == WAV[:12]

    s3_store.delete(key)
    assert s3_store.head(key) is None

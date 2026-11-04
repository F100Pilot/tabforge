"""Desktop storage (ADR-0008): key -> path safety, upload signatures, LocalObjectStore on disk."""

import asyncio
import os
from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from tabforge_api.local_storage import (
    InvalidKeyError,
    LocalObjectStore,
    SignatureError,
    UploadSizeError,
    key_path,
    upload_signature,
    verify_upload_signature,
)

SECRET = b"s" * 32
NOW = 1_800_000_000.0
KEY = "audio/0b9e/4f1c"


# --- key -> path ------------------------------------------------------------------------------


def test_key_maps_to_a_path_inside_the_root(tmp_path: Path) -> None:
    assert key_path(tmp_path, KEY) == tmp_path.resolve() / "audio" / "0b9e" / "4f1c"


@pytest.mark.parametrize(
    "key",
    [
        "",
        "/etc/passwd",
        "../outside",
        "audio/../../outside",
        "audio/./x",
        "audio//x",
        "audio/x/",
        "audio\\..\\x",
        "audio/x\x00y",
        "audio/x\ny",
        "C:/Windows/x",
        "audio/x:stream",
        "audio/x.",
        "audio/CON",
        "audio/nul.txt",
        "audio/a b",
        "a" * 513,
    ],
)
def test_unsafe_keys_are_rejected(tmp_path: Path, key: str) -> None:
    with pytest.raises(InvalidKeyError):
        key_path(tmp_path, key)


def test_symlink_escaping_the_root_is_rejected(tmp_path: Path) -> None:
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "audio").symlink_to(outside, target_is_directory=True)
    with pytest.raises(InvalidKeyError):
        key_path(root, "audio/x")


# --- signatures -------------------------------------------------------------------------------


def _sig(**overrides: object) -> str:
    values: dict[str, object] = {
        "method": "PUT",
        "key": KEY,
        "expires": int(NOW) + 60,
        "content_type": "audio/wav",
        "content_length": 100,
        **overrides,
    }
    return upload_signature(SECRET, **values)  # type: ignore[arg-type]


def _verify(sig: str | None, **overrides: object) -> None:
    values: dict[str, object] = {
        "method": "PUT",
        "key": KEY,
        "expires": str(int(NOW) + 60),
        "sig": sig,
        "content_type": "audio/wav",
        "content_length": 100,
        "now": NOW,
        **overrides,
    }
    verify_upload_signature(SECRET, **values)  # type: ignore[arg-type]


def test_signature_round_trip() -> None:
    _verify(_sig())


def test_signature_is_hex_sha256() -> None:
    sig = _sig()
    assert len(sig) == 64
    int(sig, 16)


@pytest.mark.parametrize(
    "field",
    [
        {"method": "POST"},
        {"key": "audio/0b9e/other"},
        {"content_type": "audio/flac"},
        {"content_length": 101},
    ],
)
def test_tampering_any_signed_field_is_refused(field: dict[str, object]) -> None:
    with pytest.raises(SignatureError) as exc:
        _verify(_sig(), **field)
    assert exc.value.code == "invalid_signature"


def test_tampered_expiry_is_refused() -> None:
    with pytest.raises(SignatureError, match="signature"):
        _verify(_sig(), expires=str(int(NOW) + 120))


def test_other_secret_is_refused() -> None:
    other = upload_signature(b"o" * 32, "PUT", KEY, int(NOW) + 60, "audio/wav", 100)
    with pytest.raises(SignatureError):
        _verify(other)


def test_expired_signature_is_refused() -> None:
    expires = int(NOW) - 1
    with pytest.raises(SignatureError) as exc:
        _verify(_sig(expires=expires), expires=str(expires))
    assert exc.value.code == "upload_url_expired"


def test_expiry_beyond_the_ttl_cap_is_refused() -> None:
    expires = int(NOW) + 301
    with pytest.raises(SignatureError) as exc:
        _verify(_sig(expires=expires), expires=str(expires))
    assert exc.value.code == "upload_url_expired"


@pytest.mark.parametrize("expires", [None, "", "abc", "-5", "1e9"])
def test_malformed_expiry_is_refused(expires: str | None) -> None:
    with pytest.raises(SignatureError):
        _verify(_sig(), expires=expires)


@pytest.mark.parametrize("sig", [None, "", "zz", "é" * 64])
def test_missing_or_malformed_signature_is_refused(sig: str | None) -> None:
    with pytest.raises(SignatureError):
        _verify(sig)


# --- LocalObjectStore -------------------------------------------------------------------------


def _store(root: Path) -> LocalObjectStore:
    return LocalObjectStore(root, SECRET, "http://127.0.0.1:47801/", clock=lambda: NOW)


async def _chunks(parts: Iterable[bytes]) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


def _write(store: LocalObjectStore, key: str, parts: Iterable[bytes], length: int) -> None:
    asyncio.run(store.write_stream(key, _chunks(parts), length))


def test_store_creates_its_root(tmp_path: Path) -> None:
    _store(tmp_path / "a" / "b")
    assert (tmp_path / "a" / "b").is_dir()


def test_presign_put_url_carries_expiry_and_verifiable_signature(tmp_path: Path) -> None:
    store = _store(tmp_path)
    url = store.presign_put(KEY, "audio/wav", 100, 300)
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}" == "http://127.0.0.1:47801"
    assert parts.path == f"/v1/local-storage/{KEY}"
    query = parse_qs(parts.query)
    assert query["expires"] == [str(int(NOW) + 300)]
    store.verify_put(KEY, query["expires"][0], query["sig"][0], "audio/wav", 100)
    with pytest.raises(SignatureError):
        store.verify_put(KEY, query["expires"][0], query["sig"][0], "audio/wav", 99)


def test_presign_put_refuses_ttl_over_five_minutes_and_unsafe_keys(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="300"):
        store.presign_put(KEY, "audio/wav", 100, 301)
    with pytest.raises(InvalidKeyError):
        store.presign_put("../x", "audio/wav", 100, 60)


def test_write_head_read_prefix_delete(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.head(KEY) is None
    _write(store, KEY, [b"RIFF", b"1234", b"WAVE"], 12)
    info = store.head(KEY)
    assert info is not None
    assert (info.size_bytes, info.content_type) == (12, None)
    assert store.read_prefix(KEY, 4) == b"RIFF"
    assert store.read_prefix(KEY, 100) == b"RIFF1234WAVE"
    store.delete(KEY)
    assert store.head(KEY) is None
    store.delete(KEY)  # idempotent, like S3


def test_write_replaces_an_existing_object(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _write(store, KEY, [b"old!"], 4)
    _write(store, KEY, [b"new"], 3)
    assert store.read_prefix(KEY, 10) == b"new"


@pytest.mark.parametrize(
    ("parts", "length"),
    [([b"12345", b"6"], 5), ([b"123"], 5), ([], 1)],
    ids=["overflow", "short", "empty"],
)
def test_size_mismatch_aborts_and_leaves_no_file(
    tmp_path: Path, parts: list[bytes], length: int
) -> None:
    store = _store(tmp_path)
    with pytest.raises(UploadSizeError):
        _write(store, KEY, parts, length)
    assert store.head(KEY) is None
    leftovers = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert leftovers == []


def test_failed_write_keeps_the_previous_object(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _write(store, KEY, [b"good"], 4)
    with pytest.raises(UploadSizeError):
        _write(store, KEY, [b"too long"], 4)
    assert store.read_prefix(KEY, 10) == b"good"


def test_store_methods_reject_unsafe_keys(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for call in (
        lambda: store.head("../x"),
        lambda: store.read_prefix("../x", 1),
        lambda: store.delete("../x"),
        lambda: _write(store, "../x", [b"a"], 1),
    ):
        with pytest.raises(InvalidKeyError):
            call()


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_written_files_are_private_to_the_user(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _write(store, KEY, [b"a"], 1)
    assert (key_path(tmp_path, KEY).stat().st_mode & 0o077) == 0

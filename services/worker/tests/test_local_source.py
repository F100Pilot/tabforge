"""Desktop storage (ADR-0008): key -> path safety and the local audio source."""

from pathlib import Path

import pytest

from tabforge_worker.adapters.local_source import InvalidKeyError, LocalAudioSource, key_path

KEY = "audio/0b9e/4f1c"


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


def _put(root: Path, key: str, data: bytes) -> Path:
    path = key_path(root, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_download_copies_the_file(tmp_path: Path) -> None:
    root = tmp_path / "store"
    src = _put(root, KEY, b"RIFF....WAVE")
    dst = tmp_path / "input"
    LocalAudioSource(root).download(KEY, dst)
    assert dst.read_bytes() == b"RIFF....WAVE"
    assert src.exists()  # the original stays until retention or account deletion


def test_download_of_a_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LocalAudioSource(tmp_path).download(KEY, tmp_path / "input")


def test_delete_is_idempotent(tmp_path: Path) -> None:
    path = _put(tmp_path, KEY, b"x")
    source = LocalAudioSource(tmp_path)
    source.delete(KEY)
    assert not path.exists()
    source.delete(KEY)


def test_source_refuses_unsafe_keys(tmp_path: Path) -> None:
    source = LocalAudioSource(tmp_path / "store")
    secret = _put(tmp_path, "secret", b"x")
    with pytest.raises(InvalidKeyError):
        source.download("../secret", tmp_path / "input")
    with pytest.raises(InvalidKeyError):
        source.delete("../secret")
    assert secret.exists()

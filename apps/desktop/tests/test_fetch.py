import hashlib
import importlib.util
import urllib.error
import zipfile
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "fetch", Path(__file__).resolve().parents[1] / "packaging" / "fetch.py"
)
assert _SPEC and _SPEC.loader
fetch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fetch)

URL = "https://example.invalid/dl/tool-1.0.zip"


def _zip(path: Path) -> str:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("tool-1.0/bin/tool.exe", b"binary")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _spec(sha: str) -> dict[str, object]:
    return {
        "url": URL,
        "sha256": sha,
        "root": "tool-1.0",
        "copy": {"bin/tool.exe": "tool/tool.exe"},
    }


def test_a_file_downloaded_by_hand_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manual = tmp_path / "downloads"
    manual.mkdir()
    sha = _zip(manual / "tool-1.0.zip")

    def no_network(*args: object) -> None:
        raise AssertionError("must not download when the file is already there")

    monkeypatch.setattr(fetch.urllib.request, "urlretrieve", no_network)
    out = tmp_path / "bundle"
    fetch.fetch("tool", _spec(sha), out, tmp_path / "work", manual)
    assert (out / "tool" / "tool.exe").read_bytes() == b"binary"


def test_a_failed_download_says_what_to_fetch_by_hand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def offline(*args: object) -> None:
        raise urllib.error.URLError("[Errno 11001] getaddrinfo failed")

    monkeypatch.setattr(fetch.urllib.request, "urlretrieve", offline)
    manual = tmp_path / "downloads"
    with pytest.raises(fetch.DownloadError) as err:
        fetch.fetch("tool", _spec("0" * 64), tmp_path / "bundle", tmp_path / "work", manual)
    message = str(err.value)
    assert URL in message
    assert str(manual / "tool-1.0.zip") in message


def test_a_hand_downloaded_file_with_the_wrong_hash_is_refused(tmp_path: Path) -> None:
    manual = tmp_path / "downloads"
    manual.mkdir()
    _zip(manual / "tool-1.0.zip")
    with pytest.raises(SystemExit, match="sha256 mismatch"):
        fetch.fetch("tool", _spec("0" * 64), tmp_path / "bundle", tmp_path / "work", manual)

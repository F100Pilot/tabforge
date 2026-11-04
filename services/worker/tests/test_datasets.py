import zipfile
from pathlib import Path
from typing import Any

import pytest

from tabforge_worker.evaluation.datasets import (
    RemoteFile,
    parse_zenodo_record,
    require_license,
    safe_extract,
    verify_md5,
)


def _record(license_id: str | None = "cc-by-4.0") -> dict[str, Any]:
    metadata: dict[str, Any] = {"title": "GuitarSet", "version": "1.1.0"}
    if license_id is not None:
        metadata["license"] = {"id": license_id}
    return {
        "id": 3371780,
        "metadata": metadata,
        "files": [
            {
                "key": "annotation.zip",
                "size": 10,
                "checksum": "md5:0123456789abcdef0123456789abcdef",
                "links": {
                    "self": "https://zenodo.org/api/records/3371780/files/annotation.zip/content"
                },
            }
        ],
    }


def test_parse_zenodo_record() -> None:
    record = parse_zenodo_record(_record())

    assert record.license_id == "cc-by-4.0"
    assert record.version == "1.1.0"
    assert record.files == (
        RemoteFile(
            key="annotation.zip",
            size=10,
            md5="0123456789abcdef0123456789abcdef",
            url="https://zenodo.org/api/records/3371780/files/annotation.zip/content",
        ),
    )


def test_parse_zenodo_record_without_license_has_none() -> None:
    assert parse_zenodo_record(_record(license_id=None)).license_id is None


def test_parse_zenodo_record_rejects_non_md5_checksum() -> None:
    doc = _record()
    doc["files"][0]["checksum"] = "sha1:abc"
    with pytest.raises(ValueError, match="md5"):
        parse_zenodo_record(doc)


def test_require_license_accepts_allowed() -> None:
    require_license(parse_zenodo_record(_record()), allowed={"cc-by-4.0"})


@pytest.mark.parametrize("license_id", [None, "cc-by-nc-4.0"])
def test_require_license_rejects_other(license_id: str | None) -> None:
    with pytest.raises(PermissionError, match="licen"):
        require_license(parse_zenodo_record(_record(license_id)), allowed={"cc-by-4.0"})


def test_verify_md5(tmp_path: Path) -> None:
    f = tmp_path / "x"
    f.write_bytes(b"abc")
    verify_md5(f, "900150983cd24fb0d6963f7d28e17f72")
    with pytest.raises(ValueError, match="md5"):
        verify_md5(f, "0" * 32)


def test_safe_extract_writes_files(tmp_path: Path) -> None:
    archive = tmp_path / "a.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("annotation/00_x.jams", b"{}")

    extracted = safe_extract(archive, tmp_path / "out")

    assert extracted == [tmp_path / "out" / "annotation" / "00_x.jams"]
    assert extracted[0].read_bytes() == b"{}"


@pytest.mark.parametrize("name", ["../evil.txt", "/abs/evil.txt", "a/../../evil.txt"])
def test_safe_extract_rejects_path_traversal(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "a.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(name, b"x")

    with pytest.raises(ValueError, match="outside"):
        safe_extract(archive, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()

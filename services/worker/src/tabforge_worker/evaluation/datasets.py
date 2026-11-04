"""Download helpers for evaluation datasets hosted on Zenodo.

Licence is checked from the record metadata before any download; files are
verified against the md5 published in the record and extracted without allowing
paths outside the destination folder.
"""

import hashlib
import json
import shutil
import urllib.request
import zipfile
from collections.abc import Mapping, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ZENODO_API = "https://zenodo.org/api/records/"
_CHUNK = 1 << 20
_TIMEOUT_S = 60


@dataclass(frozen=True, slots=True)
class RemoteFile:
    key: str
    size: int
    md5: str
    url: str


@dataclass(frozen=True, slots=True)
class ZenodoRecord:
    record_id: int
    title: str
    version: str | None
    license_id: str | None
    files: tuple[RemoteFile, ...]


def parse_zenodo_record(doc: Mapping[str, Any]) -> ZenodoRecord:
    metadata = doc["metadata"]
    license_info = metadata.get("license") or {}
    files = []
    for f in doc["files"]:
        algo, _, digest = str(f["checksum"]).partition(":")
        if algo != "md5" or len(digest) != 32:
            raise ValueError(f"expected md5 checksum for {f['key']}, got {f['checksum']!r}")
        files.append(RemoteFile(str(f["key"]), int(f["size"]), digest, str(f["links"]["self"])))
    return ZenodoRecord(
        record_id=int(doc["id"]),
        title=str(metadata["title"]),
        version=metadata.get("version"),
        license_id=license_info.get("id"),
        files=tuple(files),
    )


def require_license(record: ZenodoRecord, allowed: Set[str]) -> None:
    if record.license_id not in allowed:
        raise PermissionError(
            f"record {record.record_id} licence {record.license_id!r} "
            f"not in allowed {sorted(allowed)}"
        )


def fetch_record(record_id: int) -> tuple[ZenodoRecord, dict[str, Any]]:
    """Return the parsed record and the raw JSON (kept for provenance)."""
    with urllib.request.urlopen(f"{ZENODO_API}{record_id}", timeout=_TIMEOUT_S) as resp:  # noqa: S310 (fixed https URL)
        raw: dict[str, Any] = json.load(resp)
    return parse_zenodo_record(raw), raw


def md5_of(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def verify_md5(path: Path, expected: str) -> None:
    actual = md5_of(path)
    if actual != expected:
        raise ValueError(f"md5 mismatch for {path.name}: {actual} != {expected}")


def download(remote: RemoteFile, dest_dir: Path) -> Path:
    """Download to `dest_dir/<key>` unless an identical file exists; verify md5."""
    if not remote.url.startswith("https://"):
        raise ValueError(f"refusing non-https URL {remote.url!r}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / remote.key
    if target.exists() and target.stat().st_size == remote.size and md5_of(target) == remote.md5:
        return target
    partial = target.with_suffix(target.suffix + ".part")
    with (
        urllib.request.urlopen(remote.url, timeout=_TIMEOUT_S) as resp,  # noqa: S310 (https checked above)
        partial.open("wb") as out,
    ):
        shutil.copyfileobj(resp, out, _CHUNK)
    verify_md5(partial, remote.md5)
    partial.replace(target)
    return target


def safe_extract(archive: Path, dest: Path) -> list[Path]:
    """Extract a zip, rejecting entries that would land outside `dest`."""
    root = dest.resolve()
    written: list[Path] = []
    with zipfile.ZipFile(archive) as zf:
        members = zf.infolist()
        for info in members:
            target = (root / info.filename).resolve()
            if not target.is_relative_to(root) or target == root:
                raise ValueError(f"zip entry {info.filename!r} resolves outside {root}")
        for info in members:
            target = (root / info.filename).resolve()
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out, _CHUNK)
            written.append(target)
    return written

"""Downloads the Windows runtime pieces listed in downloads.json, verifies SHA-256, and lays them
out under build/bundle (ADR-0008). Fails on an unpinned or mismatched hash."""

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(name: str, spec: dict[str, object], out: Path, work: Path) -> None:
    url = str(spec["url"])
    archive = work / f"{name}.zip"
    print(f"{name}: {url}", flush=True)
    urllib.request.urlretrieve(url, archive)  # noqa: S310 - https URLs pinned in downloads.json
    actual = sha256(archive)
    expected = spec.get("sha256")
    if expected is None:
        sys.exit(f"{name}: sha256 not pinned; downloaded file has sha256 {actual}")
    if actual != expected:
        sys.exit(f"{name}: sha256 mismatch: expected {expected}, got {actual}")
    extract = work / name
    with zipfile.ZipFile(archive) as z:
        for member in z.namelist():  # no absolute paths or parent references (zip slip)
            target = (extract / member).resolve()
            if not target.is_relative_to(extract.resolve()):
                sys.exit(f"{name}: unsafe path in archive: {member}")
        z.extractall(extract)  # members checked above (zip slip)
    root = extract / str(spec["root"])
    copies = spec["copy"]
    if not isinstance(copies, dict):
        sys.exit(f"{name}: 'copy' must be an object")
    for source, destination in copies.items():
        src, dst = root / source, out / destination
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=HERE.parent / "build" / "bundle")
    parser.add_argument("--only", nargs="*", help="subset of downloads.json keys")
    args = parser.parse_args()
    specs = {
        k: v
        for k, v in json.loads((HERE / "downloads.json").read_text()).items()
        if not k.startswith("_")
    }
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, spec in specs.items():
            if args.only and name not in args.only:
                continue
            fetch(name, spec, args.out, Path(tmp))


if __name__ == "__main__":
    main()

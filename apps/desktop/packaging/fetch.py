"""Downloads the Windows runtime pieces listed in downloads.json, verifies SHA-256, and lays them
out under build/bundle (ADR-0008). Fails on an unpinned or mismatched hash.

A file already in build/downloads (same name as in the URL) is used instead of downloading it:
the way through when a network (a company one, say) blocks a download site. The SHA-256 is
checked all the same."""

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANUAL_DIR = HERE.parent / "build" / "downloads"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class UnpinnedError(Exception):
    pass


class DownloadError(Exception):
    pass


def fetch(
    name: str, spec: dict[str, object], out: Path, work: Path, manual: Path = MANUAL_DIR
) -> None:
    url = str(spec["url"])
    work.mkdir(parents=True, exist_ok=True)
    local = manual / url.rsplit("/", 1)[-1]
    archive = work / f"{name}.zip"
    if local.is_file():
        print(f"{name}: {local}", flush=True)
        shutil.copy2(local, archive)
    else:
        print(f"{name}: {url}", flush=True)
        try:
            urllib.request.urlretrieve(url, archive)  # noqa: S310 - https URLs pinned in downloads.json
        except (urllib.error.URLError, OSError) as exc:
            raise DownloadError(
                f"Não foi possível descarregar {name} ({exc}).\n"
                f"  Descarregue no browser: {url}\n"
                f"  e guarde o ficheiro como: {local}\n"
                "  Depois corra o start.bat outra vez."
            ) from exc
    actual = sha256(archive)
    expected = spec.get("sha256")
    if expected is None:
        raise UnpinnedError(f"{name}: sha256 not pinned; downloaded file has sha256 {actual}")
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
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, spec in specs.items():
            if args.only and name not in args.only:
                continue
            try:
                fetch(name, spec, args.out, Path(tmp))
            except (UnpinnedError, DownloadError) as exc:  # report every one in one run
                problems.append(str(exc))
    if problems:
        sys.exit("\n".join(problems))


if __name__ == "__main__":
    main()

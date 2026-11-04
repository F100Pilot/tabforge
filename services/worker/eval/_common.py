"""Shared paths and helpers for the eval scripts. Data never lives in git (see .gitignore)."""

import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GUITARSET_RECORD_ID = 3371780
GUITARSET_DIRNAME = "guitarset"


def data_dir(override: Path | None = None) -> Path:
    """`--data-dir`, else $TABFORGE_DATA_DIR, else `<repo>/data` (git-ignored)."""
    if override is not None:
        return override.resolve()
    env = os.environ.get("TABFORGE_DATA_DIR")
    return Path(env).resolve() if env else REPO_ROOT / "data"


def package_versions(names: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in names:
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = "not installed"
    return out

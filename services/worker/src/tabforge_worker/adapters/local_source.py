"""Desktop storage (ADR-0008): uploaded audio as files in the API's local storage folder.

`key_path` duplicates the API's check (tabforge_api.local_storage): the services share only the
score package (ADR-0005), and the function is small enough to keep and test in both places.
"""

import re
import shutil
from pathlib import Path

MAX_KEY_LENGTH = 512
# Allow-list per path segment: no separators, drive letters, NUL/control characters or spaces.
_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")
# Windows device names are special in every folder, with or without an extension.
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


class InvalidKeyError(ValueError):
    """The object key would not map to a file inside the storage folder."""


def key_path(root: Path, key: str) -> Path:
    """Map an object key to a path under `root`, refusing anything that could escape it."""
    if not key or len(key) > MAX_KEY_LENGTH:
        raise InvalidKeyError("empty or overlong key")
    parts = key.split("/")
    for part in parts:
        if (
            not _SEGMENT.fullmatch(part)
            or part.endswith(".")  # also "." and ".."; Windows drops trailing dots
            or part.split(".")[0].upper() in _WINDOWS_RESERVED
        ):
            raise InvalidKeyError("unsafe key segment")
    base = root.resolve()
    path = base.joinpath(*parts).resolve()  # follows symlinks: a link out of the root fails below
    if path == base or not path.is_relative_to(base):
        raise InvalidKeyError("key escapes the storage folder")
    return path


class LocalAudioSource:
    """Same port as S3AudioSource: copy into the job's temp dir; idempotent delete."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def download(self, key: str, dst: Path) -> None:
        shutil.copyfile(key_path(self._root, key), dst)

    def delete(self, key: str) -> None:
        key_path(self._root, key).unlink(missing_ok=True)

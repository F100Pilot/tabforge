"""Where the desktop app keeps its data and finds its bundled tools."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "TabForge"


def data_root(env: dict[str, str] | None = None, platform: str = sys.platform) -> Path:
    """Per-user data folder: %LOCALAPPDATA%\\TabForge on Windows, XDG data dir elsewhere.

    TABFORGE_DATA_DIR overrides both (tests, portable use).
    """
    env = dict(os.environ) if env is None else env
    if override := env.get("TABFORGE_DATA_DIR"):
        return Path(override)
    if platform == "win32":
        base = env.get("LOCALAPPDATA")
        if not base:
            raise RuntimeError("LOCALAPPDATA is not set")
        return Path(base) / APP_NAME
    xdg = env.get("XDG_DATA_HOME") or str(Path(env.get("HOME", "~")).expanduser() / ".local/share")
    return Path(xdg) / "tabforge"


@dataclass(frozen=True, slots=True)
class DataLayout:
    root: Path

    @property
    def pgdata(self) -> Path:
        return self.root / "pgdata"

    @property
    def pg_password_file(self) -> Path:
        return self.root / "pg-password"

    @property
    def audio(self) -> Path:
        return self.root / "audio"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def create(self) -> None:
        for directory in (self.root, self.audio, self.logs):
            directory.mkdir(parents=True, exist_ok=True)


def bundle_root() -> Path:
    """Folder with the bundled runtime (PyInstaller's _MEIPASS when frozen).

    In a source checkout, TABFORGE_BUNDLE_DIR must point at a folder laid out like the bundle.
    """
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    override = os.environ.get("TABFORGE_BUNDLE_DIR")
    if not override:
        raise RuntimeError("not frozen: set TABFORGE_BUNDLE_DIR to a bundle layout")
    return Path(override)


def executable(directory: Path, name: str, platform: str = sys.platform) -> Path:
    return directory / (f"{name}.exe" if platform == "win32" else name)

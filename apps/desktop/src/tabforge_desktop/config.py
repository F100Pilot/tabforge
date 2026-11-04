"""Environment for the embedded API and worker in desktop mode (ADR-0008). Pure: no I/O."""

import json
from dataclasses import dataclass
from pathlib import Path

from tabforge_desktop.paths import DataLayout, executable

WEB_PORT = 47800
API_PORT = 47801
WEB_URL = f"http://127.0.0.1:{WEB_PORT}"
API_URL = f"http://127.0.0.1:{API_PORT}"


@dataclass(frozen=True, slots=True)
class BundleLayout:
    """Runtime pieces shipped next to the launcher (PyInstaller _MEIPASS or a dev folder)."""

    root: Path

    @property
    def migrations(self) -> Path:
        return self.root / "migrations"

    @property
    def pg_bin(self) -> Path:
        return self.root / "pgsql" / "bin"

    @property
    def node(self) -> Path:
        return executable(self.root / "node", "node")

    @property
    def web_server(self) -> Path:
        return self.root / "web" / "server.js"

    @property
    def ffmpeg_dir(self) -> Path:
        return self.root / "ffmpeg"

    @property
    def models(self) -> Path:
        return self.root / "models"


def service_env(
    data: DataLayout,
    bundle: BundleLayout,
    database_url: str,
    launch_token: str,
    upload_secret: str,
    pipeline: str = "real",
) -> dict[str, str]:
    """Variables read by tabforge_api.Settings and tabforge_worker (prefix TABFORGE_)."""
    return {
        "TABFORGE_ENV": "desktop",
        "TABFORGE_DATABASE_URL": database_url,
        "TABFORGE_CORS_ORIGINS": json.dumps([WEB_URL]),
        "TABFORGE_STORAGE_BACKEND": "local",
        "TABFORGE_LOCAL_STORAGE_DIR": str(data.audio),
        "TABFORGE_DESKTOP_LAUNCH_TOKEN": launch_token,
        "TABFORGE_LOCAL_UPLOAD_SECRET": upload_secret,
        "TABFORGE_API_PUBLIC_URL": API_URL,
        "TABFORGE_WEB_BASE_URL": WEB_URL,
        # Plain HTTP on 127.0.0.1: a Secure cookie would never be sent back.
        "TABFORGE_SESSION_COOKIE_SECURE": "false",
        "TABFORGE_WORKER_PIPELINE": pipeline,
        "TABFORGE_FFMPEG": str(executable(bundle.ffmpeg_dir, "ffmpeg")),
        "TABFORGE_FFPROBE": str(executable(bundle.ffmpeg_dir, "ffprobe")),
        # Demucs weights are baked into the bundle; never download at run time.
        "HF_HOME": str(bundle.models / "hf"),
        "HF_HUB_OFFLINE": "1",
        "NUMBA_CACHE_DIR": str(data.root / "cache" / "numba"),
    }


def web_env() -> dict[str, str]:
    """For the Next.js standalone server. NEXT_PUBLIC_* values are baked at build time."""
    return {"PORT": str(WEB_PORT), "HOSTNAME": "127.0.0.1", "NEXT_TELEMETRY_DISABLED": "1"}

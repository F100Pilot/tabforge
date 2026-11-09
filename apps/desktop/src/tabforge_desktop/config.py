"""Environment for the embedded API and worker in desktop mode (ADR-0008). Pure: no I/O."""

import json
from dataclasses import dataclass
from pathlib import Path

from tabforge_desktop.paths import DataLayout, executable


@dataclass(frozen=True, slots=True)
class Ports:
    """Loopback ports chosen at each start, so another program on a fixed port cannot block us.

    The window uses the web origin: the web server forwards /v1 to the API (apps/web/src/proxy.ts),
    so the session cookie stays on one origin. Only the signed audio PUT goes to the API port.
    """

    web: int
    api: int

    def __post_init__(self) -> None:
        if self.web == self.api:
            raise ValueError("web and API need different ports")

    @property
    def web_url(self) -> str:
        return f"http://127.0.0.1:{self.web}"

    @property
    def api_url(self) -> str:
        return f"http://127.0.0.1:{self.api}"


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


def music_dir() -> Path:
    """Where imported MP3s are copied: <home>/Music/TabForge (Windows' Music folder)."""
    return Path.home() / "Music" / "TabForge"


def service_env(
    data: DataLayout,
    bundle: BundleLayout,
    database_url: str,
    launch_token: str,
    upload_secret: str,
    ports: Ports,
    pipeline: str = "real",
) -> dict[str, str]:
    """Variables read by tabforge_api.Settings and tabforge_worker (prefix TABFORGE_)."""
    return {
        "TABFORGE_ENV": "desktop",
        "TABFORGE_DATABASE_URL": database_url,
        "TABFORGE_CORS_ORIGINS": json.dumps([ports.web_url]),
        "TABFORGE_STORAGE_BACKEND": "local",
        "TABFORGE_LOCAL_STORAGE_DIR": str(data.audio),
        "TABFORGE_DESKTOP_LAUNCH_TOKEN": launch_token,
        "TABFORGE_LOCAL_UPLOAD_SECRET": upload_secret,
        # Signed upload URLs go straight to the API (CORS allows PUT from the web origin):
        # Next's proxy buffers request bodies and cuts them at 10 MB, too small for audio.
        "TABFORGE_API_PUBLIC_URL": ports.api_url,
        "TABFORGE_WEB_BASE_URL": ports.web_url,
        # Plain HTTP on 127.0.0.1: a Secure cookie would never be sent back.
        "TABFORGE_SESSION_COOKIE_SECURE": "false",
        "TABFORGE_WORKER_PIPELINE": pipeline,
        "TABFORGE_FFMPEG": str(executable(bundle.ffmpeg_dir, "ffmpeg")),
        "TABFORGE_FFPROBE": str(executable(bundle.ffmpeg_dir, "ffprobe")),
        # YouTube import (ADR-0014): yt-dlp runs YouTube's JavaScript on the bundled Node and
        # keeps a copy of each MP3 in the user's Music folder.
        "TABFORGE_NODE": str(bundle.node),
        "TABFORGE_MUSIC_DIR": str(music_dir()),
        # Demucs weights are baked into the bundle; never download at run time.
        "HF_HOME": str(bundle.models / "hf"),
        "HF_HUB_OFFLINE": "1",
        "NUMBA_CACHE_DIR": str(data.root / "cache" / "numba"),
    }


def web_env(ports: Ports) -> dict[str, str]:
    """For the Next.js standalone server; it reads the API address at run time (proxy.ts)."""
    return {
        "PORT": str(ports.web),
        "HOSTNAME": "127.0.0.1",
        "TABFORGE_API_INTERNAL_URL": ports.api_url,
        "NEXT_TELEMETRY_DISABLED": "1",
    }

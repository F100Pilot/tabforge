"""Audio from a YouTube link, as MP3, with yt-dlp (desktop only, ADR-0014).

yt-dlp needs a JavaScript runtime for YouTube; the desktop bundle's Node is passed in. The
duration is checked before anything is downloaded.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
)
MAX_URL_LENGTH = 2048
SOCKET_TIMEOUT_S = 30
MP3_QUALITY_KBPS = "192"
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)
}


class YoutubeError(Exception):
    """`code`: unavailable (yt-dlp missing), audio_too_long, download_failed."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class Downloaded:
    path: Path
    title: str
    duration_s: float | None


def is_youtube_url(url: str) -> bool:
    """An http(s) link to a YouTube host, without credentials or a port."""
    if not url or len(url) > MAX_URL_LENGTH:
        return False
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme in {"http", "https"}
        and parts.hostname in YOUTUBE_HOSTS
        and parts.username is None
        and port is None
    )


def clean_message(message: str) -> str:
    """yt-dlp's error without the "ERROR:" prefix and the "please report this issue" tail."""
    text = message.removeprefix("ERROR: ").strip()
    return text.split("; please report this issue", 1)[0].strip()


def safe_filename(title: str, limit: int = 120) -> str:
    """A Windows-safe file name (no extension) from a video title."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip().rstrip(". ")
    name = name[:limit].rstrip(". ") or "audio"
    return f"{name}_" if name.upper() in _WINDOWS_RESERVED else name


def download_mp3(
    url: str,
    workdir: Path,
    *,
    ffmpeg: Path | None,
    max_duration_s: float,
    node: Path | None = None,
) -> Downloaded:
    """Download the best audio of one video into `workdir` and convert it to MP3."""
    try:
        import yt_dlp
    except ImportError as exc:  # only the desktop installs it
        raise YoutubeError("unavailable", "yt-dlp is not installed") from exc

    options: dict[str, Any] = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "outtmpl": str(workdir / "audio.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": MP3_QUALITY_KBPS,
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": SOCKET_TIMEOUT_S,
        "retries": 3,
    }
    if ffmpeg is not None:
        options["ffmpeg_location"] = str(ffmpeg)
    if node is not None:
        options["js_runtimes"] = {"node": {"path": str(node)}}

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            if not isinstance(info, dict):
                raise YoutubeError("download_failed", "no video found at this link")
            duration = info.get("duration")
            if isinstance(duration, (int, float)) and duration > max_duration_s:
                raise YoutubeError("audio_too_long", f"{duration:.0f}s > {max_duration_s:.0f}s")
            ydl.process_ie_result(info, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise YoutubeError("download_failed", clean_message(str(exc))) from exc

    path = workdir / "audio.mp3"
    if not path.is_file():
        raise YoutubeError("download_failed", "the audio could not be converted to MP3")
    title = str(info.get("title") or "audio")
    return Downloaded(path, title, float(duration) if isinstance(duration, (int, float)) else None)

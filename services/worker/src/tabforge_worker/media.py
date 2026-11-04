"""ffprobe/ffmpeg wrappers for untrusted audio (threat model T1).

Hardening on top of the container sandbox (non-root, no network in production):
- the demuxer is forced from the declared type, which the API already matched to the file's
  magic bytes, so ffmpeg never auto-detects another format;
- only the `file` protocol is allowed, so a crafted file cannot make ffmpeg fetch anything;
- every call has a timeout, and stdin is closed.
"""

import subprocess
from pathlib import Path

FORMATS = {"audio/wav": "wav", "audio/flac": "flac", "audio/ogg": "ogg", "audio/mpeg": "mp3"}
PROBE_TIMEOUT_S = 30
DECODE_TIMEOUT_S = 300


class MediaError(Exception):
    """The file could not be read as the declared audio format."""


def _demuxer(content_type: str) -> str:
    try:
        return FORMATS[content_type]
    except KeyError:
        raise MediaError(f"unsupported content type {content_type!r}") from None


def _run(cmd: list[str], timeout_s: int) -> str:
    try:
        proc = subprocess.run(  # noqa: S603 (fixed argv, no shell)
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"{cmd[0]} timed out") from exc
    if proc.returncode != 0:
        raise MediaError(f"{cmd[0]} failed: {proc.stderr.strip()[-300:]}")
    return proc.stdout


def probe_duration_s(path: Path, content_type: str) -> float:
    out = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-f",
            _demuxer(content_type),
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            "-i",
            str(path),
        ],
        PROBE_TIMEOUT_S,
    )
    try:
        duration = float(out.strip())
    except ValueError as exc:
        raise MediaError("no duration in file") from exc
    if duration <= 0:
        raise MediaError("empty audio")
    return duration


def normalize_to_wav(
    src: Path, content_type: str, dst: Path, sample_rate: int = 44100, channels: int = 2
) -> None:
    """Decode to 16-bit PCM WAV at the rate Demucs expects (44.1 kHz stereo)."""
    _run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-protocol_whitelist",
            "file",
            "-f",
            _demuxer(content_type),
            "-i",
            str(src),
            "-vn",
            "-ac",
            str(channels),
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(dst),
        ],
        DECODE_TIMEOUT_S,
    )

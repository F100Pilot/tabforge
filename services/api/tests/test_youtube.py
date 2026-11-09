"""YouTube import (ADR-0014): link check, and a real yt-dlp + ffmpeg run on a local file."""

import http.server
import importlib.util
import math
import shutil
import struct
import threading
import wave
from collections.abc import Iterator
from pathlib import Path

import pytest

from tabforge_api.audio_types import AudioType, sniff_audio_type
from tabforge_api.youtube import (
    YoutubeError,
    clean_message,
    download_mp3,
    is_youtube_url,
    safe_filename,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&t=10s",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_youtube_links_are_accepted(url: str) -> None:
    assert is_youtube_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "ftp://www.youtube.com/watch?v=x",
        "https://www.youtube.com.evil.example/watch?v=x",
        "https://evil.example/?u=https://www.youtube.com/watch?v=x",
        "https://user@www.youtube.com/watch?v=x",
        "https://www.youtube.com:8443/watch?v=x",
        "https://127.0.0.1/watch?v=x",
        "file:///etc/passwd",
        "https://www.youtube.com/watch?v=" + "x" * 3000,
    ],
)
def test_other_links_are_refused(url: str) -> None:
    assert not is_youtube_url(url)


def test_yt_dlp_messages_lose_the_report_this_issue_tail() -> None:
    raw = (
        "ERROR: [youtube] abc: Video unavailable; please report this issue on "
        "https://github.com/yt-dlp/yt-dlp/issues?q= , filling out the appropriate issue template. "
        "Confirm you are on the latest version using yt-dlp -U"
    )
    assert clean_message(raw) == "[youtube] abc: Video unavailable"
    assert clean_message("ERROR: plain") == "plain"


def test_safe_filename_keeps_the_title_readable_and_windows_safe() -> None:
    assert (
        safe_filename('AC/DC - Back In Black: "Live" <2024>?')
        == "AC_DC - Back In Black_ _Live_ _2024__"
    )
    assert safe_filename("CON") == "CON_"
    assert safe_filename("   ") == "audio"
    assert len(safe_filename("a" * 500)) <= 120


def _tone(path: Path, seconds: float) -> None:
    rate = 22050
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = (
            int(8000 * math.sin(2 * math.pi * 330 * i / rate)) for i in range(int(rate * seconds))
        )
        w.writeframes(b"".join(struct.pack("<h", f) for f in frames))


@pytest.fixture
def served(tmp_path: Path) -> Iterator[str]:
    """A local web server with one WAV file, as yt-dlp's generic extractor downloads it."""
    root = tmp_path / "site"
    root.mkdir()
    _tone(root / "song.wav", 3.0)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(root), **kwargs)  # type: ignore[arg-type]

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/song.wav"
    server.shutdown()


HAS_YT_DLP = importlib.util.find_spec("yt_dlp") is not None
needs_tools = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or not HAS_YT_DLP, reason="needs ffmpeg and yt-dlp"
)


@needs_tools
def test_download_mp3_converts_with_ffmpeg(served: str, tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    got = download_mp3(
        served, work, ffmpeg=Path(shutil.which("ffmpeg") or "ffmpeg"), max_duration_s=600
    )
    assert got.path.suffix == ".mp3" and got.path.is_file()
    assert sniff_audio_type(got.path.read_bytes()[:16]) is AudioType.MP3
    assert got.title == "song"


@needs_tools
def test_download_mp3_refuses_a_too_long_video_before_downloading(
    served: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import yt_dlp

    real = yt_dlp.YoutubeDL.extract_info

    def with_duration(self: yt_dlp.YoutubeDL, *args: object, **kwargs: object) -> object:
        info = real(self, *args, **kwargs)
        if isinstance(info, dict):
            info["duration"] = 3600
        return info

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", with_duration)
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(YoutubeError) as err:
        download_mp3(
            served, work, ffmpeg=Path(shutil.which("ffmpeg") or "ffmpeg"), max_duration_s=600
        )
    assert err.value.code == "audio_too_long"
    assert not list(work.iterdir())


@pytest.mark.skipif(not HAS_YT_DLP, reason="needs yt-dlp")
def test_a_missing_page_is_a_download_error(tmp_path: Path) -> None:
    with pytest.raises(YoutubeError) as err:
        download_mp3("http://127.0.0.1:9/nothing", tmp_path, ffmpeg=None, max_duration_s=600)
    assert err.value.code == "download_failed"

"""ffmpeg/ffprobe wrappers against the real binaries (skipped when ffmpeg is not installed)."""

import math
import shutil
import struct
import wave
from pathlib import Path

import pytest

from tabforge_worker.media import MediaError, normalize_to_wav, probe_duration_s

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def write_tone(path: Path, seconds: float, freq: float = 329.63, sr: int = 22050) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / sr)))
                for i in range(int(seconds * sr))
            )
        )


def test_probe_duration(tmp_path: Path) -> None:
    src = tmp_path / "a.wav"
    write_tone(src, 1.5)
    assert probe_duration_s(src, "audio/wav") == pytest.approx(1.5, abs=0.01)


def test_normalize_to_44k1_stereo_pcm(tmp_path: Path) -> None:
    src, dst = tmp_path / "a.wav", tmp_path / "out.wav"
    write_tone(src, 1.0)
    normalize_to_wav(src, "audio/wav", dst)
    with wave.open(str(dst)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (44100, 2, 2)
        assert w.getnframes() == pytest.approx(44100, abs=50)


def test_garbage_is_rejected(tmp_path: Path) -> None:
    src = tmp_path / "x.wav"
    src.write_bytes(b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 64)
    with pytest.raises(MediaError):
        probe_duration_s(src, "audio/wav")


def test_declared_format_is_enforced(tmp_path: Path) -> None:
    # A real WAV file declared as FLAC must not be decoded as something else.
    src = tmp_path / "a.flac"
    write_tone(src, 0.5)
    with pytest.raises(MediaError):
        probe_duration_s(src, "audio/flac")


def test_unsupported_declared_type(tmp_path: Path) -> None:
    src = tmp_path / "a.wav"
    write_tone(src, 0.5)
    with pytest.raises(MediaError, match="unsupported"):
        probe_duration_s(src, "video/mp4")

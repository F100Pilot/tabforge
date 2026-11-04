"""ffmpeg/ffprobe executables are configurable (desktop bundle, ADR-0008); no binaries needed."""

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tabforge_worker import media


class FakeRun:
    def __init__(self, stdout: str = "1.5\n") -> None:
        self.argv: list[list[str]] = []
        self.stdout = stdout

    def __call__(self, cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        self.argv.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, self.stdout, "")


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> FakeRun:
    fake = FakeRun()
    monkeypatch.setattr(subprocess, "run", fake)
    return fake


def test_defaults_resolve_from_path(fake_run: FakeRun, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TABFORGE_FFMPEG", raising=False)
    monkeypatch.delenv("TABFORGE_FFPROBE", raising=False)
    media.probe_duration_s(Path("a.wav"), "audio/wav")
    media.normalize_to_wav(Path("a.wav"), "audio/wav", Path("b.wav"))
    assert [argv[0] for argv in fake_run.argv] == ["ffprobe", "ffmpeg"]


def test_environment_overrides_the_executables(
    fake_run: FakeRun, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ffmpeg, ffprobe = tmp_path / "bin" / "ffmpeg.exe", tmp_path / "bin" / "ffprobe.exe"
    monkeypatch.setenv("TABFORGE_FFMPEG", str(ffmpeg))
    monkeypatch.setenv("TABFORGE_FFPROBE", str(ffprobe))
    assert media.probe_duration_s(Path("a.wav"), "audio/wav") == 1.5
    media.normalize_to_wav(Path("a.wav"), "audio/wav", Path("b.wav"))
    assert [argv[0] for argv in fake_run.argv] == [str(ffprobe), str(ffmpeg)]
    # The hardening flags stay in place whatever binary runs.
    assert all("-protocol_whitelist" in argv for argv in fake_run.argv)


def test_empty_override_falls_back_to_path(
    fake_run: FakeRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TABFORGE_FFPROBE", "")
    media.probe_duration_s(Path("a.wav"), "audio/wav")
    assert fake_run.argv[0][0] == "ffprobe"

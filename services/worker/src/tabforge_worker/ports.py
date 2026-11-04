"""Interfaces for third-party pipeline stages (ADR-0002). Implementations land in M1/M2."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class NoteEvent:
    """A transcribed note. Times in seconds; pitch as MIDI number (0-127)."""

    onset_s: float
    offset_s: float
    pitch: int
    velocity: int

    def __post_init__(self) -> None:
        if not 0 <= self.pitch <= 127:
            raise ValueError(f"pitch out of MIDI range: {self.pitch}")
        if not 0 <= self.velocity <= 127:
            raise ValueError(f"velocity out of MIDI range: {self.velocity}")
        if self.onset_s < 0 or self.offset_s <= self.onset_s:
            raise ValueError("require 0 <= onset_s < offset_s")


class Separator(Protocol):
    def isolate_guitar(self, audio: Path, workdir: Path) -> Path: ...


class Transcriber(Protocol):
    def transcribe(self, audio: Path) -> list[NoteEvent]: ...


class BeatTracker(Protocol):
    def beats(self, audio: Path) -> list[float]: ...

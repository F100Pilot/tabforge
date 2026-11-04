"""Internal score format (versioned JSON, ADR-0002) and its conversion to alphaTex.

alphaTex is generated here from a validated Score, never from free user text (threat model T5).
Strings are numbered as in tablature and alphaTex: 1 = highest string, 6 = lowest.
Syntax verified against @coderline/alphatab 1.9.0's AlphaTexImporter.
"""

from fractions import Fraction
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

STRING_COUNT = 6
MAX_FRET = 24
MAX_BARS = 2000

Duration = Literal[1, 2, 4, 8, 16, 32, 64]
Midi = Annotated[int, Field(ge=0, le=127)]

_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScoreNote(_Strict):
    string: int = Field(ge=1, le=STRING_COUNT)
    fret: int = Field(ge=0, le=MAX_FRET)


class ScoreBeat(_Strict):
    """A beat; no notes means a rest."""

    duration: Duration
    notes: list[ScoreNote] = Field(default_factory=list, max_length=STRING_COUNT)

    @model_validator(mode="after")
    def _one_note_per_string(self) -> Self:
        strings = [n.string for n in self.notes]
        if len(strings) != len(set(strings)):
            raise ValueError("a beat has at most one note per string")
        return self


class ScoreBar(_Strict):
    beats: list[ScoreBeat] = Field(min_length=1)


class Score(_Strict):
    schema_version: Literal[1]
    tempo_bpm: int = Field(ge=20, le=400)
    time_signature: tuple[Annotated[int, Field(ge=1, le=32)], Literal[1, 2, 4, 8, 16, 32]]
    # MIDI pitch of each open string, string 1 (highest) first.
    tuning: list[Midi] = Field(min_length=STRING_COUNT, max_length=STRING_COUNT)
    bars: list[ScoreBar] = Field(min_length=1, max_length=MAX_BARS)

    @model_validator(mode="after")
    def _bars_fill_time_signature(self) -> Self:
        numerator, denominator = self.time_signature
        expected = Fraction(numerator, denominator)
        for index, bar in enumerate(self.bars, 1):
            total = sum((Fraction(1, beat.duration) for beat in bar.beats), Fraction(0))
            if total != expected:
                raise ValueError(f"bar {index} lasts {total}, time signature needs {expected}")
        return self


def midi_to_note_name(midi: int) -> str:
    return f"{_NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def _string_literal(text: str) -> str:
    cleaned = "".join(" " if ch < " " or ch == "\x7f" else ch for ch in text)
    return '"' + cleaned.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _beat(beat: ScoreBeat) -> str:
    if not beat.notes:
        return f"r.{beat.duration}"
    notes = [f"{n.fret}.{n.string}" for n in beat.notes]
    if len(notes) == 1:
        return f"{notes[0]}.{beat.duration}"
    return f"({' '.join(notes)}).{beat.duration}"


def to_alphatex(score: Score, title: str) -> str:
    tuning = " ".join(midi_to_note_name(m) for m in score.tuning)
    # Multi-argument metadata in parentheses and no "." separator: the alphaTab 1.9 syntax
    # that its parser accepts without diagnostics (older forms raise AT301/AT400 warnings).
    header = f"\\title {_string_literal(title)} \\tempo {score.tempo_bpm} \\tuning ({tuning})"
    numerator, denominator = score.time_signature
    bars = " ".join(" ".join(_beat(b) for b in bar.beats) + " |" for bar in score.bars)
    return f"{header}\n\\ts ({numerator} {denominator}) {bars}"

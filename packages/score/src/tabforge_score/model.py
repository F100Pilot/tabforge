"""Internal score format (versioned JSON, ADR-0002/ADR-0005) and its conversion to alphaTex.

alphaTex is generated here from a validated Score, never from free user text (threat model T5).
Strings are numbered as in tablature and alphaTex: 1 = highest string, 6 = lowest.
Syntax verified against @coderline/alphatab 1.9.0's AlphaTexImporter: `{d}` dotted beat,
`{tu 3}` triplet, `-` in place of the fret for a tied note, metadata arguments in parentheses.

Versions: v1 has plain durations only; v2 adds dots, triplets, ties and warnings. v1 documents
are valid v2 documents (all new fields have defaults), so one model reads both.
"""

from fractions import Fraction
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

STRING_COUNT = 6
MAX_FRET = 24
MAX_BARS = 2000
MAX_WARNINGS = 1000

Duration = Literal[1, 2, 4, 8, 16, 32, 64]
Midi = Annotated[int, Field(ge=0, le=127)]
WarningCode = Literal["out_of_range", "too_many_notes"]

_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_TRIPLET_GROUP = 3


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScoreNote(_Strict):
    string: int = Field(ge=1, le=STRING_COUNT)
    fret: int = Field(ge=0, le=MAX_FRET)
    # Continues the note on the same string and fret of the previous beat (no new attack).
    tie: bool = False


class ScoreBeat(_Strict):
    """A beat; no notes means a rest."""

    duration: Duration
    dots: Literal[0, 1] = 0
    tuplet: Literal[3] | None = None
    notes: list[ScoreNote] = Field(default_factory=list, max_length=STRING_COUNT)

    @model_validator(mode="after")
    def _check(self) -> Self:
        strings = [n.string for n in self.notes]
        if len(strings) != len(set(strings)):
            raise ValueError("a beat has at most one note per string")
        if self.tuplet is not None and self.dots:
            raise ValueError("dotted triplets are not supported")
        return self


class ScoreBar(_Strict):
    beats: list[ScoreBeat] = Field(min_length=1)


class ScoreWarning(_Strict):
    """A transcribed note that could not be placed (US-02: marked, not silently dropped)."""

    bar: int = Field(ge=1)
    code: WarningCode
    pitch: Midi | None = None


def beat_value(beat: ScoreBeat) -> Fraction:
    """Length of a beat as a fraction of a whole note."""
    value = Fraction(1, beat.duration)
    if beat.dots:
        value *= Fraction(3, 2)
    if beat.tuplet == _TRIPLET_GROUP:
        value *= Fraction(2, 3)
    return value


class Score(_Strict):
    schema_version: Literal[1, 2]
    tempo_bpm: int = Field(ge=20, le=400)
    time_signature: tuple[Annotated[int, Field(ge=1, le=32)], Literal[1, 2, 4, 8, 16, 32]]
    # MIDI pitch of each open string, string 1 (highest) first.
    tuning: list[Midi] = Field(min_length=STRING_COUNT, max_length=STRING_COUNT)
    bars: list[ScoreBar] = Field(min_length=1, max_length=MAX_BARS)
    warnings: list[ScoreWarning] = Field(default_factory=list, max_length=MAX_WARNINGS)

    @model_validator(mode="after")
    def _check(self) -> Self:
        numerator, denominator = self.time_signature
        expected = Fraction(numerator, denominator)
        for index, bar in enumerate(self.bars, 1):
            _check_triplet_groups(index, bar)  # structure first: clearer error than the length
            total = sum((beat_value(b) for b in bar.beats), Fraction(0))
            if total != expected:
                raise ValueError(f"bar {index} lasts {total}, time signature needs {expected}")
        _check_ties(self.bars)
        for warning in self.warnings:
            if warning.bar > len(self.bars):
                raise ValueError(f"warning refers to bar {warning.bar}, score has {len(self.bars)}")
        return self


def _check_triplet_groups(index: int, bar: ScoreBar) -> None:
    run: list[ScoreBeat] = []
    for beat in [*bar.beats, None]:
        if beat is not None and beat.tuplet is not None:
            run.append(beat)
            continue
        if run and (
            len(run) % _TRIPLET_GROUP
            or any(
                len({b.duration for b in run[i : i + _TRIPLET_GROUP]}) != 1
                for i in range(0, len(run), _TRIPLET_GROUP)
            )
        ):
            raise ValueError(f"bar {index}: triplets must be groups of three equal beats")
        run = []


def _check_ties(bars: list[ScoreBar]) -> None:
    previous: dict[int, int] = {}  # string -> fret sounding at the end of the previous beat
    for index, bar in enumerate(bars, 1):
        for beat in bar.beats:
            for note in beat.notes:
                if note.tie and previous.get(note.string) != note.fret:
                    raise ValueError(
                        f"bar {index}: tie on string {note.string} does not continue the "
                        "previous note on that string and fret"
                    )
            previous = {n.string: n.fret for n in beat.notes}


def midi_to_note_name(midi: int) -> str:
    return f"{_NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def _string_literal(text: str) -> str:
    cleaned = "".join(" " if ch < " " or ch == "\x7f" else ch for ch in text)
    return '"' + cleaned.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _note(note: ScoreNote) -> str:
    return f"{'-' if note.tie else note.fret}.{note.string}"


def _beat(beat: ScoreBeat) -> str:
    effects = []
    if beat.dots:
        effects.append("d")
    if beat.tuplet:
        effects.append(f"tu {beat.tuplet}")
    suffix = f"{{{' '.join(effects)}}}" if effects else ""
    if not beat.notes:
        return f"r.{beat.duration}{suffix}"
    notes = [_note(n) for n in beat.notes]
    body = notes[0] if len(notes) == 1 else f"({' '.join(notes)})"
    return f"{body}.{beat.duration}{suffix}"


def to_alphatex(score: Score, title: str) -> str:
    tuning = " ".join(midi_to_note_name(m) for m in score.tuning)
    # Multi-argument metadata in parentheses and no "." separator: the alphaTab 1.9 syntax
    # that its parser accepts without diagnostics (older forms raise AT301/AT400 warnings).
    header = f"\\title {_string_literal(title)} \\tempo {score.tempo_bpm} \\tuning ({tuning})"
    numerator, denominator = score.time_signature
    bars = " ".join(" ".join(_beat(b) for b in bar.beats) + " |" for bar in score.bars)
    return f"{header}\n\\ts ({numerator} {denominator}) {bars}"

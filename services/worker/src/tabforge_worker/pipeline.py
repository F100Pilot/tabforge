"""Pipeline stages (docs/architecture.md). M1 runs stubs; real stages arrive in M2."""

from enum import StrEnum
from typing import Any


class Stage(StrEnum):
    SEPARATING = "separating"
    TRANSCRIBING = "transcribing"
    ARRANGING = "arranging"


def plan_stages(source_kind: str) -> list[Stage]:
    """Stages for an input; an isolated guitar stem skips source separation (ADR-0002)."""
    if source_kind == "mix":
        return [Stage.SEPARATING, Stage.TRANSCRIBING, Stage.ARRANGING]
    if source_kind == "guitar_stem":
        return [Stage.TRANSCRIBING, Stage.ARRANGING]
    raise ValueError(f"unknown source_kind: {source_kind!r}")


# Fixed score written by the M1 stub pipeline: an E minor pentatonic phrase in 4/4.
# Format: tabforge_api.score.Score v1 (strings 1 = highest .. 6 = lowest).
STUB_SCORE: dict[str, Any] = {
    "schema_version": 1,
    "tempo_bpm": 96,
    "time_signature": [4, 4],
    "tuning": [64, 59, 55, 50, 45, 40],
    "bars": [
        {
            "beats": [
                {"duration": 8, "notes": [{"string": 6, "fret": 0}]},
                {"duration": 8, "notes": [{"string": 6, "fret": 3}]},
                {"duration": 8, "notes": [{"string": 5, "fret": 0}]},
                {"duration": 8, "notes": [{"string": 5, "fret": 2}]},
                {"duration": 8, "notes": [{"string": 4, "fret": 0}]},
                {"duration": 8, "notes": [{"string": 4, "fret": 2}]},
                {"duration": 4, "notes": [{"string": 3, "fret": 0}]},
            ]
        },
        {
            "beats": [
                {"duration": 4, "notes": [{"string": 6, "fret": 0}, {"string": 5, "fret": 2}]},
                {"duration": 4, "notes": []},
                {"duration": 2, "notes": [{"string": 1, "fret": 0}, {"string": 2, "fret": 0}]},
            ]
        },
    ],
}

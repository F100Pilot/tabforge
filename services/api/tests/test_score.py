from typing import Any

import pytest
from pydantic import ValidationError

from tabforge_api.score import Score, midi_to_note_name, to_alphatex


def _score(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": 1,
        "tempo_bpm": 90,
        "time_signature": [4, 4],
        "tuning": [64, 59, 55, 50, 45, 40],
        "bars": [
            {
                "beats": [
                    {"duration": 4, "notes": [{"string": 6, "fret": 0}]},
                    {"duration": 4, "notes": [{"string": 5, "fret": 3}]},
                    {"duration": 4, "notes": [{"string": 1, "fret": 0}, {"string": 2, "fret": 1}]},
                    {"duration": 4, "notes": []},
                ]
            }
        ],
    }
    base.update(overrides)
    return base


def test_valid_score_parses() -> None:
    score = Score.model_validate(_score())
    assert len(score.bars) == 1
    assert score.bars[0].beats[2].notes[1].fret == 1


def test_to_alphatex_writes_header_bars_notes_chords_and_rests() -> None:
    tex = to_alphatex(Score.model_validate(_score()), title="Riff")
    assert tex == (
        '\\title "Riff" \\tempo 90 \\tuning (E4 B3 G3 D3 A2 E2)\n'
        "\\ts (4 4) 0.6.4 3.5.4 (0.1 1.2).4 r.4 |"
    )


def test_to_alphatex_escapes_title_quotes_backslashes_and_controls() -> None:
    tex = to_alphatex(Score.model_validate(_score()), title='a "q" \\ b\nc')
    assert tex.startswith('\\title "a \\"q\\" \\\\ b c" ')


def test_to_alphatex_separates_multiple_bars() -> None:
    bar = {"beats": [{"duration": 1, "notes": [{"string": 6, "fret": 5}]}]}
    tex = to_alphatex(Score.model_validate(_score(bars=[bar, bar])), title="x")
    assert tex.endswith("\\ts (4 4) 5.6.1 | 5.6.1 |")


@pytest.mark.parametrize(("midi", "name"), [(64, "E4"), (40, "E2"), (61, "C#4"), (0, "C-1")])
def test_midi_to_note_name(midi: int, name: str) -> None:
    assert midi_to_note_name(midi) == name


def test_bar_must_fill_time_signature() -> None:
    short_bar = {"beats": [{"duration": 2, "notes": []}]}
    with pytest.raises(ValidationError, match="bar 1"):
        Score.model_validate(_score(bars=[short_bar]))


def test_bar_accepts_mixed_durations_that_sum_to_measure() -> None:
    bar = {
        "beats": [
            {"duration": 2, "notes": []},
            {"duration": 8, "notes": []},
            {"duration": 8, "notes": []},
            {"duration": 4, "notes": []},
        ]
    }
    Score.model_validate(_score(bars=[bar], time_signature=[4, 4]))
    Score.model_validate(_score(bars=[{"beats": bar["beats"][1:]}], time_signature=[2, 4]))


def test_one_note_per_string_per_beat() -> None:
    beat = {"duration": 1, "notes": [{"string": 1, "fret": 0}, {"string": 1, "fret": 3}]}
    with pytest.raises(ValidationError, match="string"):
        Score.model_validate(_score(bars=[{"beats": [beat]}]))


@pytest.mark.parametrize(
    "note",
    [
        {"string": 0, "fret": 0},
        {"string": 7, "fret": 0},
        {"string": 1, "fret": 25},
        {"string": 1, "fret": -1},
    ],
)
def test_note_bounds(note: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Score.model_validate(_score(bars=[{"beats": [{"duration": 1, "notes": [note]}]}]))


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": 2},
        {"tempo_bpm": 0},
        {"tuning": [64, 59, 55, 50, 45]},
        {"tuning": [64, 59, 55, 50, 45, 128]},
        {"time_signature": [4, 3]},
        {"bars": []},
        {"extra_field": 1},
    ],
)
def test_invalid_scores_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Score.model_validate(_score(**overrides))


def test_beat_duration_must_be_power_of_two() -> None:
    bar = {"beats": [{"duration": 3, "notes": []}]}
    with pytest.raises(ValidationError):
        Score.model_validate(_score(bars=[bar]))

"""Re-fretting an existing tab with other Viterbi weights (ADR-0016)."""

import random
from typing import Any

from tabforge_score import Score
from tabforge_score.compare import score_events
from tabforge_score.fretting import DEFAULT_WEIGHTS, Weights, assign_positions
from tabforge_score.refret import refretted_score

STANDARD = [64, 59, 55, 50, 45, 40]  # string 1 (high E) first
HIGH = Weights(1.0, -0.1, 0.1, 0.0)  # prefers frets up the neck


def _score(bars: list[list[dict[str, Any]]], tuning: list[int] = STANDARD) -> Score:
    return Score.model_validate(
        {
            "schema_version": 2,
            "tempo_bpm": 100,
            "time_signature": [4, 4],
            "tuning": tuning,
            "bars": [{"beats": beats} for beats in bars],
        }
    )


def _q(*notes: tuple[int, int] | tuple[int, int, bool]) -> dict[str, Any]:
    return {
        "duration": 4,
        "notes": [{"string": n[0], "fret": n[1], "tie": len(n) == 3 and bool(n[2])} for n in notes],
    }


def _pitches(score: Score, track: int = 0) -> list[tuple[float, int]]:
    return [(float(e.onset), e.pitch) for e in score_events(score, track)]


def test_a_line_takes_the_positions_the_weights_choose() -> None:
    # A-B-C#-D played high on the D string; the default weights play it in first position.
    score = _score([[_q((4, 7)), _q((4, 9)), _q((4, 11)), _q((4, 12))]])
    pitches = [STANDARD[3] + f for f in (7, 9, 11, 12)]
    expected = assign_positions([((p,), (90,)) for p in pitches], STANDARD, DEFAULT_WEIGHTS)

    result, changed = refretted_score(score, DEFAULT_WEIGHTS)

    got = [(e.string, e.fret) for e in score_events(result)]
    assert got == [(f.positions[0].string, f.positions[0].fret) for f in expected]
    assert changed == sum(g != (4, f) for g, f in zip(got, (7, 9, 11, 12), strict=True))
    assert changed > 0
    assert _pitches(result) == _pitches(score)


def test_nothing_changes_when_the_tab_already_follows_the_weights() -> None:
    score = _score([[_q((5, 0)), _q((5, 2)), _q((4, 0)), _q((4, 2))]])
    result, changed = refretted_score(score, DEFAULT_WEIGHTS)
    assert changed == 0
    assert result == score


def test_a_tied_note_moves_with_the_note_it_continues() -> None:
    # A2 held over the bar line on string 6 fret 5; the default weights play it open (string 5).
    score = _score([[_q((6, 5)), _q((6, 5, True)), _q((6, 5, True)), _q((6, 5, True))]])
    result, changed = refretted_score(score, DEFAULT_WEIGHTS)
    beats = result.bars[0].beats
    assert [(n.string, n.fret, n.tie) for b in beats for n in b.notes] == [
        (5, 0, False),
        (5, 0, True),
        (5, 0, True),
        (5, 0, True),
    ]
    assert changed == 1  # one attacked note


def test_a_held_note_that_would_share_a_string_keeps_the_original_positions() -> None:
    # E3 on string 5 fret 7, held into beat 2 where D3 is played on the open D string. The
    # weights move E3 to string 4 fret 2 and keep D3 open on string 4: both on string 4 in beat
    # 2, so those events stay as they were.
    score = _score([[_q((5, 7)), _q((5, 7, True), (4, 0)), _q(), _q()]])
    result, changed = refretted_score(score, DEFAULT_WEIGHTS)
    assert changed == 0
    assert result == score


def test_every_track_is_refretted_in_its_own_tuning() -> None:
    drop_d = [64, 59, 55, 50, 45, 38]
    score = Score.model_validate(
        {
            "schema_version": 3,
            "tempo_bpm": 100,
            "time_signature": [4, 4],
            "tracks": [
                {"name": "Lead", "tuning": STANDARD, "bars": [{"beats": [_q((4, 12))] * 4}]},
                {"name": "Rhythm", "tuning": drop_d, "bars": [{"beats": [_q((6, 7))] * 4}]},
            ],
        }
    )
    result, changed = refretted_score(score, DEFAULT_WEIGHTS)
    assert changed == 8
    assert _pitches(result, 0) == _pitches(score, 0)
    assert _pitches(result, 1) == _pitches(score, 1)
    assert result.tracks[1].tuning == drop_d


def test_random_tabs_stay_valid_with_the_same_notes() -> None:
    rng = random.Random(7)  # noqa: S311 (test data)
    for _ in range(60):
        bars = []
        held: dict[int, int] = {}
        for _bar in range(4):
            beats = []
            for _beat in range(4):
                notes: list[tuple[int, int] | tuple[int, int, bool]] = []
                used: set[int] = set()
                for string, fret in list(held.items()):
                    if rng.random() < 0.5:
                        notes.append((string, fret, True))
                        used.add(string)
                for _n in range(rng.choice((0, 1, 1, 2, 3))):
                    string = rng.randint(1, 6)
                    if string not in used:
                        used.add(string)
                        notes.append((string, rng.randint(0, 9)))
                held = {n[0]: n[1] for n in notes}
                beats.append(_q(*notes))
            bars.append(beats)
        score = _score(bars)
        for weights in (DEFAULT_WEIGHTS, HIGH, Weights(1.0, 0.4, 2.0, 1.0)):
            result, changed = refretted_score(score, weights)
            assert _pitches(result) == _pitches(score)
            assert [[len(b.notes) for b in bar.beats] for bar in result.bars] == [
                [len(b.notes) for b in bar.beats] for bar in score.bars
            ]
            assert [n.tie for bar in result.bars for b in bar.beats for n in b.notes] == [
                n.tie for bar in score.bars for b in bar.beats for n in b.notes
            ]
            assert (changed == 0) == (result == score)

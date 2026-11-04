import pytest
from tabforge_score import to_alphatex

from tabforge_worker.arrange.fretting import Fretted, Position
from tabforge_worker.arrange.layout import Piece, build_score, decompose
from tabforge_worker.arrange.quantize import Event, Quantized

STANDARD = (64, 59, 55, 50, 45, 40)


@pytest.mark.parametrize(
    ("start", "length", "expected"),
    [
        (0, 12, [Piece(12, 4)]),
        (0, 18, [Piece(18, 4, dots=1)]),
        (0, 48, [Piece(48, 1)]),
        (0, 30, [Piece(24, 2), Piece(6, 8)]),
        (12, 24, [Piece(24, 2)]),
        (12, 36, [Piece(36, 2, dots=1)]),
        (6, 12, [Piece(12, 4)]),
        (9, 6, [Piece(3, 16), Piece(3, 16)]),
        (3, 3, [Piece(3, 16)]),
    ],
)
def test_decompose_binary(start: int, length: int, expected: list[Piece]) -> None:
    assert decompose(start, length, frozenset()) == expected


def test_decompose_triplet_beat_uses_triplet_eighths() -> None:
    assert decompose(12, 8, frozenset({1})) == [Piece(4, 8, tuplet=3), Piece(4, 8, tuplet=3)]


def test_decompose_splits_at_triplet_beat_edges() -> None:
    # quarter from tick 6 into triplet beat 1: eighth (binary) then triplet eighths
    assert decompose(6, 10, frozenset({1})) == [
        Piece(6, 8),
        Piece(4, 8, tuplet=3),
    ]


def _q(*events: Event, triplets: frozenset[int] = frozenset(), total: int = 48) -> Quantized:
    return Quantized(events, triplets, total, 96)


def _f(*positions: tuple[int, int], pitches: tuple[int, ...] = (), dropped=()) -> Fretted:  # type: ignore[no-untyped-def]
    pos = tuple(Position(s, f) for s, f in positions)
    return Fretted(pitches or tuple(range(len(pos))), pos, dropped)


def test_quarters_in_one_bar() -> None:
    q = _q(Event(0, 12, (40,)), Event(12, 24, (43,)), Event(24, 36, (45,)), Event(36, 48, (47,)))
    score = build_score(q, [_f((6, 0)), _f((6, 3)), _f((5, 0)), _f((5, 2))], STANDARD)
    assert score.schema_version == 2
    assert score.tempo_bpm == 96
    assert to_alphatex(score, "t").endswith("\\ts (4 4) 0.6.4 3.6.4 0.5.4 2.5.4 |")


def test_leading_and_trailing_rests_fill_the_bar() -> None:
    q = _q(Event(12, 24, (40,)))
    score = build_score(q, [_f((6, 0))], STANDARD)
    assert to_alphatex(score, "t").endswith("r.4 0.6.4 r.2 |")


def test_note_across_barline_is_tied() -> None:
    q = _q(Event(36, 60, (40, 47)), total=96)
    score = build_score(q, [_f((6, 0), (5, 2))], STANDARD)
    assert to_alphatex(score, "t").endswith("r.2{d} (0.6 2.5).4 | (-.6 -.5).4 r.2{d} |")


def test_triplet_beat() -> None:
    q = _q(
        Event(0, 4, (40,)),
        Event(4, 8, (42,)),
        Event(8, 12, (43,)),
        Event(12, 48, (45,)),
        triplets=frozenset({0}),
    )
    score = build_score(q, [_f((6, 0)), _f((6, 2)), _f((6, 3)), _f((5, 0))], STANDARD)
    assert to_alphatex(score, "t").endswith("0.6.8{tu 3} 2.6.8{tu 3} 3.6.8{tu 3} 0.5.2{d} |")


def test_empty_quantized_gives_one_rest_bar() -> None:
    score = build_score(_q(), [], STANDARD)
    assert to_alphatex(score, "t").endswith("r.1 |")


def test_event_with_all_notes_dropped_becomes_rest() -> None:
    q = _q(Event(0, 48, (20,)))
    score = build_score(q, [Fretted((), (), ((20, "out_of_range"),))], STANDARD)
    assert to_alphatex(score, "t").endswith("r.1 |")
    assert [(w.bar, w.code, w.pitch) for w in score.warnings] == [(1, "out_of_range", 20)]


def test_warnings_carry_bar_numbers() -> None:
    q = _q(Event(0, 48, (40,)), Event(48, 96, (40, 41)), total=96)
    fretted = [_f((6, 0)), _f((6, 0), pitches=(40,), dropped=((41, "too_many_notes"),))]
    score = build_score(q, fretted, STANDARD)
    assert [(w.bar, w.code) for w in score.warnings] == [(2, "too_many_notes")]


def test_tuning_is_written_high_string_first() -> None:
    assert build_score(_q(), [], STANDARD).tuning == list(STANDARD)


def test_mismatched_lengths_are_rejected() -> None:
    with pytest.raises(ValueError, match="one Fretted per event"):
        build_score(_q(Event(0, 12, (40,))), [], STANDARD)

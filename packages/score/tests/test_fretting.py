from tabforge_score.fretting import Position, assign_positions, candidate_positions

STANDARD = (64, 59, 55, 50, 45, 40)  # string 1 (high E) .. string 6 (low E)


def _line(*pitches: int) -> list[tuple[tuple[int, ...], tuple[int, ...]]]:
    return [((p,), (90,)) for p in pitches]


def test_candidate_positions_cover_every_string_in_range() -> None:
    assert candidate_positions(52, STANDARD) == [Position(4, 2), Position(5, 7), Position(6, 12)]
    assert candidate_positions(40, STANDARD) == [Position(6, 0)]
    assert candidate_positions(88, STANDARD) == [Position(1, 24)]
    assert candidate_positions(39, STANDARD) == []
    assert candidate_positions(89, STANDARD) == []


def test_open_position_scale_stays_in_first_position() -> None:
    result = assign_positions(_line(40, 42, 43, 45, 47, 48, 50), STANDARD)
    positions = [r.positions[0] for r in result]
    assert positions == [
        Position(6, 0),
        Position(6, 2),
        Position(6, 3),
        Position(5, 0),
        Position(5, 2),
        Position(5, 3),
        Position(4, 0),
    ]


def test_high_melody_stays_in_one_area() -> None:
    result = assign_positions(_line(72, 74, 76, 74, 72), STANDARD)
    frets = [r.positions[0].fret for r in result]
    assert max(frets) - min(frets) <= 5
    assert {r.positions[0].string for r in result} <= {1, 2}


def test_open_e_minor_chord() -> None:
    (result,) = assign_positions([((40, 47, 52, 55, 59, 64), (90,) * 6)], STANDARD)
    assert sorted(result.positions, key=lambda p: p.string) == [
        Position(1, 0),
        Position(2, 0),
        Position(3, 0),
        Position(4, 2),
        Position(5, 2),
        Position(6, 0),
    ]
    assert result.dropped == ()


def test_chord_keeps_hand_span_within_four_frets() -> None:
    (result,) = assign_positions([((48, 52, 55, 60), (90,) * 4)], STANDARD)  # C major triad
    fretted = [p.fret for p in result.positions if p.fret > 0]
    assert max(fretted) - min(fretted) <= 4


def test_repeated_note_keeps_its_position() -> None:
    result = assign_positions(_line(57, 57, 57), STANDARD)
    assert len({r.positions[0] for r in result}) == 1


def test_stays_near_previous_hand_position() -> None:
    result = assign_positions(_line(45, 52, 45), STANDARD)
    assert result[1].positions[0] == Position(4, 2)


def test_out_of_range_pitch_is_dropped_with_warning() -> None:
    (result,) = assign_positions([((30, 52), (90, 90))], STANDARD)
    assert result.pitches == (52,)
    assert result.dropped == ((30, "out_of_range"),)


def test_notes_competing_for_one_string_drop_the_quietest() -> None:
    # E2 and F2 can only be played on the low E string.
    (result,) = assign_positions([((40, 41), (100, 30))], STANDARD)
    assert result.pitches == (40,)
    assert result.dropped == ((41, "too_many_notes"),)


def test_seven_note_chord_is_reduced_to_six() -> None:
    pitches = (40, 45, 50, 55, 59, 64, 69)
    (result,) = assign_positions([(pitches, (90, 90, 90, 90, 90, 90, 10))], STANDARD)
    assert len(result.positions) == 6
    assert result.dropped == ((69, "too_many_notes"),)


def test_positions_follow_pitch_order() -> None:
    (result,) = assign_positions([((55, 40), (90, 90))], STANDARD)
    assert result.pitches == (55, 40)
    assert [STANDARD[p.string - 1] + p.fret for p in result.positions] == [55, 40]


def test_empty_input() -> None:
    assert assign_positions([], STANDARD) == []

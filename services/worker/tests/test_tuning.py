from tabforge_worker.arrange.fretting import path_cost, prepare_events
from tabforge_worker.arrange.tuning import CANDIDATES, STANDARD, detect_tuning
from tabforge_worker.ports import NoteEvent

D_STANDARD = tuple(t - 2 for t in STANDARD)
DROP_D = (*STANDARD[:5], 38)
B_STANDARD = tuple(t - 5 for t in STANDARD)


def _notes(*chords: tuple[int, ...], step: float = 0.25) -> list[NoteEvent]:
    """One chord (or single note) every `step` seconds."""
    return [
        NoteEvent(onset_s=i * step, offset_s=i * step + step * 0.9, pitch=p, velocity=90)
        for i, chord in enumerate(chords)
        for p in chord
    ]


def _riff(low: int, times: int = 20) -> list[tuple[int, ...]]:
    """Chugging on the lowest note with a melody above it."""
    return [(low,), (low,), (low + 3,), (low + 5,), (low + 7,), (low + 10,)] * times


def test_candidates_are_named_and_unique() -> None:
    names = [c.name for c in CANDIDATES]
    assert names[0] == "E standard"
    assert len(set(names)) == len(names)
    assert len({c.tuning for c in CANDIDATES}) == len(CANDIDATES)


def test_no_notes_is_e_standard() -> None:
    guess = detect_tuning([])
    assert (guess.name, guess.tuning, guess.floor) == ("E standard", STANDARD, None)


def test_music_above_low_e_stays_in_e_standard() -> None:
    assert detect_tuning(_notes(*_riff(40))).name == "E standard"


def test_a_few_stray_low_notes_do_not_change_the_tuning() -> None:
    # Bass bleed or octave errors: 1 % of the notes below E2.
    notes = _notes(*_riff(40, times=40), *[(36,)] * 2)
    assert detect_tuning(notes).name == "E standard"


def test_a_low_b_riff_is_b_standard() -> None:
    guess = detect_tuning(_notes(*_riff(35)))
    assert (guess.name, guess.tuning, guess.floor) == ("B standard", B_STANDARD, 35)


def test_a_low_e_flat_riff_is_e_flat_standard() -> None:
    assert detect_tuning(_notes(*_riff(39))).name == "Eb standard"


def test_one_finger_power_chords_on_low_d_are_drop_d() -> None:
    # D5, F5, G5, A5 as root-fifth-octave: one finger across three strings in Drop D.
    chords = [(r, r + 7, r + 12) for r in (38, 41, 43, 45)] * 12
    guess = detect_tuning(_notes(*chords))
    assert (guess.name, guess.tuning) == ("Drop D", DROP_D)


def test_low_d_with_fourths_on_the_low_strings_is_d_standard() -> None:
    # Root + fourth on strings 6-5 is one fret in D standard, a stretch in Drop D.
    chords = [(r, r + 5) for r in (38, 40, 41, 43)] * 12 + [(38,)] * 20
    guess = detect_tuning(_notes(*chords))
    assert (guess.name, guess.tuning) == ("D standard", D_STANDARD)


def test_notes_below_the_lowest_candidate_are_ignored() -> None:
    # Sub-bass far below any six-string tuning (A1 = 33) is not guitar.
    notes = _notes(*_riff(40, times=20), *[(28,)] * 30)
    assert detect_tuning(notes).name == "E standard"


def test_path_cost_is_lower_for_the_tuning_that_fits_the_shapes() -> None:
    chords = [((38, 45, 50), (90, 90, 90))] * 8
    drop = path_cost(prepare_events(chords, DROP_D))
    standard = path_cost(prepare_events(chords, D_STANDARD))
    assert drop < standard

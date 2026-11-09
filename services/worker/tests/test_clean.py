from tabforge_worker.arrange.clean import QUIET_RATIO, WINDOW_S, clean_notes
from tabforge_worker.ports import NoteEvent


def _n(onset: float, pitch: int, velocity: int) -> NoteEvent:
    return NoteEvent(onset_s=onset, offset_s=onset + 0.2, pitch=pitch, velocity=velocity)


def test_no_notes() -> None:
    assert clean_notes([]) == []


def test_notes_of_similar_strength_are_all_kept() -> None:
    notes = [_n(i * 0.25, 60 + i % 5, 80 + i % 7) for i in range(40)]
    assert clean_notes(notes) == notes


def test_much_quieter_notes_are_removed() -> None:
    loud = [_n(i * 0.25, 60, 90) for i in range(40)]
    faint = [_n(i * 0.25 + 0.1, 72, int(90 * QUIET_RATIO) - 5) for i in range(5)]
    assert clean_notes(loud + faint) == loud


def test_the_threshold_follows_the_local_dynamics() -> None:
    # A quiet intro and a loud chorus: the intro is judged against itself, not the chorus.
    intro = [_n(i * 0.25, 60, 40) for i in range(40)]
    start = 40 * 0.25 + WINDOW_S
    chorus = [_n(start + i * 0.25, 64, 110) for i in range(40)]
    assert clean_notes(intro + chorus) == intro + chorus


def test_order_is_by_onset() -> None:
    notes = [_n(1.0, 60, 90), _n(0.0, 62, 90), _n(0.5, 64, 90)]
    assert [n.onset_s for n in clean_notes(notes)] == [0.0, 0.5, 1.0]

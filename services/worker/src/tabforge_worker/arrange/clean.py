"""Clean-up of the transcribed notes before arranging (docs/eval/M3-notes.md).

Basic Pitch reports a velocity from the note's amplitude. Notes much quieter than those around
them are mostly harmonics, sympathetic strings and, in a band mix, other instruments that leak
into the Demucs guitar stem. A note is kept when its velocity is at least `QUIET_RATIO` of the
median velocity of the notes starting within `WINDOW_S` around it, so a quiet intro is judged
against itself and not against a loud chorus.
"""

import bisect
from collections.abc import Sequence
from statistics import median

from tabforge_worker.ports import NoteEvent

QUIET_RATIO = 0.7  # GuitarSet players 03-05: note F1 0.777 -> 0.799 (chosen on players 00-02)
WINDOW_S = 10.0


def clean_notes(notes: Sequence[NoteEvent]) -> list[NoteEvent]:
    """The notes worth arranging, in onset order."""
    ordered = sorted(notes, key=lambda n: (n.onset_s, n.pitch))
    onsets = [n.onset_s for n in ordered]
    half = WINDOW_S / 2
    kept: list[NoteEvent] = []
    for note in ordered:
        lo = bisect.bisect_left(onsets, note.onset_s - half)
        hi = bisect.bisect_right(onsets, note.onset_s + half)
        local = median(n.velocity for n in ordered[lo:hi])
        if note.velocity >= QUIET_RATIO * local:
            kept.append(note)
    return kept

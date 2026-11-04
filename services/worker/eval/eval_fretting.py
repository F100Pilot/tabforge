"""String/fret assignment accuracy on GuitarSet reference pitches (no audio involved).

Notes starting within 30 ms are grouped as one event (a chord), as the quantizer would.
Reports exact (string, fret) agreement with the annotation, per track and overall, for the
Viterbi assignment and for the naive "lowest fret" rule from M0.

Usage: uv run python eval/eval_fretting.py
"""

import json
import sys
from collections import defaultdict
from statistics import fmean

from _common import GUITARSET_DIRNAME, data_dir

from tabforge_worker.arrange.fretting import assign_positions, candidate_positions
from tabforge_worker.evaluation.guitarset import (
    STANDARD_TUNING,
    GuitarNote,
    parse_jams,
    parse_track_id,
)

CHORD_WINDOW_S = 0.03
# fretting uses string 1 = highest; GuitarSet string 0 = lowest
TUNING_HIGH_FIRST = tuple(reversed(STANDARD_TUNING))


def to_tab_string(guitarset_string: int) -> int:
    return 6 - guitarset_string


def main() -> int:
    root = data_dir(None) / GUITARSET_DIRNAME / "annotation"
    files = sorted(root.glob("*.jams"))
    if not files:
        print(f"no annotations under {root}", file=sys.stderr)
        return 2
    totals = {"viterbi": 0, "naive": 0, "n": 0}
    by_mode: dict[str, list[float]] = defaultdict(list)
    for path in files:
        info = parse_track_id(path.stem)
        notes = parse_jams(json.loads(path.read_text()))
        groups: list[list[GuitarNote]] = []
        for note in notes:
            if groups and note.onset_s - groups[-1][0].onset_s <= CHORD_WINDOW_S:
                groups[-1].append(note)
            else:
                groups.append([note])
        events = [(tuple(n.pitch for n in g), tuple(90 for _ in g)) for g in groups]
        result = assign_positions(events, TUNING_HIGH_FIRST)
        ok = naive = n = 0
        for group, fretted in zip(groups, result, strict=True):
            placed = dict(zip(fretted.pitches, fretted.positions, strict=True))
            for note in group:
                n += 1
                truth = (to_tab_string(note.string), note.fret)
                pos = placed.get(note.pitch)
                ok += pos is not None and (pos.string, pos.fret) == truth
                low = min(candidate_positions(note.pitch, TUNING_HIGH_FIRST), key=lambda p: p.fret)
                naive += (low.string, low.fret) == truth
        totals["viterbi"] += ok
        totals["naive"] += naive
        totals["n"] += n
        by_mode[info.mode].append(ok / n)
    n = totals["n"]
    print(f"notes {n}")
    print(f"viterbi exact string/fret: {totals['viterbi'] / n:.3f}")
    print(f"naive lowest fret:         {totals['naive'] / n:.3f}")
    for mode, values in sorted(by_mode.items()):
        print(f"  {mode}: per-track mean {fmean(values):.3f} ({len(values)} tracks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

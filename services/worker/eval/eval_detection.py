"""Basic Pitch thresholds and the clean-up ratio (ADR-0017): a grid chosen on some players,
measured on the others and on the band songs.

The model runs once per recording; its activations (note and onset frames) are cached under
<data>/eval/activations/, and every threshold combination is applied to them with
`basic_pitch.note_creation.model_output_to_notes`, as `predict()` does. Recordings: GuitarSet
microphone audio (360) and, if `eval_band.py` has made them, the Demucs guitar stems of the
BabySlakh songs. Onset-only note F1 (onset +-50 ms, pitch +-50 cents), pooled over recordings.

Reported:
- the combination best on GuitarSet players 00-02, against the current defaults on 03-05 and on
  the band songs;
- per player 03-05, the gain of tuning per player on top of it (leave one recording out, kept
  only if better on the held-out recordings), to judge learning per user.

Usage: uv run --extra ml --extra eval python eval/eval_detection.py [--workers N]
"""

import argparse
import bisect
import json
import sys
from collections.abc import Sequence
from itertools import product
from multiprocessing import Pool
from pathlib import Path
from statistics import median

import basic_pitch.note_creation as note_creation
import mir_eval
import numpy as np
from _common import GUITARSET_DIRNAME, data_dir
from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
from basic_pitch.constants import AUDIO_SAMPLE_RATE, FFT_HOP
from basic_pitch.inference import Model, run_inference
from eval_band import guitar_stems, reference

from tabforge_worker.adapters.basic_pitch import (
    LIBRARY_FRAME_THRESHOLD,
    LIBRARY_MIN_NOTE_LENGTH_MS,
    LIBRARY_ONSET_THRESHOLD,
)
from tabforge_worker.arrange.clean import QUIET_RATIO, WINDOW_S
from tabforge_worker.evaluation.guitarset import parse_jams, parse_track_id

Note = tuple[float, float, int, float]  # onset s, offset s, MIDI pitch, amplitude
Counts = tuple[int, int, int]  # matched, reference notes, transcribed notes

ONSET = (0.3, 0.4, 0.5, 0.6, 0.7)
FRAME = (0.2, 0.3, 0.4, 0.5)
MIN_NOTE_MS = (58.0, LIBRARY_MIN_NOTE_LENGTH_MS, 200.0)
RATIO = (0.0, 0.5, 0.6, QUIET_RATIO, 0.8)  # 0: no clean-up
Candidate = tuple[float, float, float, float]  # onset, frame, min note ms, clean-up ratio
CANDIDATES: list[Candidate] = [
    (o, f, m, r) for o, f, m in product(ONSET, FRAME, MIN_NOTE_MS) for r in RATIO
]
OLD = CANDIDATES.index(
    (LIBRARY_ONSET_THRESHOLD, LIBRARY_FRAME_THRESHOLD, LIBRARY_MIN_NOTE_LENGTH_MS, QUIET_RATIO)
)
TRAIN_PLAYERS = ("00", "01", "02")


def clean(notes: list[Note], ratio: float) -> list[Note]:
    """`arrange.clean.clean_notes` with another ratio (velocity = amplitude, same median)."""
    if ratio == 0:
        return notes
    ordered = sorted(notes)
    onsets = [n[0] for n in ordered]
    half = WINDOW_S / 2
    kept = []
    for note in ordered:
        lo = bisect.bisect_left(onsets, note[0] - half)
        hi = bisect.bisect_right(onsets, note[0] + half)
        if note[3] >= ratio * median(n[3] for n in ordered[lo:hi]):
            kept.append(note)
    return kept


def matched(ref: Sequence[Note], est: Sequence[Note]) -> Counts:
    if not ref or not est:
        return (0, len(ref), len(est))

    def arrays(notes: Sequence[Note]) -> tuple[np.ndarray, np.ndarray]:
        iv = np.array([[n[0], max(n[1], n[0] + 0.01)] for n in notes])
        return iv, mir_eval.util.midi_to_hz(np.array([n[2] for n in notes], dtype=float))

    (ri, rh), (ei, eh) = arrays(ref), arrays(est)
    pairs = mir_eval.transcription.match_notes(
        ri, rh, ei, eh, onset_tolerance=0.05, pitch_tolerance=50.0, offset_ratio=None
    )
    return (len(pairs), len(ref), len(est))


def recording_counts(item: tuple[Path, list[Note]]) -> list[Counts]:
    """Counts of every candidate on one recording."""
    path, ref = item
    cached = np.load(path)
    output = {k: cached[k].astype(np.float32) for k in ("note", "onset")}
    output["contour"] = np.zeros((output["note"].shape[0], 1), np.float32)  # frame count only
    result = []
    for onset, frame, min_ms in product(ONSET, FRAME, MIN_NOTE_MS):
        _, events = note_creation.model_output_to_notes(
            output,
            onset_thresh=onset,
            frame_thresh=frame,
            min_note_len=int(np.round(min_ms / 1000 * (AUDIO_SAMPLE_RATE / FFT_HOP))),
            include_pitch_bends=False,
            melodia_trick=True,
        )
        notes = [(float(s), float(e), int(p), float(a)) for s, e, p, a, _ in events]
        result += [matched(ref, clean(notes, ratio)) for ratio in RATIO]
    return result


def f1(c: Counts) -> float:
    return 2 * c[0] / (c[1] + c[2]) if c[1] + c[2] else 0.0


def pooled(rows: Sequence[Sequence[Counts]], candidate: int) -> float:
    return f1(tuple(sum(r[candidate][k] for r in rows) for k in range(3)))  # type: ignore[arg-type]


def best(rows: Sequence[Sequence[Counts]], default: int) -> int:
    return max(range(len(CANDIDATES)), key=lambda c: (pooled(rows, c), c == default))


def per_user_gain(rows: Sequence[Sequence[Counts]], default: int) -> tuple[float, float]:
    """Leave one recording out; the tuned choice is kept only where it beats `default` on the
    other recordings' held-out folds (as an accepted-or-not profile would)."""
    held: list[Counts] = []
    for i, row in enumerate(rows):
        rest = [r for j, r in enumerate(rows) if j != i]
        choice = best(rest, default)
        held.append(row[choice])
    tuned = f1(tuple(sum(h[k] for h in held) for k in range(3)))  # type: ignore[arg-type]
    base = pooled(rows, default)
    return base, max(base, tuned)


def cache_activations(items: list[tuple[Path, Path]]) -> None:
    missing = [(wav, out) for wav, out in items if not out.exists()]
    if not missing:
        return
    model = Model(build_icassp_2022_model_path(FilenameSuffix.onnx))
    for n, (wav, out) in enumerate(missing, 1):
        output = run_inference(wav, model)
        np.savez_compressed(
            out, note=output["note"].astype(np.float16), onset=output["onset"].astype(np.float16)
        )
        print(f"activations {n}/{len(missing)}", file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    root = data_dir(None)
    cache = root / "eval" / "activations"
    cache.mkdir(parents=True, exist_ok=True)

    guitarset: list[tuple[str, Path, list[Note]]] = []
    for jams in sorted((root / GUITARSET_DIRNAME / "annotation").glob("*.jams")):
        wav = root / GUITARSET_DIRNAME / "audio_mono-mic" / f"{jams.stem}_mic.wav"
        if wav.exists():
            ref = [
                (n.onset_s, n.offset_s, n.pitch, 1.0)
                for n in parse_jams(json.loads(jams.read_text()))
            ]
            guitarset.append((jams.stem, wav, ref))
    band: list[tuple[str, Path, list[Note]]] = []
    slakh = root / "babyslakh" / "babyslakh_16k"
    for track in sorted(slakh.glob("Track*")):
        stem = root / "eval" / "band" / f"{track.name}-band.wav"
        stems = guitar_stems(track)
        if stems and stem.exists():
            ref = [(n.onset_s, n.offset_s, n.pitch, 1.0) for n in reference(track, stems)]
            band.append((track.name, stem, ref))
    if not guitarset:
        print(f"no GuitarSet microphone audio under {root}", file=sys.stderr)
        return 2

    every = [(f"gs-{name}", wav, ref) for name, wav, ref in guitarset]
    every += [(f"band-{name}", wav, ref) for name, wav, ref in band]
    cache_activations([(wav, cache / f"{key}.npz") for key, wav, _ in every])
    with Pool(args.workers) as pool:
        rows = pool.map(
            recording_counts, [(cache / f"{key}.npz", ref) for key, _, ref in every], chunksize=4
        )
    by_key = dict(zip([key for key, _, _ in every], rows, strict=True))
    player = {f"gs-{name}": parse_track_id(name).player for name, _, _ in guitarset}
    train = [by_key[k] for k, p in player.items() if p in TRAIN_PLAYERS]
    test = [by_key[k] for k, p in player.items() if p not in TRAIN_PLAYERS]
    band_rows = [by_key[f"band-{name}"] for name, _, _ in band]

    chosen = best(train, OLD)
    print(f"{len(CANDIDATES)} combinations (onset, frame, min note ms, clean-up ratio)")
    print(f"current {CANDIDATES[OLD]}  chosen on players 00-02 {CANDIDATES[chosen]}")
    print(f"players 00-02 (train)  {pooled(train, OLD):.3f} -> {pooled(train, chosen):.3f}")
    print(f"players 03-05 (test)   {pooled(test, OLD):.3f} -> {pooled(test, chosen):.3f}")
    if band_rows:
        print(
            f"band songs ({len(band_rows):>2})       {pooled(band_rows, OLD):.3f} -> "
            f"{pooled(band_rows, chosen):.3f}"
        )
    print("per player, tuning on top of the chosen combination (leave one recording out):")
    for p in sorted({p for p in player.values() if p not in TRAIN_PLAYERS}):
        mine = [by_key[k] for k, q in player.items() if q == p]
        base, tuned = per_user_gain(mine, chosen)
        print(f"  player {p}: {base:.3f} -> {tuned:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

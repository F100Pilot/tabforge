"""Tuning detection (ADR-0013) on GuitarSet: every track replayed in every candidate tuning.

GuitarSet is played in E standard. Keeping each annotated (string, fret) and changing the open
strings gives the same music in another tuning: all strings down for the standard tunings, the
low string a whole tone lower for the drop tunings. No audio is involved: this measures the
decision rule, not the note detection (see `--transcribed` for that).

Reports, per tuning: tracks detected exactly, tracks where the low string is right (the
standard/drop pair may still be swapped) and the confusions. With `--margins`, the share of
standard and drop replays that each margin would call "drop".

With `--transcribed`, the false alarms instead: Basic Pitch on the E standard audio (mic and
pickup mix), so octave errors and stray low notes are real; every guess but E standard is one.

Usage: uv run python eval/eval_tuning.py [--margins] [--limit N]
       uv run --extra ml python eval/eval_tuning.py --transcribed [--limit N]
"""

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from _common import GUITARSET_DIRNAME, data_dir

from tabforge_worker.arrange import tuning as tuning_mod
from tabforge_worker.arrange.fretting import DEFAULT_WEIGHTS
from tabforge_worker.arrange.tuning import CANDIDATES, FLOOR_SHARE, MIN_FLOOR_NOTES, detect_tuning
from tabforge_worker.evaluation.guitarset import GuitarNote, parse_jams
from tabforge_worker.ports import NoteEvent


def replay(notes: list[GuitarNote], tuning: tuple[int, ...]) -> list[NoteEvent]:
    """GuitarSet string 0 = low E = tuning[5] (tuning is high string first)."""
    return [NoteEvent(n.onset_s, n.offset_s, tuning[5 - n.string] + n.fret, 90) for n in notes]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--margins", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--transcribed", action="store_true")
    args = parser.parse_args()
    root = data_dir(None) / GUITARSET_DIRNAME / "annotation"
    files = sorted(root.glob("*.jams"))
    if args.limit:
        files = files[:: max(1, len(files) // args.limit)][: args.limit]
    if not files:
        print(f"no annotations under {root}", file=sys.stderr)
        return 2
    if args.transcribed:
        return false_alarms(files)

    exact: Counter[str] = Counter()
    low_ok: Counter[str] = Counter()
    # Tracks that play the open low string at least as often as the detector needs: the case
    # it is for (a down-tuned riff on the low string); elsewhere nothing reveals the tuning.
    sub_n = 0
    sub_exact: Counter[str] = Counter()
    sub_low: Counter[str] = Counter()
    confusions: dict[str, Counter[str]] = defaultdict(Counter)
    ratios: dict[str, list[float]] = {"standard": [], "drop": []}
    for path in files:
        notes = parse_jams(json.loads(path.read_text()))
        open_low = sum(n.string == 0 and n.fret == 0 for n in notes)
        uses_low = open_low >= max(MIN_FLOOR_NOTES, math.ceil(FLOOR_SHARE * len(notes)))
        sub_n += uses_low
        for cand in CANDIDATES:
            played = replay(notes, cand.tuning)
            guess = detect_tuning(played)
            exact[cand.name] += guess.name == cand.name
            low_ok[cand.name] += guess.tuning[5] == cand.tuning[5]
            if uses_low:
                sub_exact[cand.name] += guess.name == cand.name
                sub_low[cand.name] += guess.tuning[5] == cand.tuning[5]
            if guess.name != cand.name:
                confusions[cand.name][guess.name] += 1
            if args.margins and cand.name in ("D standard", "Drop D"):
                pair = [c for c in CANDIDATES if c.tuning[5] == 38]
                events = tuning_mod._events(played)
                std = tuning_mod._effort(events, pair[0].tuning, DEFAULT_WEIGHTS)
                drop = tuning_mod._effort(events, pair[1].tuning, DEFAULT_WEIGHTS)
                kind = "standard" if cand.name == "D standard" else "drop"
                ratios[kind].append(drop / std if std else 1.0)

    n = len(files)
    print(f"tracks {n} (each replayed in {len(CANDIDATES)} tunings)")
    print(f"tracks playing the open low string often: {sub_n}")
    head = f"{'tuning':<13} {'exact':>6} {'low string':>11} | {'those tracks':>12} {'low':>6}"
    print(f"{head}  confused with")
    for cand in CANDIDATES:
        top = ", ".join(f"{k} {v}" for k, v in confusions[cand.name].most_common(3))
        se = sub_exact[cand.name] / sub_n if sub_n else 0.0
        sl = sub_low[cand.name] / sub_n if sub_n else 0.0
        print(
            f"{cand.name:<13} {exact[cand.name] / n:>6.1%} {low_ok[cand.name] / n:>11.1%} |"
            f" {se:>12.1%} {sl:>6.1%}  {top}"
        )
    k = len(CANDIDATES)
    print(
        f"all           {sum(exact.values()) / (n * k):>6.1%}"
        f" {sum(low_ok.values()) / (n * k):>11.1%} |"
        f" {sum(sub_exact.values()) / max(1, sub_n * k):>12.1%}"
        f" {sum(sub_low.values()) / max(1, sub_n * k):>6.1%}"
    )
    if args.margins:
        print("\ndrop/standard effort on the D replays; share called 'drop' per margin:")
        for margin in (0.0, 0.02, 0.05, 0.08, 0.10, 0.15):
            s = sum(r < 1 - margin for r in ratios["standard"]) / len(ratios["standard"])
            d = sum(r < 1 - margin for r in ratios["drop"]) / len(ratios["drop"])
            print(f"  margin {margin:.2f}: D standard replays {s:.1%}, Drop D replays {d:.1%}")
    return 0


AUDIO = (("audio_mono-mic", "_mic.wav"), ("audio_mono-pickup_mix", "_mix.wav"))


def false_alarms(files: list[Path]) -> int:
    from tabforge_worker.adapters.basic_pitch import BasicPitchOnnxTranscriber

    transcriber = BasicPitchOnnxTranscriber()
    audio_root = data_dir(None) / GUITARSET_DIRNAME
    guesses: Counter[str] = Counter()
    below_e: list[float] = []
    for path in files:
        for folder, suffix in (
            ("audio_mono-mic", "_mic.wav"),
            ("audio_mono-pickup_mix", "_mix.wav"),
        ):
            audio = audio_root / folder / f"{path.stem}{suffix}"
            if not audio.exists():
                continue
            notes = transcriber.transcribe(audio)
            guess = detect_tuning(notes)
            guesses[guess.name] += 1
            below_e.append(sum(n.pitch < 40 for n in notes) / max(1, len(notes)))
    total = sum(guesses.values())
    print(f"transcribed E standard recordings: {total}")
    for name, count in guesses.most_common():
        print(f"  {name:<13} {count:>4} ({count / total:.1%})")
    below_e.sort()
    print(
        f"notes below E2 per recording: median {below_e[len(below_e) // 2]:.2%},"
        f" max {below_e[-1]:.2%}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

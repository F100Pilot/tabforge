"""M0 baseline: GuitarSet audio -> (optional Demucs htdemucs_6s) -> Basic Pitch ONNX -> note F1.

Usage:
  uv run python eval/run_m0.py --audio mic                # isolated guitar, no separation
  uv run python eval/run_m0.py --audio mic --separate     # same audio through Demucs first
Writes `<data>/eval/m0-<condition>.json` and prints a summary table.
"""

import argparse
import json
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import soundfile
from _common import GUITARSET_DIRNAME, data_dir, package_versions

from tabforge_worker.adapters.basic_pitch import (
    DEFAULT_FRAME_THRESHOLD,
    DEFAULT_MIN_NOTE_LENGTH_MS,
    DEFAULT_ONSET_THRESHOLD,
    BasicPitchOnnxTranscriber,
)
from tabforge_worker.evaluation.guitarset import parse_jams, parse_track_id
from tabforge_worker.evaluation.metrics import NoteScores, mean_scores, score_notes

# GuitarSet archive folder and filename suffix per audio rendition.
AUDIO_SOURCES = {
    "mic": ("audio_mono-mic", "_mic.wav"),
    "mix": ("audio_mono-pickup_mix", "_mix.wav"),
}
VERSIONED = ("basic-pitch", "onnxruntime", "demucs", "torch", "mir_eval", "numpy", "librosa")


def _index_audio(folder: Path, suffix: str) -> dict[str, Path]:
    return {p.name.removesuffix(suffix): p for p in folder.rglob(f"*{suffix}")}


def _summarise(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[NoteScores]] = defaultdict(list)
    for row in rows:
        groups[row[key]].append(NoteScores(**row["scores"]))
    return {g: {**asdict(mean_scores(s)), "tracks": len(s)} for g, s in sorted(groups.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--audio", choices=sorted(AUDIO_SOURCES), default="mic")
    parser.add_argument("--separate", action="store_true", help="run Demucs htdemucs_6s first")
    parser.add_argument("--device", help="Demucs device (default: cuda if available)")
    parser.add_argument("--limit", type=int, help="evaluate only the first N tracks")
    parser.add_argument("--every", type=int, default=1, help="take every k-th track (subset)")
    parser.add_argument("--onset-threshold", type=float, default=DEFAULT_ONSET_THRESHOLD)
    parser.add_argument("--frame-threshold", type=float, default=DEFAULT_FRAME_THRESHOLD)
    parser.add_argument("--min-note-ms", type=float, default=DEFAULT_MIN_NOTE_LENGTH_MS)
    parser.add_argument("--tag", default="", help="suffix for the output file name")
    args = parser.parse_args()

    root = data_dir(args.data_dir)
    gs = root / GUITARSET_DIRNAME
    folder, suffix = AUDIO_SOURCES[args.audio]
    audio_index = _index_audio(gs / folder, suffix)
    jams_files = sorted((gs / "annotation").rglob("*.jams"))
    if not jams_files or not audio_index:
        print(f"no data under {gs}; run eval/download_guitarset.py first", file=sys.stderr)
        return 2
    jams_files = jams_files[:: args.every][: args.limit]

    condition = f"{args.audio}{'+demucs' if args.separate else ''}{args.tag}"
    t0 = time.perf_counter()
    transcriber = BasicPitchOnnxTranscriber(
        args.onset_threshold, args.frame_threshold, args.min_note_ms
    )
    load_bp_s = time.perf_counter() - t0
    separator = None
    load_sep_s = 0.0
    if args.separate:
        from tabforge_worker.adapters.demucs import DemucsGuitarSeparator

        t0 = time.perf_counter()
        separator = DemucsGuitarSeparator(device=args.device)
        load_sep_s = time.perf_counter() - t0

    out_dir = root / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        for i, jams_path in enumerate(jams_files, 1):
            track_id = jams_path.stem
            info = parse_track_id(track_id)
            audio = audio_index.get(track_id)
            if audio is None:
                print(f"missing audio for {track_id}", file=sys.stderr)
                return 2
            ref = parse_jams(json.loads(jams_path.read_text()))
            audio_s = float(soundfile.info(str(audio)).duration)

            sep_s = 0.0
            if separator is not None:
                t0 = time.perf_counter()
                audio = separator.isolate_guitar(audio, Path(tmp))
                sep_s = time.perf_counter() - t0
            t0 = time.perf_counter()
            est = transcriber.transcribe(audio)
            bp_s = time.perf_counter() - t0
            if separator is not None:
                audio.unlink()

            scores = score_notes(ref, est)
            rows.append(
                {
                    **asdict(info),
                    "audio_s": audio_s,
                    "separate_s": sep_s,
                    "transcribe_s": bp_s,
                    "scores": asdict(scores),
                }
            )
            print(
                f"[{i}/{len(jams_files)}] {track_id}: F1 {scores.f1:.3f} "
                f"F1+off {scores.f1_with_offset:.3f} ({bp_s + sep_s:.1f}s)",
                flush=True,
            )

    total_audio = sum(r["audio_s"] for r in rows)
    overall = mean_scores([NoteScores(**r["scores"]) for r in rows])
    result: dict[str, Any] = {
        "condition": condition,
        "dataset": {"name": "GuitarSet", "audio": folder, "tracks": len(rows)},
        "config": {
            "onset_threshold": args.onset_threshold,
            "frame_threshold": args.frame_threshold,
            "min_note_ms": args.min_note_ms,
            "demucs_model": "htdemucs_6s" if separator else None,
            "demucs_device": separator.device if separator else None,
        },
        "versions": package_versions(VERSIONED),
        "timing": {
            "load_transcriber_s": load_bp_s,
            "load_separator_s": load_sep_s,
            "audio_total_s": total_audio,
            "transcribe_s_per_audio_min": 60 * sum(r["transcribe_s"] for r in rows) / total_audio,
            "separate_s_per_audio_min": 60 * sum(r["separate_s"] for r in rows) / total_audio,
        },
        "summary": {
            "all": {
                **asdict(overall),
                "tracks": len(rows),
            },
            "by_mode": _summarise(rows, "mode"),
            "by_style": _summarise(rows, "style"),
        },
        "tracks": rows,
    }
    out = out_dir / f"m0-{condition}.json"
    out.write_text(json.dumps(result, indent=2))
    print(
        f"\n{condition}: tracks={len(rows)} P={overall.precision:.3f} R={overall.recall:.3f} "
        f"F1={overall.f1:.3f} F1+off={overall.f1_with_offset:.3f} -> {out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Time and peak memory per stage, each in a fresh process, on clips of fixed length.

Usage: uv run python eval/profile_m0.py --source <some.wav> --durations 60 180
The source audio is tiled to each duration. Results: `<data>/eval/m0-profile.json`.
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from _common import data_dir, package_versions

MARKER = "PROFILE_RESULT "
STAGES = ("basic_pitch", "demucs")


def _proc_status_mib(field: str) -> float:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(f"{field}:"):
            return int(line.split()[1]) / 1024  # kB -> MiB
    raise RuntimeError(f"{field} not in /proc/self/status")


def _child(stage: str, clip: Path, device: str | None) -> None:
    import soundfile

    audio_s = float(soundfile.info(str(clip)).duration)
    t0 = time.perf_counter()
    if stage == "basic_pitch":
        from tabforge_worker.adapters.basic_pitch import BasicPitchOnnxTranscriber

        transcriber = BasicPitchOnnxTranscriber()
        load_s = time.perf_counter() - t0
        rss_loaded = _proc_status_mib("VmHWM")
        t1 = time.perf_counter()
        transcriber.transcribe(clip)
        used_device = "cpu (onnxruntime CPUExecutionProvider)"
    else:
        import torch

        from tabforge_worker.adapters.demucs import DemucsGuitarSeparator

        separator = DemucsGuitarSeparator(device=device)
        load_s = time.perf_counter() - t0
        rss_loaded = _proc_status_mib("VmHWM")
        t1 = time.perf_counter()
        out = separator.isolate_guitar(clip, clip.parent)
        out.unlink()
        used_device = f"{separator.device} (torch threads={torch.get_num_threads()})"
        if separator.device == "cuda":
            used_device += f", cuda peak {torch.cuda.max_memory_allocated() / 2**20:.0f} MiB"
    run_s = time.perf_counter() - t1
    result = {
        "stage": stage,
        "audio_s": audio_s,
        "load_s": load_s,
        "run_s": run_s,
        "run_s_per_audio_min": 60 * run_s / audio_s,
        "peak_rss_after_load_mib": rss_loaded,
        "peak_rss_mib": _proc_status_mib("VmHWM"),
        "device": used_device,
    }
    print(MARKER + json.dumps(result), flush=True)


def _make_clip(source: Path, seconds: int, out: Path) -> None:
    import numpy as np
    import soundfile

    data, sr = soundfile.read(str(source), always_2d=True)
    need = seconds * sr
    reps = -(-need // len(data))
    soundfile.write(str(out), np.tile(data, (reps, 1))[:need], sr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", nargs=2, metavar=("STAGE", "CLIP"), help=argparse.SUPPRESS)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--source", type=Path, help="audio to tile into test clips")
    parser.add_argument("--durations", type=int, nargs="+", default=[60, 180])
    parser.add_argument("--stages", nargs="+", choices=STAGES, default=list(STAGES))
    parser.add_argument("--device", help="Demucs device (default: cuda if available)")
    args = parser.parse_args()

    if args.child:
        _child(args.child[0], Path(args.child[1]), args.device)
        return 0
    if args.source is None:
        parser.error("--source is required")

    out_dir = data_dir(args.data_dir) / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for seconds in args.durations:
        clip = out_dir / f"profile-{seconds}s.wav"
        _make_clip(args.source, seconds, clip)
        for stage in args.stages:
            cmd = [sys.executable, __file__, "--child", stage, str(clip)]
            if args.device:
                cmd += ["--device", args.device]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
            lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(MARKER)]
            if proc.returncode != 0 or not lines:
                print(proc.stderr[-3000:], file=sys.stderr)
                return 1
            result = json.loads(lines[-1].removeprefix(MARKER))
            results.append(result)
            print(json.dumps(result), flush=True)
        clip.unlink()

    report = {
        "host": {
            "cpu": platform.processor() or platform.machine(),
            "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
        },
        "versions": package_versions(("basic-pitch", "onnxruntime", "demucs", "torch")),
        "results": results,
    }
    (out_dir / "m0-profile.json").write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

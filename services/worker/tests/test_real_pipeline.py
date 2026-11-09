"""RealPipeline control flow with fake models (no ML needed); real ffmpeg for audio checks."""

import hashlib
import shutil
import uuid
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest
from tabforge_score import Score
from test_media import write_tone

from tabforge_worker.arrange.fretting import Weights
from tabforge_worker.pipeline import PipelineError, Stage
from tabforge_worker.ports import NoteEvent
from tabforge_worker.queue import ClaimedJob
from tabforge_worker.real_pipeline import RealPipeline

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


class FakeSource:
    def __init__(self, maker) -> None:  # type: ignore[no-untyped-def]
        self.maker = maker
        self.keys: list[str] = []

    def download(self, key: str, dst: Path) -> None:
        self.keys.append(key)
        self.maker(dst)


class FakeTranscriber:
    def __init__(self) -> None:
        self.inputs: list[Path] = []

    def transcribe(self, audio: Path) -> list[NoteEvent]:
        self.inputs.append(audio)
        return [NoteEvent(0.0, 0.5, 64, 90), NoteEvent(0.5, 1.0, 69, 90)]


class FakeBeats:
    def beats(self, audio: Path) -> list[float]:
        return [0.0, 0.5, 1.0, 1.5]


class FakeStereo:
    def __init__(self) -> None:
        self.inputs: list[Path] = []

    def side_ratios(self, audio: Path, notes: Sequence[NoteEvent]) -> list[float] | None:
        self.inputs.append(audio)
        return None


class FakeSeparator:
    def __init__(self) -> None:
        self.inputs: list[Path] = []

    def isolate_guitar(self, audio: Path, workdir: Path) -> Path:
        self.inputs.append(audio)
        out = workdir / "guitar.wav"
        shutil.copy(audio, out)
        return out


def _job(kind: str) -> ClaimedJob:
    return ClaimedJob(uuid.uuid4(), uuid.uuid4(), 1, kind, uuid.uuid4(), "audio/u/a", "audio/wav")


def _pipeline(
    source: FakeSource, **kw: object
) -> tuple[RealPipeline, FakeTranscriber, FakeSeparator]:
    pipe, transcriber, separator, _ = _pipeline_with_stereo(source, **kw)
    return pipe, transcriber, separator


def _pipeline_with_stereo(
    source: FakeSource, **kw: object
) -> tuple[RealPipeline, FakeTranscriber, FakeSeparator, FakeStereo]:
    transcriber, separator, stereo = FakeTranscriber(), FakeSeparator(), FakeStereo()
    pipe = RealPipeline(
        source=source,
        transcriber=lambda: transcriber,
        separator=lambda: separator,
        beat_tracker=lambda: FakeBeats(),
        stereo=lambda: stereo,
        **kw,  # type: ignore[arg-type]
    )
    return pipe, transcriber, separator, stereo


def test_guitar_stem_skips_separation_and_builds_score(tmp_path: Path) -> None:
    expected_sha: list[str] = []

    def make(dst: Path) -> None:
        write_tone(dst, 2.0)
        expected_sha.append(hashlib.sha256(dst.read_bytes()).hexdigest())

    pipe, transcriber, separator, stereo = _pipeline_with_stereo(FakeSource(make))
    seen: list[Stage] = []
    result = pipe.process(_job("guitar_stem"), seen.append)

    assert seen == [Stage.NORMALIZING, Stage.TRANSCRIBING, Stage.ARRANGING]
    assert separator.inputs == []
    assert stereo.inputs == []  # one guitar: no Lead/Rhythm split
    assert transcriber.inputs and transcriber.inputs[0].name == "audio.wav"
    assert result.duration_ms == pytest.approx(2000, abs=20)
    assert result.sha256 == expected_sha[0]
    score = Score.model_validate(result.score)
    assert score.schema_version == 2
    sounding = [
        score.tuning[n.string - 1] + n.fret
        for b in score.bars
        for beat in b.beats
        for n in beat.notes
    ]
    assert sounding == [64, 69]  # E4 then A4, whichever positions the Viterbi picked


def test_mix_separates_before_transcribing(tmp_path: Path) -> None:
    pipe, transcriber, separator = _pipeline(FakeSource(lambda dst: write_tone(dst, 1.0)))
    seen: list[Stage] = []
    pipe.process(_job("mix"), seen.append)
    assert Stage.SEPARATING in seen
    assert separator.inputs[0].name == "audio.wav"
    assert transcriber.inputs[0].name == "guitar.wav"


def test_mix_builds_lead_and_rhythm_tracks_from_the_guitar_stem(tmp_path: Path) -> None:
    pipe, _, _, stereo = _pipeline_with_stereo(FakeSource(lambda dst: write_tone(dst, 1.0)))
    result = pipe.process(_job("mix"), lambda _: None)

    assert [p.name for p in stereo.inputs] == ["guitar.wav"]
    score = Score.model_validate(result.score)
    assert score.schema_version == 3
    assert "bars" not in result.score and "tuning" not in result.score
    tracks = score.track_list()
    assert [t.name for t in tracks] == ["Lead", "Rhythm"]
    assert len(tracks[0].bars) == len(tracks[1].bars)
    lead = [
        tracks[0].tuning[n.string - 1] + n.fret
        for b in tracks[0].bars
        for beat in b.beats
        for n in beat.notes
    ]
    # E4 and A4 single notes, no stereo info: the high register puts both in Lead.
    assert lead == [64, 69]


def test_too_long_audio_fails_before_transcription(tmp_path: Path) -> None:
    pipe, transcriber, _ = _pipeline(
        FakeSource(lambda dst: write_tone(dst, 2.0)), max_duration_s=1.0
    )
    with pytest.raises(PipelineError) as err:
        pipe.process(_job("guitar_stem"), lambda _: None)
    assert err.value.code == "audio_too_long"
    assert transcriber.inputs == []


def test_unreadable_audio(tmp_path: Path) -> None:
    pipe, transcriber, _ = _pipeline(
        FakeSource(lambda dst: dst.write_bytes(b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 32))
    )
    with pytest.raises(PipelineError) as err:
        pipe.process(_job("guitar_stem"), lambda _: None)
    assert err.value.code == "audio_unreadable"
    assert transcriber.inputs == []


def test_temporary_files_are_removed(tmp_path: Path) -> None:
    dirs: list[Path] = []

    def make(dst: Path) -> None:
        dirs.append(dst.parent)
        write_tone(dst, 0.5)

    pipe, _, _ = _pipeline(FakeSource(make))
    pipe.process(_job("guitar_stem"), lambda _: None)
    assert not dirs[0].exists()


def _positions(score: Score) -> list[tuple[int, int]]:
    return [
        (n.string, n.fret)
        for t in score.track_list()
        for b in t.bars
        for beat in b.beats
        for n in beat.notes
    ]


@pytest.mark.parametrize("kind", ["guitar_stem", "mix"])
def test_the_owners_tuned_weights_choose_the_positions(kind: str) -> None:
    """ADR-0011: a job carrying the owner's weights arranges with them (v2 and v3 alike)."""
    pipe, _, _ = _pipeline(FakeSource(lambda dst: write_tone(dst, 1.0)))
    default = Score.model_validate(pipe.process(_job(kind), lambda _: None).score)
    high = Weights(span=1.0, height=-0.4, move=0.1, open_move=0.0)
    tuned_job = replace(_job(kind), weights=high)
    tuned = Score.model_validate(pipe.process(tuned_job, lambda _: None).score)
    assert _positions(default) != _positions(tuned)
    assert max(f for _, f in _positions(tuned)) > max(f for _, f in _positions(default))


class LowBTranscriber(FakeTranscriber):
    """A riff on low B (35), below E standard: only a down-tuned guitar plays it."""

    def transcribe(self, audio: Path) -> list[NoteEvent]:
        self.inputs.append(audio)
        pitches = [35, 35, 38, 40, 42, 35] * 4
        return [NoteEvent(i * 0.08, i * 0.08 + 0.07, p, 90) for i, p in enumerate(pitches)]


@pytest.mark.parametrize("kind", ["guitar_stem", "mix"])
def test_the_tuning_is_detected_from_the_notes(kind: str) -> None:
    transcriber = LowBTranscriber()
    pipe = RealPipeline(
        source=FakeSource(lambda dst: write_tone(dst, 2.0)),
        transcriber=lambda: transcriber,
        separator=lambda: FakeSeparator(),
        beat_tracker=lambda: FakeBeats(),
        stereo=lambda: FakeStereo(),
    )
    score = Score.model_validate(pipe.process(_job(kind), lambda _: None).score)
    b_standard = [59, 54, 50, 45, 40, 35]
    assert all(t.tuning == b_standard for t in score.track_list())
    # No note falls off the neck: E standard would have dropped every low B as out of range.
    assert not [w for t in score.track_list() for w in t.warnings if w.code == "out_of_range"]


def test_a_fixed_tuning_skips_the_detection() -> None:
    transcriber = LowBTranscriber()
    standard = (64, 59, 55, 50, 45, 40)
    pipe = RealPipeline(
        source=FakeSource(lambda dst: write_tone(dst, 2.0)),
        transcriber=lambda: transcriber,
        separator=lambda: FakeSeparator(),
        beat_tracker=lambda: FakeBeats(),
        stereo=lambda: FakeStereo(),
        tuning=standard,
    )
    score = Score.model_validate(pipe.process(_job("guitar_stem"), lambda _: None).score)
    assert tuple(score.tuning) == standard


class FaintTranscriber(FakeTranscriber):
    """Two loud notes and one far quieter (a harmonic or another instrument's leak)."""

    def transcribe(self, audio: Path) -> list[NoteEvent]:
        self.inputs.append(audio)
        return [
            NoteEvent(0.0, 0.5, 64, 90),
            NoteEvent(0.1, 0.4, 76, 20),
            NoteEvent(0.5, 1.0, 69, 90),
        ]


def test_quiet_notes_are_left_out_before_arranging() -> None:
    transcriber = FaintTranscriber()
    pipe = RealPipeline(
        source=FakeSource(lambda dst: write_tone(dst, 2.0)),
        transcriber=lambda: transcriber,
        separator=lambda: FakeSeparator(),
        beat_tracker=lambda: FakeBeats(),
        stereo=lambda: FakeStereo(),
    )
    score = Score.model_validate(pipe.process(_job("guitar_stem"), lambda _: None).score)
    sounding = [
        score.tuning[n.string - 1] + n.fret
        for b in score.bars
        for beat in b.beats
        for n in beat.notes
    ]
    assert sounding == [64, 69]

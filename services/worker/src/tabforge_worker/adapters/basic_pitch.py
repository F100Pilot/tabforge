"""Basic Pitch transcriber on the bundled ONNX model (ADR-0002: no TensorFlow)."""

from pathlib import Path

from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
from basic_pitch.inference import Model, predict

from tabforge_worker.ports import NoteEvent

# Library defaults of basic-pitch 0.4.0 `predict()`.
DEFAULT_ONSET_THRESHOLD = 0.5
DEFAULT_FRAME_THRESHOLD = 0.3
DEFAULT_MIN_NOTE_LENGTH_MS = 127.70


class BasicPitchOnnxTranscriber:
    """`Transcriber` backed by `nmp.onnx` via onnxruntime (CPU provider)."""

    def __init__(
        self,
        onset_threshold: float = DEFAULT_ONSET_THRESHOLD,
        frame_threshold: float = DEFAULT_FRAME_THRESHOLD,
        min_note_length_ms: float = DEFAULT_MIN_NOTE_LENGTH_MS,
    ) -> None:
        model_path = build_icassp_2022_model_path(FilenameSuffix.onnx)
        self._model = Model(model_path)
        if self._model.model_type is not Model.MODEL_TYPES.ONNX:
            raise RuntimeError(f"expected ONNX backend, got {self._model.model_type}")
        self._onset_threshold = onset_threshold
        self._frame_threshold = frame_threshold
        self._min_note_length_ms = min_note_length_ms

    def transcribe(self, audio: Path) -> list[NoteEvent]:
        _, _, note_events = predict(
            audio,
            self._model,
            onset_threshold=self._onset_threshold,
            frame_threshold=self._frame_threshold,
            minimum_note_length=self._min_note_length_ms,
        )
        return sorted(
            (
                NoteEvent(
                    onset_s=float(start),
                    offset_s=float(end),
                    pitch=int(pitch),
                    velocity=min(127, max(0, round(127 * float(amplitude)))),
                )
                for start, end, pitch, amplitude, _ in note_events
            ),
            key=lambda n: (n.onset_s, n.pitch),
        )

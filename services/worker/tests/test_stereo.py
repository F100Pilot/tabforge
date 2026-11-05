"""Side-channel ratio per note on synthetic stereo signals (needs numpy/librosa: ml extra)."""

from pathlib import Path

import pytest

from tabforge_worker.ports import NoteEvent

pytestmark = pytest.mark.ml

SR = 44100


def _tone(hz: float, seconds: float, phase: float = 0.0, detune_cents: float = 0.0):  # type: ignore[no-untyped-def]
    import numpy as np

    t = np.arange(int(seconds * SR)) / SR
    f = hz * 2 ** (detune_cents / 1200)
    # Fundamental + 2 overtones, like a (very) clean guitar.
    return sum((0.5 / k) * np.sin(2 * np.pi * k * f * t + k * phase) for k in (1, 2, 3))


def _note(pitch: int, onset: float = 0.1, offset: float = 0.9) -> NoteEvent:
    return NoteEvent(onset_s=onset, offset_s=offset, pitch=pitch, velocity=90)


def test_centred_tone_has_no_side_energy() -> None:
    import numpy as np

    from tabforge_worker.adapters.stereo import side_ratios

    a4 = _tone(440.0, 1.0)
    l_only = _tone(110.0, 1.0)  # an unrelated guitar on the left, so the file is not mono
    signal = np.stack([a4 + l_only, a4])
    ratios = side_ratios(signal, SR, [_note(69)])
    assert ratios is not None
    assert ratios[0] < 0.01


def test_hard_panned_doubled_pair_is_wide() -> None:
    import numpy as np

    from tabforge_worker.adapters.stereo import side_ratios

    # Two takes of E3: one hard left, one hard right, slightly detuned and out of phase.
    left = _tone(164.81, 1.0)
    right = _tone(164.81, 1.0, phase=1.3, detune_cents=6)
    ratios = side_ratios(np.stack([left, right]), SR, [_note(52)])
    assert ratios is not None
    # Wide: about as much side as mid energy (above 0.5 when the takes are partly out of phase).
    assert 0.3 < ratios[0] < 0.9


def test_single_hard_panned_guitar_is_half_side() -> None:
    import numpy as np

    from tabforge_worker.adapters.stereo import side_ratios

    left = _tone(220.0, 1.0)
    ratios = side_ratios(np.stack([left, np.zeros_like(left)]), SR, [_note(57)])
    assert ratios is not None
    assert ratios[0] == pytest.approx(0.5, abs=0.01)


def test_each_note_is_measured_on_its_own_partials() -> None:
    import numpy as np

    from tabforge_worker.adapters.stereo import side_ratios

    # Centred A5 melody over wide doubled E2 power-chord roots, at the same time.
    melody = _tone(880.0, 1.0)
    left, right = _tone(82.41, 1.0), _tone(82.41, 1.0, phase=2.0, detune_cents=-7)
    signal = np.stack([melody + left, melody + right])
    ratios = side_ratios(signal, SR, [_note(81), _note(40)])
    assert ratios is not None
    assert ratios[0] < 0.05
    assert ratios[1] > 0.3


def test_mono_or_identical_channels_give_none() -> None:
    import numpy as np

    from tabforge_worker.adapters.stereo import side_ratios

    tone = _tone(440.0, 1.0)
    assert side_ratios(tone[np.newaxis, :], SR, [_note(69)]) is None
    assert side_ratios(np.stack([tone, tone]), SR, [_note(69)]) is None


def test_notes_at_the_end_of_the_file_and_very_short_notes() -> None:
    import numpy as np

    from tabforge_worker.adapters.stereo import side_ratios

    left = _tone(220.0, 1.0)
    signal = np.stack([left, np.zeros_like(left)])
    notes = [_note(57, 0.98, 1.0), _note(57, 0.5, 0.52), _note(57, 1.2, 1.3)]
    ratios = side_ratios(signal, SR, notes)
    assert ratios is not None and len(ratios) == 3
    assert ratios[1] == pytest.approx(0.5, abs=0.01)


def test_analyzer_reads_a_stereo_wav(tmp_path: Path) -> None:
    import numpy as np
    import soundfile as sf

    from tabforge_worker.adapters.stereo import StereoSideAnalyzer

    left = _tone(220.0, 1.0)
    path = tmp_path / "stem.wav"
    sf.write(path, np.stack([left, np.zeros_like(left)], axis=1) * 0.5, SR)
    ratios = StereoSideAnalyzer().side_ratios(path, [_note(57)])
    assert ratios is not None
    assert ratios[0] == pytest.approx(0.5, abs=0.01)

    mono = tmp_path / "mono.wav"
    sf.write(mono, left * 0.5, SR)
    assert StereoSideAnalyzer().side_ratios(mono, [_note(57)]) is None

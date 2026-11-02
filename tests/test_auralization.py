"""Tests for FluidSynth auralization (utils/auralization.py)."""

import numpy as np

from muscriptor.utils import auralization as aur


class _Completed:
    returncode = 0
    stderr = b""


def test_synthesize_midi_runs_fluidsynth_and_mixes_to_mono(monkeypatch, tmp_path):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return _Completed()

    stereo = np.zeros((10, 2), dtype=np.float32)
    stereo[:, 0] = 0.5
    stereo[:, 1] = 0.5
    monkeypatch.setattr(aur.subprocess, "run", fake_run)
    monkeypatch.setattr(aur.sf, "read", lambda path, dtype=None: (stereo, 44100))

    out = aur._synthesize_midi(tmp_path / "in.mid", tmp_path / "font.sf2")

    assert np.allclose(out, 0.5)  # the two channels averaged
    assert str(tmp_path / "in.mid") in seen["argv"]
    assert "-ni" in seen["argv"] and "-F" in seen["argv"]


def test_auralize_crops_bar_offset_and_rms_matches(monkeypatch, tmp_path):
    sr = aur._SAMPLE_RATE
    synth = np.ones(sr * 2, dtype=np.float32)
    original = np.full(sr * 2, 0.25, dtype=np.float32)
    written = {}

    monkeypatch.setattr(aur, "_resolve_soundfont", lambda path: tmp_path / "f.sf2")
    monkeypatch.setattr(aur, "_synthesize_midi", lambda midi, font: synth.copy())
    # The bar-alignment delay only exists in the MIDI, so skip parsing it.
    monkeypatch.setattr(aur, "MidiFile", lambda path: object())
    monkeypatch.setattr(aur, "read_bar_offset", lambda midi: 0.5)
    monkeypatch.setattr(aur, "_load_mono_44k", lambda path: original.copy())
    monkeypatch.setattr(
        aur.sf,
        "write",
        lambda path, data, rate: written.update(path=path, data=data, rate=rate),
    )

    aur.auralize(tmp_path / "in.mid", tmp_path / "orig.wav", tmp_path / "out.wav")

    stereo = written["data"]
    assert written["rate"] == sr
    assert stereo.shape == (sr * 2, 2)
    # L keeps the original untouched.
    assert np.array_equal(stereo[:, 0], original)
    # The 0.5 s bar offset was cut from the start of the synthesis, so the
    # padded mix has 0.5 s of silence at the end.
    assert stereo[0, 1] > 0
    assert np.all(stereo[-(sr // 2) :, 1] == 0)
    # R is RMS-normalized to the original's loudness.
    assert np.isclose(np.sqrt(np.mean(stereo[:, 1] ** 2)), 0.25, atol=1e-4)

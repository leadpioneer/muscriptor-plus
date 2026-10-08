"""Hermetic tests for the preprocessing layer and its server integration.

No real separation model, GPU or network: `audio_separator` is stubbed out
with a fake module for the preprocessor unit tests, and the server tests run
against a fake preprocessor injected through `create_app`.
"""

import sys
import types
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from muscriptor.events import NoteEndEvent, NoteStartEvent
from muscriptor.preprocessing import PreprocessError, PreprocessResult
from muscriptor.preprocessing.artifacts import StemStore
from muscriptor.preprocessing.vocal_removal import VocalRemovalPreprocessor
from muscriptor.server import create_app

from .test_server import FAKE_MIDI, _parse_sse, _wav_bytes, make_model


def _write_wav(path: Path, value: int = 100, frames: int = 100) -> None:
    """A tiny 16-bit mono WAV with a recognizable constant sample value."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(value.to_bytes(2, "little", signed=True) * frames)


class FakeSeparator:
    """Stand-in for `audio_separator.separator.Separator`, recording calls.

    `separate_impl` (set on the class before the preprocessor runs) produces
    the stem files and returns the paths to hand back, mimicking the real
    `separate()`.
    """

    instances: list = []
    pending_impl = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.output_dir = kwargs.get("output_dir")
        self.loaded_models = []
        self.separate_calls = []
        self.separate_impl = FakeSeparator.pending_impl
        FakeSeparator.instances.append(self)

    def load_model(self, model_filename):
        self.loaded_models.append(model_filename)

    def separate(self, audio_file_path, custom_output_names=None):
        self.separate_calls.append((audio_file_path, custom_output_names))
        assert self.separate_impl is not None, "test must set separate_impl"
        return self.separate_impl(Path(self.output_dir), Path(audio_file_path))


def _install_fake_separator(monkeypatch):
    """Make `from audio_separator.separator import Separator` import the fake."""
    package = types.ModuleType("audio_separator")
    sub = types.ModuleType("audio_separator.separator")
    sub.Separator = FakeSeparator
    package.separator = sub
    monkeypatch.setitem(sys.modules, "audio_separator", package)
    monkeypatch.setitem(sys.modules, "audio_separator.separator", sub)
    monkeypatch.setattr("shutil.which", lambda name: "C:/fake/ffmpeg.exe")


@pytest.fixture(autouse=True)
def _fresh_separator_instances():
    FakeSeparator.instances = []
    FakeSeparator.pending_impl = None
    yield
    FakeSeparator.instances = []
    FakeSeparator.pending_impl = None


def _separate_writing_custom_names(output_dir: Path, input_path: Path):
    _write_wav(output_dir / "vocals.wav", value=10)
    _write_wav(output_dir / "instrumental.wav", value=100)
    return [
        str(output_dir / "vocals.wav"),
        str(output_dir / "instrumental.wav"),
    ]


def _separate_writing_default_names(output_dir: Path, input_path: Path):
    # What audio-separator writes when custom_output_names is ignored.
    _write_wav(output_dir / "song_(Vocals).wav", value=10)
    _write_wav(output_dir / "song_(Instrumental).wav", value=100)
    return [
        str(output_dir / "song_(Vocals).wav"),
        str(output_dir / "song_(Instrumental).wav"),
    ]


def _run(tmp_path: Path, separate_impl) -> PreprocessResult:
    FakeSeparator.pending_impl = separate_impl
    input_path = tmp_path / "song.mp3"
    input_path.write_bytes(b"fake audio bytes")
    pre = VocalRemovalPreprocessor()
    return pre.process(input_path, tmp_path / "out", "cuda")


def test_preprocessor_uses_the_configured_model_and_settings(tmp_path, monkeypatch):
    _install_fake_separator(monkeypatch)
    result = _run(tmp_path, _separate_writing_custom_names)

    sep = FakeSeparator.instances[-1]
    assert sep.loaded_models == ["vocals_mel_band_roformer.ckpt"]
    assert sep.separate_calls[0][1] == {
        "Vocals": "vocals",
        "Instrumental": "instrumental",
        "other": "instrumental",
        "Other": "instrumental",
    }
    assert result.processor_id == "vocal-removal"
    assert result.model_id == "vocals_mel_band_roformer.ckpt"
    assert result.instrumental_path == tmp_path / "out" / "instrumental.wav"
    assert result.vocals_path == tmp_path / "out" / "vocals.wav"
    assert result.audio_for_transcription == result.instrumental_path
    assert result.settings["model_id"] == "vocals_mel_band_roformer.ckpt"
    assert result.settings["device"] == "cuda"
    assert result.settings["output_format"] == "WAV"
    assert result.duration_seconds > 0


def test_preprocessor_finds_stems_with_default_names(tmp_path, monkeypatch):
    _install_fake_separator(monkeypatch)
    result = _run(tmp_path, _separate_writing_default_names)
    assert result.instrumental_path.name == "song_(Instrumental).wav"
    assert result.vocals_path.name == "song_(Vocals).wav"


def test_preprocessor_finds_instrumental_named_other(tmp_path, monkeypatch):
    # audio-separator 0.47 + the Kim mel-band-roformer vocals model names the
    # secondary stem "(other)" and ignores custom names for it, while the
    # vocals file does get its custom name.
    _install_fake_separator(monkeypatch)

    def other_naming(output_dir: Path, input_path: Path):
        _write_wav(output_dir / "vocals.wav", value=10)
        _write_wav(output_dir / "input_(other)_vocals_mel_band_roformer.wav", value=100)
        return [
            str(output_dir / "input_(other)_vocals_mel_band_roformer.wav"),
            str(output_dir / "vocals.wav"),
        ]

    result = _run(tmp_path, other_naming)
    assert result.instrumental_path.name == "input_(other)_vocals_mel_band_roformer.wav"
    assert result.vocals_path.name == "vocals.wav"


def test_preprocessor_resolves_relative_stem_paths(tmp_path, monkeypatch):
    # audio-separator 0.47 returns bare file names (relative to output_dir).
    _install_fake_separator(monkeypatch)

    def bare_names(output_dir: Path, input_path: Path):
        _write_wav(output_dir / "vocals.wav", value=10)
        _write_wav(output_dir / "instrumental.wav", value=100)
        return ["vocals.wav", "instrumental.wav"]

    result = _run(tmp_path, bare_names)
    assert result.instrumental_path.is_absolute()
    assert result.instrumental_path.is_file()
    assert result.vocals_path.is_absolute()
    assert result.vocals_path.is_file()


def test_preprocessor_raises_when_instrumental_is_missing(tmp_path, monkeypatch):
    _install_fake_separator(monkeypatch)

    def only_vocals(output_dir: Path, input_path: Path):
        _write_wav(output_dir / "vocals.wav")
        return [str(output_dir / "vocals.wav")]

    with pytest.raises(PreprocessError, match="no instrumental stem"):
        _run(tmp_path, only_vocals)


def test_preprocessor_maps_out_of_memory(tmp_path, monkeypatch):
    _install_fake_separator(monkeypatch)

    def oom(output_dir: Path, input_path: Path):
        raise RuntimeError("CUDA out of memory while separating")

    with pytest.raises(PreprocessError, match="out of GPU memory"):
        _run(tmp_path, oom)


def test_preprocessor_maps_model_load_failure(tmp_path, monkeypatch):
    _install_fake_separator(monkeypatch)
    monkeypatch.setattr(
        FakeSeparator,
        "load_model",
        lambda self, model_filename: (_ for _ in ()).throw(
            RuntimeError("download failed")
        ),
    )
    input_path = tmp_path / "song.mp3"
    input_path.write_bytes(b"x")
    with pytest.raises(PreprocessError, match="could not load separation model"):
        VocalRemovalPreprocessor().process(input_path, tmp_path / "out", "cpu")


def test_preprocessor_requires_ffmpeg(tmp_path, monkeypatch):
    _install_fake_separator(monkeypatch)
    monkeypatch.setattr("shutil.which", lambda name: None)
    input_path = tmp_path / "song.mp3"
    input_path.write_bytes(b"x")
    with pytest.raises(PreprocessError, match="ffmpeg"):
        VocalRemovalPreprocessor().process(input_path, tmp_path / "out", "cpu")


def test_preprocessor_reports_a_missing_input_file(tmp_path, monkeypatch):
    _install_fake_separator(monkeypatch)
    with pytest.raises(PreprocessError, match="not found"):
        VocalRemovalPreprocessor().process(
            tmp_path / "missing.mp3", tmp_path / "out", "cpu"
        )


def test_preprocessor_keeps_the_original_input_untouched(tmp_path, monkeypatch):
    _install_fake_separator(monkeypatch)
    input_path = tmp_path / "song.mp3"
    input_path.write_bytes(b"fake audio bytes")
    FakeSeparator.pending_impl = _separate_writing_custom_names
    VocalRemovalPreprocessor().process(input_path, tmp_path / "out", "cpu")
    # The separation reads a copy in its own output dir; the upload is intact.
    assert input_path.read_bytes() == b"fake audio bytes"


# ---------------------------------------------------------------- StemStore


def test_stem_store_roundtrip(tmp_path):
    store = StemStore()
    store.register("run1", tmp_path, {"instrumental": tmp_path / "i.wav"})
    assert store.get("run1", "instrumental") == tmp_path / "i.wav"
    assert store.get("run1", "vocals") is None
    assert store.get("unknown", "instrumental") is None


def test_stem_store_expires_by_ttl(tmp_path):
    clock = [1000.0]
    store = StemStore(ttl_s=60.0, time_fn=lambda: clock[0])
    store.register("run1", tmp_path, {"instrumental": tmp_path / "i.wav"})
    clock[0] += 61.0
    assert store.get("run1", "instrumental") is None


def test_stem_store_caps_run_count(tmp_path):
    clock = [1000.0]
    store = StemStore(max_runs=2, time_fn=lambda: clock[0])
    dirs = []
    for i in range(3):
        d = tmp_path / f"run{i}"
        d.mkdir()
        dirs.append(d)
        store.register(f"run{i}", d, {"instrumental": d / "i.wav"})
        clock[0] += 1
    assert store.get("run0", "instrumental") is None  # oldest evicted
    assert store.get("run2", "instrumental") is not None
    assert not dirs[0].exists()  # evicted dir removed from disk
    assert dirs[2].exists()


def test_stem_store_sweeps_orphan_dirs(tmp_path):
    import os

    clock = [1000.0]
    store = StemStore(ttl_s=60.0, time_fn=lambda: clock[0])
    old = tmp_path / "muscriptor-stems-old"
    old.mkdir()
    fresh = tmp_path / "muscriptor-stems-fresh"
    fresh.mkdir()
    old_time = clock[0] - 120.0
    os.utime(old, (old_time, old_time))
    store.sweep_orphans(tmp_path)
    assert not old.exists()
    assert fresh.exists()


# --------------------------------------------------- Server integration (SSE)


class FakePreprocessor:
    """Fake AudioPreprocessor: records calls, writes real stem files."""

    processor_id = "fake-vocal-removal"

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list = []
        self.error = error

    def process(self, input_path, output_dir, device, progress_callback=None):
        from muscriptor.preprocessing.models import SeparationSettings

        self.calls.append((Path(input_path), Path(output_dir), device))
        if self.error is not None:
            raise self.error
        output_dir = Path(output_dir)
        _write_wav(output_dir / "vocals.wav", value=10)
        _write_wav(output_dir / "instrumental.wav", value=100)
        return PreprocessResult(
            input_path=Path(input_path),
            audio_for_transcription=output_dir / "instrumental.wav",
            vocals_path=output_dir / "vocals.wav",
            instrumental_path=output_dir / "instrumental.wav",
            processor_id=self.processor_id,
            model_id="fake-model",
            model_version=None,
            settings=SeparationSettings(device=device).to_dict(),
            duration_seconds=0.1,
        )


_S0 = NoteStartEvent(pitch=60, start_time=0.0, index=0, instrument="piano")
_TWO_NOTES = [
    _S0,
    NoteEndEvent(end_time=0.5, start_event=_S0),
]


def _app_with_preprocessor(preprocessor, model=None) -> TestClient:
    return TestClient(
        create_app(
            model or make_model(events=_TWO_NOTES),
            preprocessor_factory=lambda: preprocessor,
        )
    )


def _post(client: TestClient, tmp_path: Path, remove_vocals: bool = False):
    return client.post(
        "/transcribe",
        files={"file": ("silent.wav", _wav_bytes(tmp_path), "audio/wav")},
        data={"remove_vocals": "true"} if remove_vocals else {},
    )


def test_without_remove_vocals_the_preprocessor_is_never_used(tmp_path):
    created = []

    def factory():
        created.append(1)
        return FakePreprocessor()

    model = make_model(events=_TWO_NOTES)
    client = TestClient(create_app(model, preprocessor_factory=factory))
    resp = _post(client, tmp_path)
    assert resp.status_code == 200
    parsed = _parse_sse(resp.text)
    # Plain pipeline: no stage/error events, final event without stem keys.
    assert all(
        ev["type"] in {"start", "end", "transcription_complete"} for ev in parsed
    )
    assert "stems" not in parsed[-1]
    assert "from_instrumental" not in parsed[-1]
    # The preprocessor was never instantiated (lazy factory) nor called.
    assert created == []
    # And the model received the decoded original upload (a silent WAV).
    wav_arg, sr_arg = model.transcribe.call_args[0][0]
    assert sr_arg == 16000
    assert float(wav_arg.abs().max()) == 0.0


def test_with_remove_vocals_the_model_transcribes_the_instrumental(tmp_path):
    import torch

    pre = FakePreprocessor()
    model = make_model(events=_TWO_NOTES)
    client = _app_with_preprocessor(pre, model=model)
    resp = _post(client, tmp_path, remove_vocals=True)
    assert resp.status_code == 200
    parsed = _parse_sse(resp.text)

    assert [ev["type"] for ev in parsed] == [
        "stage",
        "stage",
        "stage",
        "stage",
        "start",
        "end",
        "stage",  # midi
        "transcription_complete",
    ]
    assert [ev["stage"] for ev in parsed[:4]] == [
        "prepare",
        "vocal_removal",
        "instrumental",
        "transcription",
    ]
    final = parsed[-1]
    assert final["from_instrumental"] is True
    assert final["stems"]["vocals"].startswith("/stems/")
    assert final["stems"]["instrumental"].startswith("/stems/")

    # The model ran on the instrumental stem (sample value 100), not on the
    # silent original upload, and preprocessed exactly once.
    assert model.transcribe.call_count == 1
    wav_arg, sr_arg = model.transcribe.call_args[0][0]
    assert sr_arg == 16000
    assert wav_arg.shape[0] == 1
    assert torch.allclose(wav_arg, torch.full_like(wav_arg, 100.0 / 32768.0))
    assert len(pre.calls) == 1


def test_stems_are_downloadable_and_unknown_runs_404(tmp_path):
    pre = FakePreprocessor()
    client = _app_with_preprocessor(pre)
    resp = _post(client, tmp_path, remove_vocals=True)
    final = _parse_sse(resp.text)[-1]
    run_id = final["stems"]["vocals"].split("/")[2]

    vocals = client.get(f"/stems/{run_id}/vocals")
    assert vocals.status_code == 200
    assert vocals.headers["content-type"].startswith("audio/wav")
    instrumental = client.get(f"/stems/{run_id}/instrumental")
    assert instrumental.status_code == 200
    assert client.get(f"/stems/{run_id}/nope").status_code == 404
    assert client.get("/stems/deadbeef/vocals").status_code == 404


def test_preprocessing_failure_stops_before_transcription(tmp_path):
    pre = FakePreprocessor(error=PreprocessError("separation exploded"))
    model = make_model(events=_TWO_NOTES)
    client = _app_with_preprocessor(pre, model=model)
    resp = _post(client, tmp_path, remove_vocals=True)
    # The stream opens, then reports the error; no notes, no MIDI.
    assert resp.status_code == 200
    parsed = _parse_sse(resp.text)
    assert parsed == [
        {"type": "stage", "stage": "prepare"},
        {"type": "stage", "stage": "vocal_removal"},
        {"type": "error", "detail": "separation exploded"},
    ]
    model.transcribe.assert_not_called()


def test_midi_endpoint_transcribes_the_instrumental(tmp_path):
    import torch

    pre = FakePreprocessor()
    model = make_model()
    client = _app_with_preprocessor(pre, model=model)
    resp = client.post(
        "/transcribe/midi",
        files={"file": ("silent.wav", _wav_bytes(tmp_path), "audio/wav")},
        data={"remove_vocals": "true"},
    )
    assert resp.status_code == 200
    assert resp.content == FAKE_MIDI
    wav_arg, _ = model.transcribe_and_postprocess.call_args[0][0]
    assert torch.allclose(wav_arg, torch.full_like(wav_arg, 100.0 / 32768.0))


def test_midi_endpoint_removes_the_run_dir_when_done(tmp_path):
    # The MIDI response carries no downloadable stems, so the scratch
    # directory must not outlive the request (no orphan-sweep wait).
    import tempfile

    pre = FakePreprocessor()
    model = make_model()
    client = _app_with_preprocessor(pre, model=model)
    tempdir = Path(tempfile.gettempdir())
    before = set(tempdir.glob("muscriptor-stems-*"))
    resp = client.post(
        "/transcribe/midi",
        files={"file": ("silent.wav", _wav_bytes(tmp_path), "audio/wav")},
        data={"remove_vocals": "true"},
    )
    assert resp.status_code == 200
    assert len(pre.calls) == 1  # preprocessing actually ran
    assert set(tempdir.glob("muscriptor-stems-*")) - before == set()

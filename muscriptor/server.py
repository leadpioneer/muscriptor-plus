"""FastAPI server exposing transcription as an SSE event stream.

POST /transcribe with an audio file (multipart/form-data field `file`; WAV,
or any format soundfile/libsndfile can read — mp3, flac, ogg, m4a, …) returns
`text/event-stream`. Each event's data is a JSON dict tagged by `type`:
`start` / `end` note events (same shape as `muscriptor.main._event_to_dict`),
`progress` chunk anchors (`{completed, total}`), and a final
`transcription_complete` event carrying the base64-encoded .mid file (`data`)
plus the detected `beat_grid`
(`{bpm, beats_per_bar, first_downbeat, onset_delay}`, or null if no tempo was
found). `onset_delay` is how late the streamed note times are against those
beats: the MIDI has it taken out already, an SSE consumer has to subtract it.

POST /transcribe/midi takes the same upload but blocks until transcription
completes and returns the raw `audio/midi` bytes directly (no SSE, no
base64), with a `Content-Disposition: attachment` header. Audio longer than
15 minutes is rejected with 413.

POST /sheets takes a MIDI upload instead of audio (the `quantized_midi` from
/transcribe, with `quantized=true`) and returns every file
`muscriptor.utils.sheets.write_sheets` engraves from it — MusicXML, the full
score, one PDF per instrument — as a single uncompressed zip. It needs
MuseScore 4+ on the server, and answers 503 when there is none.

POST /transcribe and /transcribe/midi also accept `remove_vocals=true`: the
upload first goes through an opt-in preprocessing step (lead-vocal removal via
`muscriptor.preprocessing`, using audio-separator) and the model transcribes
the instrumental stem instead of the original mix. The SSE stream then carries
`stage` events (preprocessing phases), a terminal `error` event when
preprocessing fails (transcription never silently falls back to the original
audio), and — on /transcribe — `stems` download URLs in the final event, served
by GET /stems/{run_id}/{stem} until the store reaps them.
"""

import asyncio
import base64
import dataclasses
import gc
import io
import json
import logging
import os
import shutil
import tempfile
import threading
import time
import uuid
import wave
import zipfile
from pathlib import Path
from typing import Annotated, Callable, Literal
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.middleware.gzip import GZipMiddleware

from muscriptor.accelerator import current_accelerator
from muscriptor.events import NoteEndEvent, NoteStartEvent, ProgressEvent
from muscriptor.preprocessing import (
    AudioPreprocessor,
    PreprocessError,
    StemStore,
    VocalRemovalPreprocessor,
)
from muscriptor.soundfonts import SF3_URL
from muscriptor.tokenizer.mt3 import MT3_FULL_PLUS_GROUP_NAMES
from muscriptor.transcription_model import TranscriptionModel
from muscriptor.utils.audio import _read_non_wav_file, _read_wav_file
from muscriptor.utils.beats import BeatDetectionError, TempoDetection
from muscriptor.utils.download import download_if_necessary
from muscriptor.utils.sheets import (
    MuseScoreError,
    MuseScoreNotFoundError,
    _run,
    write_sheets,
)


def _make_release_once(lock: threading.Lock):
    """Return a callable that releases `lock` at most once.

    Safe to call from multiple cleanup paths (generator finally + response
    background task), possibly from different threads, without risking a
    double-release RuntimeError.
    """
    guard = threading.Lock()
    released = False

    def release():
        nonlocal released
        with guard:
            if released:
                return
            released = True
        lock.release()

    return release


_MAX_TRANSCRIBE_MIDI_DURATION_S = 15 * 60
# Comfortably above any 15-minute upload (the largest legitimate WAV is ~260 MB
# at 48 kHz 24-bit stereo); stops a giant upload from being read into a bytes
# object and decoded into an even larger float tensor.
_MAX_UPLOAD_BYTES = 512 * 1024 * 1024
# An arrangement document is well under a megabyte even at the note cap;
# parsing a 512 MB one into Python objects would take gigabytes.
_ARRANGEMENT_MAX_BYTES = 16 * 1024 * 1024
# MIDI uploads are a few hundred KB even for a long song (5000 notes is ~40 KB).
# Capping them at a few MB stops parallel /auralize, /sheets or /arrange
# requests from each holding a 512 MB bytes object before the render lock is
# even taken, and keeps mido's ~100x in-memory expansion bounded.
_MIDI_MAX_BYTES = 2 * 1024 * 1024
# Body caps, keyed by endpoint. FastAPI parses the whole multipart body before
# the handler runs, so the per-field `file.size` checks below only fire after
# the body has already been spooled to disk. The middleware compares these
# caps against the incoming stream and answers 413 before that happens; the
# extra megabyte leaves room for the multipart boundaries and form fields.
_MULTIPART_OVERHEAD_BYTES = 1024 * 1024
_MAX_REQUEST_BYTES = _MAX_UPLOAD_BYTES + _MULTIPART_OVERHEAD_BYTES
_UPLOAD_BODY_LIMITS = {
    "/transcribe": _MAX_REQUEST_BYTES,
    "/transcribe/midi": _MAX_REQUEST_BYTES,
    "/auralize": _MAX_UPLOAD_BYTES + _MIDI_MAX_BYTES + _MULTIPART_OVERHEAD_BYTES,
    "/sheets": _MIDI_MAX_BYTES + _MULTIPART_OVERHEAD_BYTES,
    "/arrange/guitar": _MIDI_MAX_BYTES + _MULTIPART_OVERHEAD_BYTES,
    "/arrange/guitar/midi": _ARRANGEMENT_MAX_BYTES + _MULTIPART_OVERHEAD_BYTES,
    "/arrange/guitar/tab": _ARRANGEMENT_MAX_BYTES + _MULTIPART_OVERHEAD_BYTES,
    "/arrange/guitar/musicxml": _ARRANGEMENT_MAX_BYTES + _MULTIPART_OVERHEAD_BYTES,
    "/arrange/guitar/pdf": _ARRANGEMENT_MAX_BYTES + _MULTIPART_OVERHEAD_BYTES,
    "/model": _MULTIPART_OVERHEAD_BYTES,
}
# 8 kHz is the lowest rate a codec produces, 768 kHz the highest libsndfile
# reads. A bogus header rate (0, 1000003, …) used to divide by zero or make
# the resampler allocate tens of GB.
_MIN_SAMPLE_RATE = 8000
_MAX_SAMPLE_RATE = 768000
# FluidSynth synthesizes far faster than real time; this only caps a runaway
# (e.g. a hostile MIDI whose ticks stretch to dozens of hours).
_MAX_AURALIZE_MIDI_DURATION_S = 30 * 60
# Seconds a concurrent /sheets, /arrange/guitar, or /auralize request waits in
# line for the active job to finish before giving up with 503.
_RENDER_LOCK_TIMEOUT_S = 30.0

SHEETS_ZIP_NAME = "sheets.zip"
# Already-compressed downloads bypass GZipMiddleware (a response that sets
# Content-Encoding is passed through): re-gzipping a 38 MB soundfont or a
# multi-hundred-MB WAV burns the event loop for seconds and stalls every
# other request. Text (arrangement JSON, MusicXML, tab) stays compressed.
_NO_GZIP = {"Content-Encoding": "identity"}


def _attachment_header(stem: str, extension: str) -> str:
    """Content-Disposition for a download named after a client-supplied stem.

    Strips path segments, control characters (CR/LF), quotes and backslashes,
    and falls back to an ASCII name + RFC 5987 `filename*` when non-ASCII.
    """
    base = Path(stem).name if stem else ""
    clean = (
        "".join(c for c in base if c >= " " and c not in ('"', "\\", ";")).strip()
        or "arrangement"
    )
    try:
        clean.encode("latin-1")
    except UnicodeEncodeError:
        return (
            f'attachment; filename="arrangement{extension}"; '
            f"filename*=UTF-8''{quote(clean + extension)}"
        )
    return f'attachment; filename="{clean}{extension}"'


def _reject_bad_sample_rate(sr) -> None:
    """Refuse a header sample rate that would break decoding or resampling."""
    if not _MIN_SAMPLE_RATE <= sr <= _MAX_SAMPLE_RATE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unsupported sample rate {sr}; "
                f"expected {_MIN_SAMPLE_RATE}..{_MAX_SAMPLE_RATE} Hz"
            ),
        )


def _decode_audio(data: bytes, filename: str | None) -> tuple:
    """Decode an upload into `(wav, sr)`, WAV first then anything libsndfile reads.

    Runs off the event loop (the stdlib WAV reader and soundfile both block).
    An undecodable upload is the client's fault, so it is reported as a 400.
    """
    try:
        wav, sr = _read_wav_file(io.BytesIO(data))
    except (wave.Error, EOFError, ValueError):
        try:
            wav, sr = _read_non_wav_file(io.BytesIO(data))
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"could not decode audio file '{filename}': {e}",
            ) from e
    _reject_bad_sample_rate(sr)
    return wav, sr


def _reject_oversized_upload(file: UploadFile, limit: int = _MAX_UPLOAD_BYTES) -> None:
    """Refuse an upload larger than `limit` before it is read.

    `file.size` is filled by the multipart parser as the body spools to a temp
    file, so checking it here costs nothing and stops a giant upload from being
    loaded into a bytes object (and then decoded into an even larger float
    tensor) by one or several parallel requests. The body itself is already
    capped before parsing by `_UploadBodyLimit`.
    """
    if file.size is not None and file.size > limit:
        raise HTTPException(
            status_code=413,
            detail=(
                f"upload is {file.size / (1024 * 1024):.0f} MB; "
                f"the limit is {limit // (1024 * 1024)} MB"
            ),
        )


async def _send_too_large(send, limit: int) -> None:
    """Answer 413 before (or while) an over-limit body is parsed."""
    body = json.dumps(
        {"detail": f"request body exceeds the {limit // (1024 * 1024)} MB limit"}
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class _UploadBodyLimit:
    """Cap upload bodies before Starlette's multipart parser spools them.

    FastAPI parses the whole body before the handler runs, so
    `_reject_oversized_upload` alone lets one huge POST fill the host disk.
    This counts bytes as they arrive — also for chunked bodies, which carry no
    Content-Length — and answers 413 as soon as the path's cap is crossed.
    """

    def __init__(self, app, limits: dict[str, int]) -> None:
        self.app = app
        self.limits = limits

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return
        limit = self.limits.get(scope["path"], _MAX_REQUEST_BYTES)
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _send_too_large(send, limit)
            return
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # FastAPI turns this into its 413 response while parsing.
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"request body exceeds the "
                            f"{limit // (1024 * 1024)} MB limit"
                        ),
                    )
            return message

        await self.app(scope, limited_receive, send)


def _serialized(
    lock: threading.Lock,
    fn: Callable,
    *args,
    busy_detail: str = "server busy: another sheet render is in progress",
    **kwargs,
):
    """Run `fn(*args, **kwargs)` under `lock`, waiting up to `_RENDER_LOCK_TIMEOUT_S`."""
    if not lock.acquire(timeout=_RENDER_LOCK_TIMEOUT_S):
        raise HTTPException(status_code=503, detail=busy_detail)
    return _run_locked(lock, fn, *args, **kwargs)


def _run_locked(lock: threading.Lock, fn: Callable, *args, **kwargs):
    """Run `fn` and release a lock the caller already acquired.

    Releasing from the worker thread (not the awaiting coroutine) keeps the
    lock held if the request is cancelled while `fn` is still running.
    """
    try:
        return fn(*args, **kwargs)
    finally:
        lock.release()


def _reject_long_audio(file: UploadFile, *, check_duration: bool = True) -> None:
    """Validate audio header sample rate and (optionally) cap duration before decoding.

    The underlying spooled file is seekable, so the header alone yields the
    sample rate and duration without reading the samples into memory. WAV is
    read with the stdlib; anything else (mp3, flac, ogg, m4a, …) is probed with
    soundfile's `info` (header only). An undecodable upload passes through —
    `_decode_audio` then reports it as a 400.
    """
    try:
        file.file.seek(0)
        try:
            with wave.open(file.file, "rb") as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
        except (wave.Error, EOFError, ValueError, OSError):
            import soundfile as sf

            info = sf.info(file.file)
            sr = info.samplerate
            n_frames = info.frames
    except Exception:  # noqa: BLE001 — undecodable uploads are handled downstream
        return
    finally:
        try:
            file.file.seek(0)
        except (OSError, ValueError):
            pass
    _reject_bad_sample_rate(sr)
    if check_duration:
        duration_s = n_frames / sr
        if duration_s > _MAX_TRANSCRIBE_MIDI_DURATION_S:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"audio file is {duration_s / 60:.1f} minutes long; "
                    f"the limit is {_MAX_TRANSCRIBE_MIDI_DURATION_S // 60:.0f} minutes"
                ),
            )


def _midi_duration_s(midi_bytes: bytes) -> float | None:
    """Duration of a MIDI file in seconds, or None if it can't be parsed.

    An unparseable upload is left to the synthesis step, which reports it as a
    500 the way any other bad MIDI already is.
    """
    from mido import MidiFile

    try:
        return MidiFile(file=io.BytesIO(midi_bytes)).length
    except Exception:  # noqa: BLE001 — invalid MIDI is handled downstream
        return None


def engrave_to_zip(midi_bytes: bytes, quantized: bool = False) -> bytes:
    """Engrave `midi_bytes` and pack everything written into one zip.

    Runs `write_sheets` into a scratch directory that is thrown away once the
    archive is built, so the server keeps nothing on disk between requests.
    Member names are the bare filenames — the directory layout documented under
    "Sheet music" in the README, flattened by one level.

    Stored, not deflated: the client unpacks this archive in the browser to
    offer the files one at a time, and all but the MusicXML are PDFs, which
    carry compression of their own.
    """
    with tempfile.TemporaryDirectory(prefix="muscriptor-sheets-") as tmp:
        written = write_sheets(midi_bytes, Path(tmp), quantized=quantized)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as archive:
            for path in written:
                archive.write(path, arcname=path.name)
        return buf.getvalue()


def _engrave_arrangement_pdf(binary: str, xml_bytes: bytes, stem: str) -> bytes:
    """Engrave one arrangement's MusicXML into a score PDF via MuseScore.

    Runs headless through `sheets._run` (which sets the offscreen Qt platform
    and a shared timeout) in a throwaway directory, then packs the PDF and the
    intermediate MusicXML into a zip. Raises HTTPException(500) when MuseScore
    runs but produces no usable PDF.
    """
    with tempfile.TemporaryDirectory(prefix="guitar_pdf_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        xml_path = tmp_path / f"{stem}.musicxml"
        xml_path.write_bytes(xml_bytes)
        pdf_path = tmp_path / f"{stem}.pdf"
        proc = _run(binary, ["-o", str(pdf_path), str(xml_path)])
        if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "fingering_export_failed",
                    "message": (
                        "MuseScore ran but produced no PDF for this arrangement"
                    ),
                    "details": {"stderr": (proc.stderr or "")[-2000:]},
                },
            )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.write(pdf_path, "full_score.pdf")
            archive.write(xml_path, f"{stem}.musicxml")
        return buffer.getvalue()


def _render_auralize(mode: str, midi_data: bytes, audio: UploadFile | None) -> bytes:
    """Write the uploads to scratch files, render the WAV and read it back.

    Runs in a worker thread under `auralize_lock`, so the (up to 512 MB) audio
    upload is spooled to disk only by the request actually being rendered —
    parallel requests are refused with a 503 before they read anything.
    """
    from muscriptor.utils.auralization import auralize as do_auralize
    from muscriptor.utils.auralization import synthesize

    with tempfile.TemporaryDirectory(prefix="muscriptor-auralize-") as tmp:
        midi_path = os.path.join(tmp, "input.mid")
        with open(midi_path, "wb") as f:
            f.write(midi_data)
        out_path = os.path.join(tmp, "output.wav")
        if mode == "synth":
            synthesize(midi_path=midi_path, output_path=out_path)
        else:
            assert audio is not None  # the endpoint refuses mix without audio
            suffix = Path(audio.filename or "audio.wav").suffix.lower() or ".wav"
            audio_path = os.path.join(tmp, "audio" + suffix)
            with open(audio_path, "wb") as f:
                shutil.copyfileobj(audio.file, f)
            do_auralize(
                midi_path=midi_path,
                original_audio_path=audio_path,
                output_path=out_path,
            )
        with open(out_path, "rb") as f:
            return f.read()


def event_to_dict(ev: NoteStartEvent | NoteEndEvent) -> dict:
    if isinstance(ev, NoteStartEvent):
        return {"type": "start", **dataclasses.asdict(ev)}
    return {
        "type": "end",
        "end_time": ev.end_time,
        "start_event_index": ev.start_event_index,
    }


def _sse(payload: dict) -> str:
    """One SSE frame: a JSON dict on a single `data:` line."""
    return f"data: {json.dumps(payload)}\n\n"


def create_app(
    model: TranscriptionModel,
    web_dir: str | Path | None = None,
    model_loader: Callable[[str], TranscriptionModel] | None = None,
    model_size: str = "medium",
    preprocessor_factory: Callable[[], AudioPreprocessor] | None = None,
    stem_store: StemStore | None = None,
    idle_unload_s: float | None = None,
) -> FastAPI:
    app = FastAPI(title="muscriptor")
    # Reject an over-limit upload while it is still arriving (see
    # `_UploadBodyLimit`); the per-field checks in the handlers stay as a
    # backstop.
    app.add_middleware(_UploadBodyLimit, limits=_UPLOAD_BODY_LIMITS)
    # Arrangement documents are several MB of per-note fingering tables; gzip
    # cuts the wire size roughly tenfold. The middleware skips SSE itself.
    # shortcut: the dialog still re-fetches the whole document on every click;
    # upgrade to a per-note legal-table endpoint if that latency ever matters.
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)

    # Optional preprocessing (lead-vocal removal). The factory is only ever
    # called when a request actually asks for preprocessing, and the default
    # implementation imports `audio_separator` lazily inside `process()`, so
    # servers without the dependency keep working as long as the feature
    # stays off. Tests inject a fake factory here.
    preprocess = preprocessor_factory or (lambda: VocalRemovalPreprocessor())
    stems = stem_store or StemStore()

    def _remove_vocals(data: bytes, filename: str | None) -> tuple:
        """Run vocal removal on an upload, returning (result, run_dir).

        The upload bytes are written unchanged (original file preserved) into
        a per-run scratch directory that also receives the stems, so the
        download endpoint can serve them until the StemStore reaps the dir.
        Raises `PreprocessError` — callers turn that into their error shape
        (SSE event / HTTPException) and clean up the scratch dir themselves.
        """
        run_id = uuid.uuid4().hex
        # Reap abandoned runs from earlier requests before adding another
        # scratch dir to the same temp location.
        stems.sweep_orphans(Path(tempfile.gettempdir()))
        run_dir = Path(tempfile.gettempdir()) / f"muscriptor-stems-{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename or "audio.wav").suffix or ".wav"
        input_path = run_dir / f"input{suffix}"
        input_path.write_bytes(data)
        try:
            device = str(current_accelerator())
        except RuntimeError:
            device = "cpu"
        try:
            result = preprocess().process(input_path, run_dir, device)
        except Exception:
            # No stems were produced — don't leave the scratch dir behind.
            shutil.rmtree(run_dir, ignore_errors=True)
            raise
        return result, run_dir

    def _stems_payload(run_id: str, produced: dict[str, Path]) -> dict:
        """Download URLs for the stems this run actually registered."""
        return {stem: f"/stems/{run_id}/{stem}" for stem in produced}

    # ---- Model unloading (free VRAM while the server sits idle) -----------
    # The loaded model keeps its weights resident in GPU memory even when
    # nothing is happening. Dropping the object returns that memory to the
    # driver (after an allocator flush); because the weights are cached on
    # disk, the next request just reloads them in a few seconds.
    # `model_state["model"] is None` + status "unloaded" marks that state.
    last_model_use = [time.monotonic()]

    def _drop_model() -> None:
        old = model_state["model"]
        model_state["model"] = None
        model_state["status"] = "unloaded"
        model_state["error"] = None
        # Dropping the last reference doesn't return cached CUDA blocks to the
        # driver unless the allocator is told to (same as the model switcher).
        del old
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 — cleanup must never raise
            pass

    def unload_model() -> dict:
        """Unload the live model, refusing while it's in use."""
        if model_loader is None:
            # Without a loader there's no way back: don't strand the server.
            raise HTTPException(
                status_code=501,
                detail="model unloading is not available on this server",
            )
        if transcribe_lock.locked():
            raise HTTPException(
                status_code=409,
                detail="a transcription is in progress; try again when it finishes",
            )
        if model_state["status"] == "loading":
            raise HTTPException(
                status_code=409, detail="a model is already being loaded"
            )
        if model_state["model"] is not None:
            _drop_model()
        return {"model": model_state["size"], "status": "unloaded"}

    def ensure_model() -> TranscriptionModel:
        """The live model, reloading it first after an unload.

        Callers hold the transcription lock, so a reload can't race a running
        transcription. Weights come from the local cache — seconds, no network.
        """
        last_model_use[0] = time.monotonic()
        # A /model swap is in flight: the old weights are still live, but a
        # transcription started now would run on them while the loader frees
        # their memory. This backstops the pre-lock check in
        # acquire_transcribe_lock against the narrow window before the lock is
        # actually acquired (the handler maps this to an error/503).
        if model_state["status"] == "loading":
            raise RuntimeError("a model is being loaded; try again shortly")
        if model_state["model"] is not None:
            return model_state["model"]
        model_state["status"] = "loading"
        model_state["error"] = None
        try:
            model_state["model"] = model_loader(model_state["size"])
        except Exception as e:  # noqa: BLE001 — surfaced to the client
            model_state["status"] = "error"
            model_state["error"] = str(e)
            raise RuntimeError(f"model reload failed: {e}") from e
        model_state["status"] = "ready"
        return model_state["model"]

    if model_loader is not None and idle_unload_s is not None and idle_unload_s > 0:

        def idle_watcher() -> None:
            while True:
                time.sleep(min(30.0, idle_unload_s))
                try:
                    if (
                        time.monotonic() - last_model_use[0] >= idle_unload_s
                        and model_state["status"] == "ready"
                        and model_state["model"] is not None
                        and transcribe_lock.acquire(blocking=False)
                    ):
                        try:
                            # Re-check under the lock: a request that started
                            # while we were deciding must keep its model.
                            if (
                                time.monotonic() - last_model_use[0] >= idle_unload_s
                                and model_state["status"] == "ready"
                                and model_state["model"] is not None
                            ):
                                logger = logging.getLogger("muscriptor.server")
                                logger.info(
                                    "server idle for %.0fs — unloading the model "
                                    "to free VRAM",
                                    idle_unload_s,
                                )
                                _drop_model()
                        finally:
                            transcribe_lock.release()
                except Exception:  # noqa: BLE001 — the watcher must never die
                    continue

        threading.Thread(target=idle_watcher, daemon=True).start()

    # Mutable model holder: POST /model swaps the live model in place. Every
    # endpoint reads the current model through this dict, so a swap is atomic
    # from the request handlers' point of view (dict item assignment under the
    # GIL); swaps only happen between requests, guarded by the transcribe lock.
    model_state = {
        "model": model,
        "size": model_size,
        "status": "ready",  # "ready" | "loading" | "error"
        "error": None,
    }

    transcribe_lock = threading.Lock()
    # MuseScore engraving is process-heavy (each render spawns a full MuseScore
    # process), so /sheets and /arrange/guitar/pdf serialize behind this lock
    # instead of letting N parallel requests spawn N processes. A second render
    # is refused with 503 rather than queueing a worker thread (see
    # `_serialized`).
    musescore_lock = threading.Lock()
    # One arrangement at a time: the solver is pure CPU (seconds per song) and
    # a handful of parallel uploads would otherwise occupy the whole thread
    # pool. Contenders get an immediate 503 instead of queueing a thread.
    arrange_lock = threading.Lock()
    # FluidSynth keeps a whole rendered mix in RAM (hundreds of MB) and spawns
    # its own process, so /auralize is serialized the same way. A second render
    # is refused at once rather than queueing behind the first.
    auralize_lock = threading.Lock()
    # State of the run currently holding the lock (or the last one to have held
    # it), guarded by `cancel_guard`: its cancel event and the id of the client
    # that started it. A new /transcribe from the SAME client (a resubmit in
    # the same browser tab) sets the cancel event so the in-flight run stops at
    # its next event boundary instead of transcribing to completion for a client
    # that has moved on. A request from a DIFFERENT client never preempts — it
    # waits for the lock like any other contender, so two independent browser
    # windows don't kill each other's transcription. This scoping must be done
    # here rather than by watching the socket: browser aborts don't always reach
    # us (e.g. port forwards / proxies keep the upstream connection open after
    # the browser aborts), so a same-tab resubmit can't be detected as a
    # disconnect.
    cancel_guard = threading.Lock()
    current_cancel: threading.Event | None = None
    current_client: str | None = None
    # Bound on how long a same-client resubmit waits for the run it just
    # cancelled to unwind and release the lock. That run stops within one
    # chunk boundary, so this only needs to cover that latency — unlike
    # genuine cross-client contention, which now fails instantly instead of
    # sitting on the connection (see below).
    preempt_wait_s = 5.0

    async def acquire_transcribe_lock(
        client_id: str | None, cancellable: bool
    ) -> tuple[threading.Event | None, Callable[[], None]]:
        """Acquire the single-transcription lock, preempting only a run started
        by this same `client_id` (a resubmit): that run is signalled to stop
        and this call waits up to `preempt_wait_s` for it to release the lock.
        A different client — or an anonymous API caller with no id — never
        preempts and is never preempted; it gets an immediate 503 instead of
        waiting, so a caller retrying against another machine (e.g. behind a
        load balancer like Traefik) doesn't have to hold the connection open.

        Returns `(cancel, release)`: `cancel` is the new run's cancel event
        (`None` when `cancellable` is False, e.g. the blocking /transcribe/midi
        render, which can't be stopped mid-flight); `release` frees the lock at
        most once, from whichever cleanup path runs first.
        """
        # Refuse while a model swap is loading: a transcription would run on the
        # outgoing weights while the loader frees their memory. The same 409 the
        # API documents for a second /model during a swap.
        if model_state["status"] == "loading":
            raise HTTPException(
                status_code=409,
                detail="a model is being loaded; try again shortly",
            )
        nonlocal current_cancel, current_client
        deadline: float | None = None
        while True:
            with cancel_guard:
                # Re-check each iteration so that even a same-client run which
                # became "current" while we were already waiting (a resubmit
                # that beat us to the lock) gets cancelled too — the newest
                # request from a given client always wins.
                preempting = (
                    current_cancel is not None
                    and client_id is not None
                    and current_client == client_id
                )
                if preempting:
                    current_cancel.set()
            if not preempting:
                acquired = await asyncio.to_thread(transcribe_lock.acquire, False)
                if not acquired:
                    raise HTTPException(
                        status_code=503,
                        detail="server busy: another transcription is in progress",
                    )
                break
            if deadline is None:
                deadline = time.monotonic() + preempt_wait_s
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HTTPException(
                    status_code=503,
                    detail="server busy: another transcription is in progress",
                )
            acquired = await asyncio.to_thread(
                transcribe_lock.acquire, True, min(0.1, remaining)
            )
            if acquired:
                break
        cancel = threading.Event() if cancellable else None
        with cancel_guard:
            current_cancel = cancel
            current_client = client_id
        return cancel, _make_release_once(transcribe_lock)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/instruments")
    async def list_instruments():
        return {"instruments": list(MT3_FULL_PLUS_GROUP_NAMES.keys())}

    @app.get("/soundfonts/MuseScore_General.sf3")
    async def soundfont() -> FileResponse:
        """Compressed soundfont for the web UI's in-browser synthesizer.

        Fetched from SF3_URL on first request (in a worker thread, so the
        event loop keeps serving) and cached locally.
        """
        path = await asyncio.to_thread(download_if_necessary, SF3_URL)
        return FileResponse(
            path, media_type="application/octet-stream", headers=_NO_GZIP
        )

    @app.post("/transcribe")
    async def transcribe(
        file: Annotated[UploadFile, File()],
        instruments: Annotated[list[str], Form(default_factory=list)],
        # "true" fails loudly on tempo detection errors, "false" doesn't even try
        detect_tempo: Annotated[TempoDetection, Form()] = "best-effort",
        # Opt-in preprocessing: strip the lead vocal and transcribe the
        # instrumental stem instead of the original mix.
        remove_vocals: Annotated[bool, Form()] = False,
        x_client_id: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        _reject_oversized_upload(file)
        _reject_long_audio(file, check_duration=False)

        unknown = [n for n in instruments if n not in MT3_FULL_PLUS_GROUP_NAMES]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"unknown instrument name(s): {', '.join(unknown)}",
            )

        # Acquire the single-transcription lock before reading or decoding the
        # upload: a 15-minute stereo file decodes to ~350 MB of float32, so
        # parallel uploads must not decode concurrently while the server
        # promises one transcription at a time. `release_lock` runs from
        # whichever cleanup path fires first: the generator's finally (normal
        # completion, errors, mid-stream disconnects), the StreamingResponse
        # background task (client disconnects before the generator is ever
        # iterated, so its finally would never run), or the except below when
        # validation fails before the response exists — either way the lock is
        # released exactly once and never leaked.
        cancel, release_lock = await acquire_transcribe_lock(
            x_client_id, cancellable=True
        )
        try:
            data = await file.read()
            # PCM WAV goes through the stdlib reader (keeps WAV decoding
            # byte-for-byte identical to the CLI); anything that isn't a
            # readable WAV (mp3, flac, ogg, m4a, …) falls back to
            # soundfile/libsndfile. Decoding blocks, so it runs in a worker
            # thread (see _decode_audio for the 400 on bad input).
            wav, sr = await asyncio.to_thread(_decode_audio, data, file.filename)
        except BaseException:
            release_lock()
            raise

        def gen():
            try:
                events: list[NoteStartEvent | NoteEndEvent] = []
                # Reload the model first if it was unloaded while idle: the
                # weights come from the local cache, so this is seconds.
                try:
                    model = ensure_model()
                except RuntimeError as e:
                    yield _sse({"type": "error", "detail": str(e)})
                    return
                # Without preprocessing this stays the exact (wav, sr) decoded
                # above — the original pipeline, byte for byte. With vocal
                # removal it is replaced by the decoded instrumental stem, so
                # both the note decoding and the beat-grid detection below run
                # on the same audio.
                transcription_wav = wav
                transcription_sr = sr
                run_id: str | None = None
                stems_payload: dict | None = None
                if remove_vocals:
                    # Separation runs inside this generator, under the same
                    # transcription lock the model uses: the GPU never runs
                    # separation and transcription at the same time.
                    yield _sse({"type": "stage", "stage": "prepare"})
                    try:
                        # The longest, most important preprocessing phase:
                        # loading the separation weights + the separation
                        # itself. Announced up front so the UI can show it
                        # while the (blocking) preprocessor call runs.
                        yield _sse({"type": "stage", "stage": "vocal_removal"})
                        result, run_dir_ = _remove_vocals(data, file.filename)
                    except PreprocessError as e:
                        yield _sse({"type": "error", "detail": str(e)})
                        return
                    yield _sse({"type": "stage", "stage": "instrumental"})
                    # audio-separator writes stems at 44.1 kHz regardless of the
                    # upload's rate, so the stem's own sample rate must ride
                    # along — using the original sr would stretch the note
                    # times and skew the BPM.
                    transcription_wav, transcription_sr = _read_non_wav_file(
                        result.audio_for_transcription
                    )
                    run_id = run_dir_.name.removeprefix("muscriptor-stems-")
                    produced = {
                        **(
                            {"vocals": result.vocals_path} if result.vocals_path else {}
                        ),
                        "instrumental": result.instrumental_path,
                    }
                    stems.register(run_id, run_dir_, produced)
                    stems_payload = _stems_payload(run_id, produced)
                    yield _sse({"type": "stage", "stage": "transcription"})
                # batch_size=1 so each chunk's notes stream out as soon as it is
                # generated, instead of waiting for a whole batch of chunks.
                # no_eos_is_ok=True so one runaway chunk that never emits EOS only
                # warns (and keeps its notes) instead of aborting the whole stream.
                # A RuntimeError here (e.g. CUDA OOM mid-generation) must end the
                # stream with a terminal error event, not a 200 whose body just
                # stops — the client would otherwise mark the run done without MIDI.
                try:
                    for ev in model.transcribe(
                        (transcription_wav, transcription_sr),
                        instruments=instruments or None,
                        batch_size=1,
                        no_eos_is_ok=True,
                    ):
                        # A newer request preempted this run — stop generating
                        # (closing the model.transcribe generator) and release the
                        # lock via the finally, at most one chunk after the signal.
                        if cancel.is_set():
                            return
                        if isinstance(ev, ProgressEvent):
                            # Coarse chunk-completion anchor — forward it but keep
                            # it out of the note list the MIDI file is built from.
                            payload = json.dumps(
                                {
                                    "type": "progress",
                                    "completed": ev.completed,
                                    "total": ev.total,
                                }
                            )
                            yield f"data: {payload}\n\n"
                            continue
                        events.append(ev)
                        payload = json.dumps(event_to_dict(ev))
                        yield f"data: {payload}\n\n"
                except Exception as e:  # noqa: BLE001 — surfaced to the client
                    yield _sse({"type": "error", "detail": str(e)})
                    return
                # All notes streamed — build the MIDI file in memory (reusing the
                # exact `muscriptor transcribe` logic) and send it as a final event
                # with the bytes base64-encoded.
                if cancel.is_set():
                    return
                if remove_vocals:
                    yield _sse({"type": "stage", "stage": "midi"})
                # Detect tempo/meter only now: it costs a few seconds of CPU and
                # nothing before this point needs it, so the notes stream first.
                # `detect_tempo=true` is the caller asking to be told when there
                # is no usable tempo: without this catch the exception would
                # escape the generator, and the client would see a 200 stream
                # that just ends — no `error`, no `transcription_complete`.
                try:
                    grid = model.detect_beat_grid_for(
                        (transcription_wav, transcription_sr), detect_tempo
                    )
                except BeatDetectionError as e:
                    yield _sse({"type": "error", "detail": str(e)})
                    return
                # Measure the onset lag up here rather than leaving it to the MIDI
                # writing, since the UI has to be told the very same number to move
                # the notes it already drew.
                if grid:
                    grid = grid.with_onset_delay(
                        [
                            ev.start_time
                            for ev in events
                            if isinstance(ev, NoteStartEvent)
                        ]
                    )
                midi_bytes = model.events_to_midi_bytes(iter(events), beat_grid=grid)
                midi_b64 = base64.b64encode(midi_bytes).decode("ascii")
                # A second copy with the notes snapped to the beat grid. Useful for
                # writing sheet music where we want "idealized" timing
                quantized_midi = (
                    model.events_to_midi_bytes(
                        iter(events), beat_grid=grid, quantize=True
                    )
                    if grid is not None and grid.beat_subdivision is not None
                    else None
                )
                # The grid rides along so the UI can draw bar lines instead of a
                # fixed seconds grid; null when no tempo was detected.
                payload = json.dumps(
                    {
                        "type": "transcription_complete",
                        "data": midi_b64,
                        "quantized_midi": base64.b64encode(quantized_midi).decode(
                            "ascii"
                        )
                        if quantized_midi
                        else None,
                        # Only the fields the UI draws with; `grid.beats` is an
                        # ndarray and not JSON-serializable anyway.
                        "beat_grid": {
                            "bpm": grid.bpm,
                            "beats_per_bar": grid.beats_per_bar,
                            "first_downbeat": grid.first_downbeat,
                            # Seconds the streamed note times sit late against
                            # the beats; the MIDI already has it taken out, the
                            # UI has to subtract it from the notes it drew.
                            "onset_delay": grid.onset_delay,
                        }
                        if grid
                        else None,
                    }
                )
                if remove_vocals:
                    # Additive keys, sent only on the vocal-removal path so the
                    # plain pipeline's final event stays byte-identical. The
                    # UI labels the result "transcribed from instrumental" and
                    # offers the stems as downloads via these URLs.
                    payload_dict = json.loads(payload)
                    payload_dict["stems"] = stems_payload
                    payload_dict["from_instrumental"] = True
                    payload = json.dumps(payload_dict)
                yield f"data: {payload}\n\n"
            except Exception as e:  # noqa: BLE001 — surfaced to the client
                # Any failure after the stream opened (stem decode, beat-grid
                # detection, MIDI assembly) must end with a terminal `error`
                # event — otherwise the stream just stops and the client marks
                # the run done with no MIDI and no explanation.
                yield _sse({"type": "error", "detail": str(e)})
            finally:
                release_lock()

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            background=BackgroundTask(release_lock),
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/transcribe/midi")
    async def transcribe_midi(
        file: Annotated[UploadFile, File()],
        instruments: Annotated[list[str], Form(default_factory=list)],
        # "true" fails loudly on tempo detection errors, "false" doesn't even try
        detect_tempo: Annotated[TempoDetection, Form()] = "best-effort",
        # Opt-in preprocessing, same semantics as /transcribe — but this
        # endpoint returns only the MIDI, so the stems are not kept around.
        remove_vocals: Annotated[bool, Form()] = False,
        x_client_id: Annotated[str | None, Header()] = None,
    ) -> Response:
        """Transcribe an audio file and return the .mid file directly.

        Unlike /transcribe, this blocks until transcription finishes and
        returns the raw MIDI bytes (no SSE, no base64) with a
        Content-Disposition header, so a plain HTTP client can save the
        response straight to disk.
        """
        _reject_oversized_upload(file)
        _reject_long_audio(file)

        unknown = [n for n in instruments if n not in MT3_FULL_PLUS_GROUP_NAMES]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"unknown instrument name(s): {', '.join(unknown)}",
            )

        # Same mutual exclusion as /transcribe, via the shared helper. This run
        # is not cancellable (it doesn't stream, so there's nothing to stop
        # mid-flight); cancellable=False records that, so nothing tries to
        # preempt a blocking MIDI render. A non-browser API caller sends no
        # client id and so neither preempts nor is preempted — it just waits for
        # the lock like any other contender.
        _cancel, release_lock = await acquire_transcribe_lock(
            x_client_id, cancellable=False
        )
        # The /transcribe/midi response carries only the MIDI bytes — the
        # stems are never downloadable through this endpoint, so the run
        # directory is removed as soon as the request is over (see the
        # finally below) instead of waiting for the orphan sweep.
        run_dir: Path | None = None
        try:
            # Read and decode only under the lock (see /transcribe): the decoded
            # audio is hundreds of MB and must not be built in parallel.
            data = await file.read()
            wav, sr = await asyncio.to_thread(_decode_audio, data, file.filename)
            duration_s = wav.shape[-1] / sr
            if duration_s > _MAX_TRANSCRIBE_MIDI_DURATION_S:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"audio file is {duration_s / 60:.1f} minutes long; "
                        f"the limit is {_MAX_TRANSCRIBE_MIDI_DURATION_S // 60:.0f} minutes"
                    ),
                )
            transcription_wav = wav
            transcription_sr = sr
            if remove_vocals:
                # Same mutual exclusion as the model itself (see /transcribe):
                # separation runs under the lock, so the GPU never does both.
                # Both calls block (separation writes the whole upload to disk
                # and runs for minutes), so they run off the event loop exactly
                # as the /transcribe generator path does.
                try:
                    result, run_dir = await asyncio.to_thread(
                        _remove_vocals, data, file.filename
                    )
                except PreprocessError as e:
                    raise HTTPException(status_code=422, detail=str(e)) from e
                transcription_wav, transcription_sr = await asyncio.to_thread(
                    _read_non_wav_file, result.audio_for_transcription
                )
            # Reload the model first if it was unloaded while idle. Loading the
            # weights blocks, so keep the event loop (health, model, static) up.
            try:
                model = await asyncio.to_thread(ensure_model)
            except RuntimeError as e:
                raise HTTPException(status_code=503, detail=str(e)) from e
            midi_bytes, _ = await asyncio.to_thread(
                model.transcribe_and_postprocess,
                (transcription_wav, transcription_sr),
                instruments=instruments or None,
                detect_tempo=detect_tempo,
            )
        except BeatDetectionError as e:
            # Only reachable with detect_tempo=true, where the caller wants an error
            # if tempo detection fails.
            raise HTTPException(status_code=422, detail=str(e)) from e
        finally:
            if run_dir is not None:
                shutil.rmtree(run_dir, ignore_errors=True)
            release_lock()

        return Response(
            content=midi_bytes,
            media_type="audio/midi",
            headers={"Content-Disposition": 'attachment; filename="result.mid"'},
        )

    @app.post("/auralize")
    async def auralize(
        midi: Annotated[UploadFile, File()],
        audio: Annotated[UploadFile | None, File()] = None,
        mode: Annotated[str, Form()] = "mix",
    ):
        """Render a transcription as WAV.

        mode="mix": stereo, original audio (L) + FluidSynth synthesis (R);
        requires the `audio` upload. mode="synth": mono, just the synthesis.
        """
        if mode not in ("mix", "synth"):
            raise HTTPException(status_code=400, detail=f"unknown mode: {mode!r}")
        if mode == "mix" and audio is None:
            raise HTTPException(
                status_code=400, detail="mode='mix' requires an audio file"
            )

        _reject_oversized_upload(midi, _MIDI_MAX_BYTES)
        if audio is not None:
            _reject_oversized_upload(audio)
            _reject_long_audio(audio)
        midi_data = await midi.read()
        # Cap the synthesis up front: a MIDI whose ticks stretch to hours would
        # otherwise hang fluidsynth for the same time and fill the disk/RAM.
        midi_duration_s = await asyncio.to_thread(_midi_duration_s, midi_data)
        if (
            midi_duration_s is not None
            and midi_duration_s > _MAX_AURALIZE_MIDI_DURATION_S
        ):
            raise HTTPException(
                status_code=413,
                detail=(
                    f"MIDI is {midi_duration_s / 60:.1f} minutes long; "
                    f"the limit is {_MAX_AURALIZE_MIDI_DURATION_S // 60:.0f} minutes"
                ),
            )
        try:
            wav_bytes = await asyncio.to_thread(
                _serialized,
                auralize_lock,
                _render_auralize,
                mode,
                midi_data,
                audio,
                busy_detail="server busy: another auralization is in progress",
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        return Response(content=wav_bytes, media_type="audio/wav", headers=_NO_GZIP)

    @app.post("/arrange/guitar")
    async def arrange_guitar(
        file: Annotated[UploadFile, File()],
        track: Annotated[int | None, Form()] = None,
        channel: Annotated[int | None, Form()] = None,
        tuning: Annotated[str, Form()] = "standard",
        max_fret: Annotated[int, Form()] = 24,
        phrase_gap_beats: Annotated[float, Form()] = 1.0,
        melody: Annotated[str, Form()] = "off",
        overrides: Annotated[str | None, Form()] = None,
        normalize: Annotated[bool, Form()] = True,
        chord_overflow: Annotated[Literal["reduce", "error"], Form()] = "reduce",
        chords: Annotated[bool, Form()] = True,
    ) -> dict:
        """Arrange one MIDI track for guitar (string/fret per note).

        A thin wrapper around the pure `muscriptor.guitar_arrangement`
        pipeline: no transcription model, no MuseScore, no audio. Returns the
        versioned arrangement JSON. Structured errors use
        `{"code", "message", "details"}`: 400 for an unreadable MIDI file or
        malformed/contradictory input, 422 for an ambiguous track choice,
        polyphonic input or an unplayable note. `melody` opts into a
        deterministic monophonic reduction (`top` = keep the highest note of
        every simultaneous onset group, `bottom` = the lowest) so real-world
        polyphonic tracks can still be arranged as one melodic line.
        `normalize` (default on) fits the part to the standard tuning first
        (transposition and octave-duplicate removal, reported in the
        document); `chord_overflow` decides what happens to onsets that
        cannot be played in full (more notes than strings, or no mutually
        compatible fingering): `reduce` (default) keeps the best playable
        subset and reports it in `chord_reductions`, `error` returns the
        structured failure.
        """
        from muscriptor.guitar_arrangement import (
            GuitarArrangementError,
            InvalidMaxFretError,
            InvalidMelodyPolicyError,
            InvalidOverridesError,
            MidiParseError,
            TooManyNotesError,
            TooLongArrangementError,
            arrange,
        )

        _reject_oversized_upload(file, _MIDI_MAX_BYTES)
        midi_bytes = await file.read()
        try:
            return await asyncio.to_thread(
                _serialized,
                arrange_lock,
                arrange,
                midi_bytes,
                filename=file.filename or "input.mid",
                track=track,
                channel=channel,
                tuning_name=tuning,
                max_fret=max_fret,
                phrase_gap_beats=phrase_gap_beats,
                melody_policy=melody,
                overrides_text=overrides,
                normalize=normalize,
                chord_overflow=chord_overflow,
                detect_chords=chords,
                busy_detail="server busy: another arrangement is in progress",
            )
        except GuitarArrangementError as e:
            status = (
                400
                if isinstance(
                    e,
                    (
                        MidiParseError,
                        InvalidOverridesError,
                        InvalidMelodyPolicyError,
                        InvalidMaxFretError,
                        TooManyNotesError,
                        TooLongArrangementError,
                    ),
                )
                else 422
            )
            raise HTTPException(
                status_code=status,
                detail={"code": e.code, "message": str(e), "details": e.details},
            ) from e

    async def _arrangement_upload(document: UploadFile, error_status: int) -> dict:
        """Parse and shape-check an uploaded arrangement.json (shared by mirrors).

        The shape checks are the minimum every converter assumes: an object
        document with object `source`/`instrument` blocks and list-typed meter
        maps. A document failing one used to surface as a 500 (AttributeError /
        TypeError) in one of the four mirrors instead of a clean 400.
        """
        import json

        _reject_oversized_upload(document)
        if document.size is not None and document.size > _ARRANGEMENT_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"arrangement document is {document.size / (1024 * 1024):.0f} MB; "
                    f"the limit is {_ARRANGEMENT_MAX_BYTES // (1024 * 1024)} MB"
                ),
            )
        raw = await document.read()

        def invalid(message: str) -> HTTPException:
            return HTTPException(
                status_code=error_status,
                detail={
                    "code": "invalid_arrangement",
                    "message": message,
                    "details": {},
                },
            )

        try:
            # Parsing a big document blocks; keep the event loop serving.
            parsed = await asyncio.to_thread(json.loads, raw)
        except (ValueError, RecursionError) as e:
            # JSONDecodeError is a ValueError; deeply nested JSON is a
            # RecursionError. Both are the client's fault, not a server 500.
            raise invalid(f"arrangement document is not valid JSON: {e}") from e
        if not isinstance(parsed, dict):
            raise invalid("arrangement document must be a JSON object")
        if parsed.get("schema_version") not in (2, 3):
            # Let the converters report the unsupported version with their own
            # error code instead of masking it as a shape error.
            return parsed
        source = parsed.get("source")
        if not isinstance(source, dict):
            raise invalid("arrangement 'source' must be an object")
        if not isinstance(parsed.get("instrument"), dict):
            raise invalid("arrangement 'instrument' must be an object")
        for key in ("tempo_events", "time_signature_events"):
            if not isinstance(source.get(key, []), list):
                raise invalid(f"arrangement 'source.{key}' must be a list")
        return parsed

    @app.post("/arrange/guitar/midi")
    async def arrangement_to_midi(
        document: Annotated[UploadFile, File()],
    ) -> Response:
        """Convert an arrangement.json back into a MIDI file.

        Pitch, onset, offset and velocity are copied verbatim from the
        document — the result is exactly what the arranger did to the source
        track (minus melody-reduction drops). No tempo is written: the
        document has none.
        """
        from muscriptor.guitar_arrangement import (
            GuitarArrangementError,
            arrangement_json_to_midi,
        )

        document_dict = await _arrangement_upload(document, 400)
        try:
            midi_bytes = await asyncio.to_thread(
                arrangement_json_to_midi, document_dict
            )
        except GuitarArrangementError as e:
            raise HTTPException(
                status_code=400,
                detail={"code": e.code, "message": str(e), "details": e.details},
            ) from e
        stem = (document.filename or "arrangement.json").rsplit(".", 1)[0]
        return Response(
            content=midi_bytes,
            media_type="audio/midi",
            headers={"Content-Disposition": _attachment_header(stem, ".mid")},
        )

    @app.post("/arrange/guitar/tab")
    async def arrangement_to_tab(
        document: Annotated[UploadFile, File()],
    ) -> Response:
        """Render an arrangement.json as ASCII tabulature (text/plain)."""
        from muscriptor.guitar_arrangement import (
            GuitarArrangementError,
            arrangement_json_to_tab,
        )

        document_dict = await _arrangement_upload(document, 400)
        try:
            tab_text = await asyncio.to_thread(arrangement_json_to_tab, document_dict)
        except GuitarArrangementError as e:
            raise HTTPException(
                status_code=400,
                detail={"code": e.code, "message": str(e), "details": e.details},
            ) from e
        return Response(content=tab_text, media_type="text/plain; charset=utf-8")

    @app.post("/arrange/guitar/musicxml")
    async def arrangement_to_musicxml(
        document: Annotated[UploadFile, File()],
        chords: Annotated[bool, Form()] = True,
        fingerings: Annotated[bool, Form()] = False,
    ) -> Response:
        """Convert an arrangement.json into fingering-preserving MusicXML.

        Every note carries `<technical><string>/<fret></technical>`, so an
        engraver renders the exact tab the arranger (or the user's locks)
        chose — unlike MIDI, which never stores string/fret. Detected jazz
        chord symbols are written as `<harmony>` above the staff
        (`chords=true`, default); left-hand finger numbers are omitted
        unless `fingerings=true`.
        """
        from muscriptor.guitar_arrangement import (
            GuitarArrangementError,
            arrangement_json_to_musicxml,
        )

        document_dict = await _arrangement_upload(document, 400)
        try:
            xml_bytes = await asyncio.to_thread(
                arrangement_json_to_musicxml,
                document_dict,
                chords=chords,
                fingerings=fingerings,
            )
        except GuitarArrangementError as e:
            raise HTTPException(
                status_code=400,
                detail={"code": e.code, "message": str(e), "details": e.details},
            ) from e
        stem = (document.filename or "arrangement.json").rsplit(".", 1)[0]
        return Response(
            content=xml_bytes,
            media_type="application/vnd.recordare.musicxml+xml",
            headers={"Content-Disposition": _attachment_header(stem, ".musicxml")},
        )

    @app.post("/arrange/guitar/pdf")
    async def arrangement_to_pdf(
        document: Annotated[UploadFile, File()],
        chords: Annotated[bool, Form()] = True,
        fingerings: Annotated[bool, Form()] = False,
    ) -> Response:
        """Engrave an arrangement.json into a score+tab PDF that provably
        keeps the chosen string/fret.

        Pipeline: arrangement → MusicXML (with `<technical>` string/fret) →
        MuseScore 4 → PDF. The MusicXML round trip is covered by a test that
        verifies MuseScore preserves the technical positions, so the PDF
        matches the arrangement JSON. Jazz chord symbols from the document's
        `chords` block are rendered above the staff by default
        (`chords=false` to omit); left-hand finger numbers stay out unless
        `fingerings=true`. Returns a zip with the PDF and the intermediate
        MusicXML. 503 when MuseScore is not installed.
        """
        from muscriptor.guitar_arrangement import (
            GuitarArrangementError,
            arrangement_json_to_musicxml,
        )
        from muscriptor.utils.sheets import (
            MuseScoreError,
            MuseScoreNotFoundError,
            find_musescore,
        )

        document_dict = await _arrangement_upload(document, 400)
        try:
            xml_bytes = await asyncio.to_thread(
                arrangement_json_to_musicxml,
                document_dict,
                chords=chords,
                fingerings=fingerings,
            )
        except GuitarArrangementError as e:
            raise HTTPException(
                status_code=400,
                detail={"code": e.code, "message": str(e), "details": e.details},
            ) from e

        # The upload filename is client-controlled and lands in file paths and
        # the Content-Disposition header, so reduce it to a bare name first —
        # an absolute or ../-laced name must not escape the scratch directory.
        stem = Path(document.filename or "arrangement.json").name.rsplit(".", 1)[0]
        try:
            binary = await asyncio.to_thread(find_musescore)
        except MuseScoreNotFoundError as e:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "musescore_unavailable",
                    "message": str(e),
                    "details": {},
                },
            ) from e
        try:
            zip_bytes = await asyncio.to_thread(
                _serialized,
                musescore_lock,
                _engrave_arrangement_pdf,
                binary,
                xml_bytes,
                stem,
            )
        except (MuseScoreError, OSError) as e:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "fingering_export_failed",
                    "message": f"could not engrave the arrangement: {e}",
                    "details": {},
                },
            ) from e
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                **_NO_GZIP,
                "Content-Disposition": _attachment_header(stem, "_score.zip"),
            },
        )

    @app.post("/sheets")
    async def sheets(
        midi: Annotated[UploadFile, File()],
        quantized: Annotated[bool, Form()] = False,
    ) -> Response:
        """Engrave a MIDI file as sheet music, returned as one zip.

        The whole set is rendered in one go — MuseScore is slow enough that a
        round trip per file would be worse — so the caller gets every PDF, the
        MusicXML and the MIDI in a single uncompressed archive and picks from it
        locally. Requires MuseScore 4+ on the server (503 without it).

        `quantized` says the upload is already snapped to a beat grid — the
        `quantized_midi` from /transcribe — which is what the notation should be
        engraved from. Without it the engraving keeps the timing jitter, so this
        does not quantize anything itself.
        """
        _reject_oversized_upload(midi, _MIDI_MAX_BYTES)
        midi_bytes = await midi.read()

        try:
            zip_bytes = await asyncio.to_thread(
                _serialized, musescore_lock, engrave_to_zip, midi_bytes, quantized
            )
        except MuseScoreNotFoundError as e:
            # A deployment problem, not a bad request: the same 503 the UI
            # already knows how to report, with the install hint as its detail.
            raise HTTPException(status_code=503, detail=str(e)) from e
        except MuseScoreError as e:
            # MuseScore ran but wrote nothing usable — most often because the
            # upload wasn't a MIDI file it could import.
            raise HTTPException(status_code=500, detail=str(e)) from e

        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                **_NO_GZIP,
                "Content-Disposition": f'attachment; filename="{SHEETS_ZIP_NAME}"',
            },
        )

    @app.get("/stems/{run_id}/{stem}")
    async def get_stem(run_id: str, stem: str) -> FileResponse:
        """Serve a preprocessing stem (vocals/instrumental) for download.

        Stems exist only for runs that used vocal removal, and only until the
        StemStore reaps their run directory (TTL + cap on stored runs).
        """
        path = stems.get(run_id, stem)
        if path is None or not path.is_file():
            raise HTTPException(
                status_code=404,
                detail="stem not found (expired, or vocal removal was not used)",
            )
        return FileResponse(
            path,
            media_type="audio/wav",
            headers={
                **_NO_GZIP,
                "Content-Disposition": f'attachment; filename="{stem}.wav"',
            },
        )

    @app.get("/model")
    async def get_model() -> dict:
        """Current model size keyword and swap status."""
        return {
            "model": model_state["size"],
            "status": model_state["status"],
            "error": model_state["error"],
        }

    @app.post("/model")
    async def switch_model(
        size: Annotated[str, Form()],
        x_model_token: Annotated[str | None, Header()] = None,
    ) -> dict:
        """Load another model size and make it the live one.

        Runs in a background thread (weights download + load take a while);
        while it runs, transcriptions and further swaps are refused with 409.
        Only a size keyword (small/medium/large) can be selected here; that
        works whatever the server was started with, including a local file —
        the loader maps the keyword to the published checkpoint.
        """
        # This endpoint mutates the shared GPU state, so a public deployment
        # must gate it: when MODEL_ADMIN_TOKEN is set, the X-Model-Token header
        # has to match. Unset (the localhost default) leaves it open.
        admin_token = os.environ.get("MODEL_ADMIN_TOKEN")
        if admin_token and x_model_token != admin_token:
            raise HTTPException(
                status_code=403,
                detail="POST /model requires the X-Model-Token header on this server",
            )
        if model_loader is None:
            raise HTTPException(
                status_code=501,
                detail="model switching is not available on this server",
            )
        size = size.strip().lower()
        if size == "unload":
            return unload_model()
        if size not in ("small", "medium", "large"):
            raise HTTPException(
                status_code=400,
                detail=f"unknown model size: {size!r} (small, medium or large)",
            )
        if model_state["status"] == "loading":
            raise HTTPException(
                status_code=409, detail="a model is already being loaded"
            )
        if size == model_state["size"] and model_state["status"] == "ready":
            return {"model": size, "status": "ready"}

        # Mark loading *before* checking the transcription lock: a transcription
        # starting in the window between the two would otherwise grab the lock
        # and the outgoing model (see acquire_transcribe_lock / ensure_model)
        # while this swap loads a second set of weights into VRAM.
        previous_status = model_state["status"]
        previous_error = model_state["error"]
        model_state["status"] = "loading"
        model_state["error"] = None
        if transcribe_lock.locked():
            model_state["status"] = previous_status
            model_state["error"] = previous_error
            raise HTTPException(
                status_code=409,
                detail="a transcription is in progress; try again when it finishes",
            )

        def load() -> None:
            try:
                new_model = model_loader(size)
                old = model_state["model"]
                model_state["model"] = new_model
                model_state["size"] = size
                model_state["status"] = "ready"
                model_state["error"] = None
                # A fresh load counts as "use": the idle unloader must not
                # drop the model right after it was asked for.
                last_model_use[0] = time.monotonic()
                # Free the old model's GPU memory promptly: dropping the last
                # reference doesn't return the cached CUDA blocks to the driver
                # unless the allocator is told to.
                del old
                gc.collect()
                try:
                    import torch

                    torch.cuda.empty_cache()
                except Exception:
                    pass
            except Exception as e:  # noqa: BLE001 — surfaced to the client
                model_state["status"] = "error"
                model_state["error"] = str(e)

        threading.Thread(target=load, daemon=True).start()
        return {"model": model_state["size"], "status": "loading"}

    if web_dir is not None:
        web_path = Path(web_dir)
        if web_path.is_dir():
            app.mount("/", StaticFiles(directory=web_path, html=True), name="web")

    return app

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
from typing import Annotated, Callable

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from muscriptor.accelerator import (
    current_accelerator,
    is_available as accelerator_available,
)
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

SHEETS_ZIP_NAME = "sheets.zip"


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

    def _stems_payload(run_id: str) -> dict:
        """Download URLs for a run's registered stems."""
        return {
            "vocals": f"/stems/{run_id}/vocals",
            "instrumental": f"/stems/{run_id}/instrumental",
        }

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
                        and not transcribe_lock.locked()
                        and model_state["status"] == "ready"
                        and model_state["model"] is not None
                    ):
                        logger = logging.getLogger("muscriptor.server")
                        logger.info(
                            "server idle for %.0fs — unloading the model to free VRAM",
                            idle_unload_s,
                        )
                        _drop_model()
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
        return FileResponse(path, media_type="application/octet-stream")

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
        data = await file.read()
        # PCM WAV goes through the stdlib reader (keeps WAV decoding byte-for-byte
        # identical to the CLI); anything that isn't a readable WAV (mp3, flac,
        # ogg, m4a, …) falls back to soundfile/libsndfile. A genuinely
        # undecodable upload (corrupt/truncated file, or a format libsndfile
        # can't read) is the client's fault, so report it as a 400 rather than
        # letting it surface as a 500.
        try:
            wav, sr = _read_wav_file(io.BytesIO(data))
        except (wave.Error, EOFError):
            try:
                wav, sr = _read_non_wav_file(io.BytesIO(data))
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"could not decode audio file '{file.filename}': {e}",
                ) from e

        unknown = [n for n in instruments if n not in MT3_FULL_PLUS_GROUP_NAMES]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"unknown instrument name(s): {', '.join(unknown)}",
            )

        # Acquire the single-transcription lock, preempting only a resubmit from
        # this same client (see acquire_transcribe_lock). `release_lock` runs
        # from whichever cleanup path fires first: the generator's finally
        # (normal completion, errors, mid-stream disconnects) or the
        # StreamingResponse background task (client disconnects before the
        # generator is ever iterated, so its finally would never run) — either
        # way the lock is released exactly once and never leaked.
        cancel, release_lock = await acquire_transcribe_lock(
            x_client_id, cancellable=True
        )

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
                    transcription_wav, _ = _read_non_wav_file(
                        result.audio_for_transcription
                    )
                    run_id = run_dir_.name.removeprefix("muscriptor-stems-")
                    stems.register(
                        run_id,
                        run_dir_,
                        {
                            **({"vocals": result.vocals_path} if result.vocals_path else {}),
                            "instrumental": result.instrumental_path,
                        },
                    )
                    stems_payload = _stems_payload(run_id)
                    yield _sse({"type": "stage", "stage": "transcription"})
                # batch_size=1 so each chunk's notes stream out as soon as it is
                # generated, instead of waiting for a whole batch of chunks.
                # no_eos_is_ok=True so one runaway chunk that never emits EOS only
                # warns (and keeps its notes) instead of aborting the whole stream.
                for ev in model.transcribe(
                    (transcription_wav, sr),
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
                        # Coarse chunk-completion anchor — forward it but keep it
                        # out of the note list the MIDI file is built from.
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
                # All notes streamed — build the MIDI file in memory (reusing the
                # exact `muscriptor transcribe` logic) and send it as a final event
                # with the bytes base64-encoded.
                if cancel.is_set():
                    return
                if remove_vocals:
                    yield _sse({"type": "stage", "stage": "midi"})
                # Detect tempo/meter only now: it costs a few seconds of CPU and
                # nothing before this point needs it, so the notes stream first.
                grid = model.detect_beat_grid_for(
                    (transcription_wav, sr), detect_tempo
                )
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
        data = await file.read()
        try:
            wav, sr = _read_wav_file(io.BytesIO(data))
        except (wave.Error, EOFError):
            try:
                wav, sr = _read_non_wav_file(io.BytesIO(data))
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"could not decode audio file '{file.filename}': {e}",
                ) from e

        duration_s = wav.shape[-1] / sr
        if duration_s > _MAX_TRANSCRIBE_MIDI_DURATION_S:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"audio file is {duration_s / 60:.1f} minutes long; "
                    f"the limit is {_MAX_TRANSCRIBE_MIDI_DURATION_S // 60:.0f} minutes"
                ),
            )

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
            transcription_wav = wav
            if remove_vocals:
                # Same mutual exclusion as the model itself (see /transcribe):
                # separation runs under the lock, so the GPU never does both.
                try:
                    result, run_dir = _remove_vocals(data, file.filename)
                except PreprocessError as e:
                    raise HTTPException(status_code=422, detail=str(e)) from e
                transcription_wav, _ = _read_non_wav_file(
                    result.audio_for_transcription
                )
            # Reload the model first if it was unloaded while idle.
            try:
                model = ensure_model()
            except RuntimeError as e:
                raise HTTPException(status_code=503, detail=str(e)) from e
            midi_bytes, _ = await asyncio.to_thread(
                model.transcribe_and_postprocess,
                (transcription_wav, sr),
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
        from muscriptor.utils.auralization import auralize as do_auralize
        from muscriptor.utils.auralization import synthesize

        if mode not in ("mix", "synth"):
            raise HTTPException(status_code=400, detail=f"unknown mode: {mode!r}")
        if mode == "mix" and audio is None:
            raise HTTPException(
                status_code=400, detail="mode='mix' requires an audio file"
            )

        midi_data = await midi.read()
        tmp_paths: list[str] = []

        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp_midi:
            tmp_midi.write(midi_data)
            midi_tmp = tmp_midi.name
            tmp_paths.append(midi_tmp)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_out:
            out_tmp = tmp_out.name
            tmp_paths.append(out_tmp)

        try:
            if mode == "synth":
                synthesize(midi_path=midi_tmp, output_path=out_tmp)
            else:
                audio_data = await audio.read()
                suffix = Path(audio.filename or "audio.wav").suffix.lower() or ".wav"
                with tempfile.NamedTemporaryFile(
                    suffix=suffix, delete=False
                ) as tmp_audio:
                    tmp_audio.write(audio_data)
                    tmp_paths.append(tmp_audio.name)
                do_auralize(
                    midi_path=midi_tmp,
                    original_audio_path=tmp_audio.name,
                    output_path=out_tmp,
                )
            with open(out_tmp, "rb") as f:
                wav_bytes = f.read()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            for p in tmp_paths:
                if os.path.exists(p):
                    os.unlink(p)

        return Response(content=wav_bytes, media_type="audio/wav")

    @app.post("/arrange/guitar")
    async def arrange_guitar(
        file: Annotated[UploadFile, File()],
        track: Annotated[int | None, Form()] = None,
        channel: Annotated[int | None, Form()] = None,
        tuning: Annotated[str, Form()] = "standard",
        max_fret: Annotated[int, Form()] = 24,
        phrase_gap_beats: Annotated[float, Form()] = 1.0,
        overrides: Annotated[str | None, Form()] = None,
    ) -> dict:
        """Arrange one monophonic MIDI track for guitar (string/fret per note).

        A thin wrapper around the pure `muscriptor.guitar_arrangement`
        pipeline: no transcription model, no MuseScore, no audio. Returns the
        versioned arrangement JSON. Structured errors use
        `{"code", "message", "details"}`: 400 for an unreadable MIDI file or
        malformed/contradictory overrides, 422 for an ambiguous track choice,
        polyphonic input or an unplayable note.
        """
        from muscriptor.guitar_arrangement import (
            GuitarArrangementError,
            MidiParseError,
            InvalidOverridesError,
            arrange,
        )

        midi_bytes = await file.read()
        try:
            return arrange(
                midi_bytes,
                filename=file.filename or "input.mid",
                track=track,
                channel=channel,
                tuning_name=tuning,
                max_fret=max_fret,
                phrase_gap_beats=phrase_gap_beats,
                overrides_text=overrides,
            )
        except GuitarArrangementError as e:
            status = 400 if isinstance(e, (MidiParseError, InvalidOverridesError)) else 422
            raise HTTPException(
                status_code=status,
                detail={"code": e.code, "message": str(e), "details": e.details},
            ) from e

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
        midi_bytes = await midi.read()

        try:
            zip_bytes = await asyncio.to_thread(engrave_to_zip, midi_bytes, quantized)
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
                "Content-Disposition": f'attachment; filename="{SHEETS_ZIP_NAME}"'
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
                "Content-Disposition": f'attachment; filename="{stem}.wav"'
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
    async def switch_model(size: Annotated[str, Form()]) -> dict:
        """Load another model size and make it the live one.

        Runs in a background thread (weights download + load take a while);
        while it runs, transcriptions and further swaps are refused with 409.
        Requires the server to have been started with a size-keyword model —
        a server running a local file path can't switch to published sizes.
        """
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
        if transcribe_lock.locked():
            raise HTTPException(
                status_code=409,
                detail="a transcription is in progress; try again when it finishes",
            )
        if size == model_state["size"] and model_state["status"] == "ready":
            return {"model": size, "status": "ready"}

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

        model_state["status"] = "loading"
        model_state["error"] = None
        threading.Thread(target=load, daemon=True).start()
        return {"model": model_state["size"], "status": "loading"}

    if web_dir is not None:
        web_path = Path(web_dir)
        if web_path.is_dir():
            app.mount("/", StaticFiles(directory=web_path, html=True), name="web")

    return app

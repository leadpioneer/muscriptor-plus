"""CLI for muscriptor: audio → MIDI transcription."""

import dataclasses
import json
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

import typer

from muscriptor.accelerator import current_accelerator
from muscriptor.events import NoteEndEvent, NoteStartEvent, ProgressEvent
from muscriptor.preprocessing import PreprocessError
from muscriptor.tokenizer.mt3 import (
    MT3_FULL_PLUS_GROUP_NAMES,
    resolve_instrument_names,
)
from muscriptor.transcription_model import TranscriptionModel
from muscriptor.utils.beats import BeatDetectionError, TempoDetection
from muscriptor.utils.download import ModelDownloadError
from muscriptor.utils.sheets import (
    MuseScoreError,
    MuseScoreNotFoundError,
    find_musescore,
    prepare_output_dir,
    write_sheets,
)

app = typer.Typer(add_completion=False, help="muscriptor — audio-to-MIDI transcription")


def _load_model(
    model_path: str | None, device: str | None, dtype: str | None = None
) -> TranscriptionModel:
    """load_model with CLI-friendly failure: known download problems (missing
    HuggingFace authentication, …) print a plain message instead of a traceback."""
    try:
        return TranscriptionModel.load_model(
            weights_path=model_path, device=device, dtype=dtype
        )
    except ModelDownloadError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


class OutputFormat(str, Enum):
    midi = "midi"
    json = "json"
    jsonl = "jsonl"
    sheets = "sheets"


def _transcribe(model, kwargs: dict, detect_tempo: str, quantize: bool = False):
    """transcribe_and_postprocess, with the CLI's --detect-tempo spelling and errors."""
    try:
        mode: TempoDetection = {
            "true": True,
            "false": False,
            "best-effort": "best-effort",
        }[detect_tempo]
        return model.transcribe_and_postprocess(
            **kwargs, detect_tempo=mode, quantize=quantize
        )
    except BeatDetectionError as e:
        typer.echo(f"Error: {e}", err=True)
        typer.echo("Pass --detect-tempo best-effort or false to continue.", err=True)
        raise typer.Exit(1)


def _event_to_dict(ev: NoteStartEvent | NoteEndEvent) -> dict:
    if isinstance(ev, NoteStartEvent):
        return {"type": "start", **dataclasses.asdict(ev)}
    return {
        "type": "end",
        "end_time": ev.end_time,
        "start_event_index": ev.start_event_index,
    }


def _remove_vocals_cli(audio_file: Path) -> Path:
    """Strip the lead vocal, keeping both stems next to the input file.

    Returns the instrumental stem — the file the transcription should run on.
    Separation errors carry user-facing messages already, so they are printed
    as-is by the caller.
    """
    from muscriptor.preprocessing import VocalRemovalPreprocessor

    try:
        device = str(current_accelerator())
    except RuntimeError:
        device = "cpu"
    stems_dir = audio_file.parent / f"{audio_file.stem}_stems"
    typer.echo("Removing lead vocals…", err=True)
    result = VocalRemovalPreprocessor().process(audio_file, stems_dir, device)
    typer.echo(
        f"Stems saved to {stems_dir} — transcribing the instrumental.",
        err=True,
    )
    return result.audio_for_transcription


@app.command()
def transcribe(
    audio_file: Annotated[
        Path, typer.Argument(help="Input audio file (wav, mp3, flac, …)")
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Output file path. Use '-' to write to stdout (all progress / "
                "timing info is sent to stderr in that case). "
                "Default: <audio_file>.<ext> where ext matches --format. "
                "With --format sheets this is a directory instead: it must be "
                "empty or not exist yet, and is created if missing."
            ),
        ),
    ] = None,
    format: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            "-f",
            help=(
                "Output format: midi (default), json (single array of events), "
                "jsonl (one event per line, streamed as transcription "
                "progresses), or sheets (a directory of engraved PDFs plus "
                "MusicXML and MIDI; requires MuseScore to be installed)"
            ),
            case_sensitive=False,
        ),
    ] = OutputFormat.midi,
    notes: Annotated[
        bool, typer.Option("--notes", help="Print decoded events to stdout")
    ] = False,
    sampling: Annotated[
        bool,
        typer.Option(
            "--sampling", help="Use temperature sampling instead of greedy decoding"
        ),
    ] = False,
    temperature: Annotated[
        float,
        typer.Option(
            "--temperature", "-t", help="Sampling temperature (only with --sampling)"
        ),
    ] = 1.0,
    cfg_coef: Annotated[
        float, typer.Option("--cfg-coef", help="Classifier-free guidance coefficient")
    ] = 1.0,  # todo: make it dynamic
    model_path: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help=(
                "Model size ('small', 'medium', 'large'; default: medium), "
                "a local safetensors path, or an hf:// / http(s):// URL"
            ),
        ),
    ] = None,
    device: Annotated[
        str,
        typer.Option(
            "--device", "-d", help="Device: 'auto', 'cpu', 'cuda', 'cuda:0', 'mps', …"
        ),
    ] = "auto",
    dtype: Annotated[
        str | None,
        typer.Option(
            "--dtype",
            help=(
                "Transformer dtype: 'float32', 'float16' or 'bfloat16'. "
                "Default: float16 on MPS, float32 elsewhere."
            ),
        ),
    ] = None,
    batch_size: Annotated[
        int | None,
        typer.Option(
            "--batch-size",
            "-b",
            help=(
                "Chunks generated per forward pass (default: 1; with "
                "--no-prelude-forcing: 4 on GPU, 1 on CPU). Values > 1 lower "
                "quality at chunk boundaries and require --no-prelude-forcing."
            ),
        ),
    ] = None,
    strict_eos: Annotated[
        bool,
        typer.Option(
            "--strict-eos",
            help="Raise an error if a chunk fails to emit EOS within the generation budget (default: downgrade to a warning)",
        ),
    ] = False,
    beam_size: Annotated[
        int,
        typer.Option(
            "--beam-size",
            help="Beam search width (1 = greedy/sampling, ≥2 enables beam search)",
        ),
    ] = 1,
    prelude_forcing: Annotated[
        bool,
        typer.Option(
            "--prelude-forcing/--no-prelude-forcing",
            help=(
                "Teacher-force each chunk's tie prologue from the previous "
                "chunk's still-sounding notes, so chunks can't restart with "
                "the wrong instruments. Needs chunks generated in order, so "
                "it requires --batch-size 1 (the default)."
            ),
        ),
    ] = True,
    auralize: Annotated[
        Path | None,
        typer.Option(
            "--auralize",
            help=(
                "Write a stereo auralization (L=original audio, R=MIDI synthesis) to "
                "this path. Requires fluidsynth on PATH. Extension determines format: "
                ".wav (default) or .mp3. Only valid with --format midi."
            ),
        ),
    ] = None,
    soundfont: Annotated[
        Path | None,
        typer.Option(
            "--soundfont",
            help=(
                "Path to a .sf2 SoundFont for auralization. Defaults to "
                "MuseScore_General.sf2, downloaded once and cached locally."
            ),
        ),
    ] = None,
    instruments: Annotated[
        str | None,
        typer.Option(
            "--instruments",
            help=(
                "Comma-separated list of expected instrument group names. "
                "When given, every instrument not in the list is forbidden "
                "from being decoded at all. Case-insensitive; unambiguous "
                "abbreviations are accepted (e.g. 'timp,cello,dist'). Run "
                "'muscriptor list-instruments' to see all available names."
            ),
        ),
    ] = None,
    remove_vocals: Annotated[
        bool,
        typer.Option(
            "--remove-vocals",
            help=(
                "Strip the lead vocal (audio-separator, Mel-Band-RoFormer) and "
                "transcribe the instrumental instead — often improves "
                "instrument and tablature accuracy on vocal tracks. Both stems "
                "are saved to <audio>_stems/ next to the input file. Requires "
                "ffmpeg on PATH."
            ),
        ),
    ] = False,
    # typer can't take the bool | Literal["best-effort"] union the API uses, so
    # the CLI spells all three states as strings and converts below.
    detect_tempo: Annotated[
        Literal["true", "false", "best-effort"],
        typer.Option(
            help=(
                "Detect the tempo and time signature from the audio and write "
                "them into the MIDI. 'true' fails if no steady tempo is found, "
                "'best-effort' warns and uses a placeholder 120 BPM with no "
                "time signature, 'false' skips detection altogether."
            ),
        ),
    ] = "best-effort",
) -> None:
    """Transcribe an audio file to MIDI."""
    instrument_names: list[str] | None = None
    if instruments is not None:
        tokens = [n for n in instruments.split(",") if n.strip()]
        try:
            instrument_names = resolve_instrument_names(tokens)
        except ValueError as e:
            typer.echo(
                f"Error: {e}. "
                "Run 'muscriptor list-instruments' to see available names.",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo(f"Instruments: {', '.join(instrument_names)}", err=True)

    if not audio_file.exists():
        typer.echo(f"Error: file not found: {audio_file}", err=True)
        raise typer.Exit(1)

    if prelude_forcing and batch_size is not None and batch_size != 1:
        typer.echo(
            f"Error: --batch-size {batch_size} requires --no-prelude-forcing: "
            "batching disables prelude forcing, which lowers transcription "
            "quality at chunk boundaries.",
            err=True,
        )
        raise typer.Exit(1)

    is_stdout = output is not None and str(output) == "-"

    if output is None:
        if format == OutputFormat.sheets:
            output = audio_file.parent / f"{audio_file.stem}_sheets"
        else:
            suffix = {
                OutputFormat.midi: ".mid",
                OutputFormat.json: ".json",
                OutputFormat.jsonl: ".jsonl",
            }[format]
            output = audio_file.with_suffix(suffix)

    if format == OutputFormat.sheets:
        if is_stdout:
            typer.echo(
                "Error: --format sheets writes a directory, so it cannot write "
                "to stdout. Pass a directory path with -o.",
                err=True,
            )
            raise typer.Exit(1)
        # Both checked before the model loads: transcribing a song takes long
        # enough that discovering a missing MuseScore afterwards would sting.
        try:
            prepare_output_dir(output)
            find_musescore()
        except (ValueError, MuseScoreNotFoundError) as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    _device = None if device == "auto" else device

    # Vocal removal runs before the model loads: it fails fast and cheap, and
    # its output decides which audio gets transcribed.
    transcription_audio = audio_file
    if remove_vocals:
        try:
            transcription_audio = _remove_vocals_cli(audio_file)
        except PreprocessError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    # All chatty progress/timing info goes to stderr — stdout is reserved for
    # the actual output when `-o -` is used.
    typer.echo("Loading model…", err=True)
    model = _load_model(model_path, _device, dtype)

    typer.echo(f"Transcribing {transcription_audio} …", err=True)

    if auralize is not None and format != OutputFormat.midi:
        typer.echo("Error: --auralize requires --format midi", err=True)
        raise typer.Exit(1)

    kwargs = dict(
        audio=transcription_audio,
        use_sampling=sampling,
        temperature=temperature,
        cfg_coef=cfg_coef,
        instruments=instrument_names,
        batch_size=batch_size,
        no_eos_is_ok=not strict_eos,
        beam_size=beam_size,
        prelude_forcing=prelude_forcing,
    )

    if format == OutputFormat.sheets:
        # Quantize to get the "idealized" timing, otherwise we might get very weird
        # 1/64th rests etc.
        midi_bytes, grid = _transcribe(model, kwargs, detect_tempo, quantize=True)
        typer.echo(f"Engraving sheet music with MuseScore → {output} …", err=True)
        try:
            written = write_sheets(
                midi_bytes,
                output,
                quantized=grid is not None and grid.beat_subdivision is not None,
            )
        except MuseScoreError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
        for path in written:
            typer.echo(f"  {path.name}", err=True)
        typer.echo(f"Saved {len(written)} files to {output}", err=True)
    elif format == OutputFormat.midi:
        midi_bytes, _ = _transcribe(model, kwargs, detect_tempo)
        if is_stdout:
            sys.stdout.buffer.write(midi_bytes)
            sys.stdout.buffer.flush()
        else:
            output.write_bytes(midi_bytes)
            typer.echo(f"Saved MIDI to {output}", err=True)
        if notes:
            typer.echo(
                "Re-run with --format json to inspect the event stream.", err=True
            )
        if auralize is not None and not is_stdout:
            from muscriptor.utils.auralization import auralize as do_auralize

            typer.echo(f"Auralizing → {auralize} …", err=True)
            do_auralize(
                midi_path=output,
                original_audio_path=audio_file,
                output_path=auralize,
                soundfont_path=soundfont,
            )
            typer.echo(f"Saved auralization to {auralize}", err=True)
    elif format == OutputFormat.jsonl:
        # Stream one JSON object per line, flushing after each event so the
        # file (or stdout pipe) can be consumed live.
        if is_stdout:
            sink = sys.stdout
            close_after = False
        else:
            sink = output.open("w")
            close_after = True
        try:
            for e in model.transcribe(**kwargs):
                if isinstance(e, ProgressEvent):
                    continue
                sink.write(json.dumps(_event_to_dict(e)) + "\n")
                sink.flush()
                if notes:
                    typer.echo(str(e), err=True)
        finally:
            if close_after:
                sink.close()
        if not is_stdout:
            typer.echo(f"Saved JSONL to {output}", err=True)
    else:  # json
        events = [
            e for e in model.transcribe(**kwargs) if not isinstance(e, ProgressEvent)
        ]
        payload = json.dumps([_event_to_dict(e) for e in events], indent=2)
        if is_stdout:
            sys.stdout.write(payload + "\n")
            sys.stdout.flush()
        else:
            output.write_text(payload)
            typer.echo(f"Saved JSON to {output}", err=True)
        if notes:
            for e in events:
                typer.echo(str(e), err=True)


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host", help="Bind address")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Port to listen on")] = 8222,
    model_path: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help=(
                "Model size ('small', 'medium', 'large'; default: medium), "
                "a local safetensors path, or an hf:// / http(s):// URL"
            ),
        ),
    ] = None,
    device: Annotated[
        str,
        typer.Option(
            "--device", "-d", help="Device: 'auto', 'cpu', 'cuda', 'cuda:0', 'mps', …"
        ),
    ] = "auto",
    dtype: Annotated[
        str | None,
        typer.Option(
            "--dtype",
            help=(
                "Transformer dtype: 'float32', 'float16' or 'bfloat16'. "
                "Default: float16 on MPS, float32 elsewhere."
            ),
        ),
    ] = None,
    idle_unload: Annotated[
        int,
        typer.Option(
            "--idle-unload",
            help=(
                "Unload the model from GPU memory after this many idle minutes "
                "(the next request reloads it from the local cache in seconds). "
                "Frees VRAM for other applications while the server sits unused. "
                "0 disables unloading. Only with a size-keyword --model."
            ),
        ),
    ] = 5,
):
    """Run the HTTP transcription server (POST /transcribe → SSE event stream)."""
    import logging

    import uvicorn

    from muscriptor.server import create_app

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    _device = None if device == "auto" else device
    typer.echo("Loading model…")
    model = _load_model(model_path, _device, dtype)
    web_dir = Path(__file__).resolve().parent / "web_dist"

    def model_loader(size: str) -> TranscriptionModel:
        """Build a model of a published size for POST /model swaps."""
        from muscriptor.transcription_model import TranscriptionModel

        return TranscriptionModel.load_model(
            weights_path=size, device=_device, dtype=dtype
        )

    fastapi_app = create_app(
        model,
        web_dir=web_dir if web_dir.is_dir() else None,
        model_loader=model_loader,
        # GET /model reports the truth for size keywords and local paths alike;
        # swapping to a published size works from either starting point.
        model_size=model_path if model_path else "medium",
        idle_unload_s=float(idle_unload * 60) if idle_unload > 0 else None,
    )
    uvicorn.run(fastapi_app, host=host, port=port)


@app.command()
def list_instruments():
    """List the instrument group names accepted by --instruments."""
    for name in MT3_FULL_PLUS_GROUP_NAMES:
        typer.echo(name)


@app.command("arrange-guitar")
def arrange_guitar(
    midi_file: Annotated[
        Path, typer.Argument(help="Input MIDI file (.mid / .midi)")
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output JSON path. Default: <midi_file>.arrangement.json",
        ),
    ] = None,
    list_tracks: Annotated[
        bool,
        typer.Option(
            "--list-tracks",
            help="List the file's note-bearing tracks and exit (no solving).",
        ),
    ] = False,
    track: Annotated[
        int | None,
        typer.Option(
            "--track",
            help="Track index to arrange. Required when several tracks have notes.",
        ),
    ] = None,
    channel: Annotated[
        int | None,
        typer.Option(
            "--channel",
            help="MIDI channel within the track (0-15; 9 is drums).",
        ),
    ] = None,
    tuning: Annotated[
        str, typer.Option("--tuning", help="Instrument preset (currently: standard).")
    ] = "standard",
    max_fret: Annotated[
        int, typer.Option("--max-fret", help="Highest fret considered playable.")
    ] = 24,
    phrase_gap_beats: Annotated[
        float,
        typer.Option(
            "--phrase-gap-beats",
            help="A silence of this many beats starts a new, independently "
            "optimized phrase.",
        ),
    ] = 1.0,
    melody: Annotated[
        str,
        typer.Option(
            "--melody",
            help="Reduce polyphonic input to one melodic line: top (highest "
            "note of each simultaneous onset group), bottom (lowest) or off "
            "(refuse polyphony).",
        ),
    ] = "off",
    overrides: Annotated[
        Path | None,
        typer.Option(
            "--overrides",
            help="JSON file pinning specific notes to string/fret positions "
            '({"version": 1, "locks": [{"note_id": …, "string": …, "fret": …}]}).',
        ),
    ] = None,
    explain: Annotated[
        bool,
        typer.Option(
            "--explain",
            help="Print a per-phrase ergonomic summary (hand positions, "
            "position changes, cost) to stderr.",
        ),
    ] = False,
):
    """Arrange one monophonic MIDI track for guitar (string/fret per note).

    Works purely on the MIDI file: pitches, onsets and durations are never
    changed, no audio model is loaded and nothing but this CPU-only solver
    runs. The result is a versioned JSON document, not yet tablature/PDF.
    """
    from muscriptor.guitar_arrangement import (
        GuitarArrangementError,
        arrange_solution,
        parse_midi,
        to_json,
    )

    try:
        midi_data = midi_file.read_bytes()
        parsed = parse_midi(midi_data)
    except OSError as e:
        typer.echo(f"Error: cannot read {midi_file}: {e}", err=True)
        raise typer.Exit(1)
    except GuitarArrangementError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if list_tracks:
        summaries = parsed.summaries()
        if not summaries:
            typer.echo("No note-bearing tracks.", err=True)
            raise typer.Exit(1)
        typer.echo(
            f"{'track':>5}  {'channel':>7}  {'notes':>5}  {'program':>7}  name"
        )
        for s in summaries:
            typer.echo(
                f"{s['track_index']:>5}  {s['channel']:>7}  {s['note_count']:>5}"
                f"  {str(s['program']) if s['program'] is not None else '-':>7}"
                f"  {s['track_name'] or ''}{'  (drum channel)' if s['drum'] else ''}"
            )
        return

    overrides_text = None
    if overrides is not None:
        try:
            overrides_text = overrides.read_text(encoding="utf-8")
        except OSError as e:
            typer.echo(f"Error: cannot read {overrides}: {e}", err=True)
            raise typer.Exit(1)

    try:
        solution = arrange_solution(
            midi_data,
            filename=midi_file.name,
            track=track,
            channel=channel,
            tuning_name=tuning,
            max_fret=max_fret,
            phrase_gap_beats=phrase_gap_beats,
            melody_policy=melody,
            overrides_text=overrides_text,
        )
    except GuitarArrangementError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if explain:
        _explain_phrases(solution)

    destination = output or midi_file.with_suffix(".arrangement.json")
    destination.write_text(to_json(solution) + "\n", encoding="utf-8")
    notes = [a for p in solution.phrases for a in p.assigned]
    typer.echo(
        f"Arranged {len(notes)} notes in {len(solution.phrases)} "
        f"phrase(s); saved to {destination}",
        err=True,
    )


def _explain_phrases(solution) -> None:
    """--explain: per-phrase ergonomic summary on stderr."""
    from muscriptor.guitar_arrangement import explain_lines

    for line in explain_lines(solution):
        typer.echo(line, err=True)


@app.command("guitar-tab")
def guitar_tab(
    arrangement_json: Annotated[
        Path,
        typer.Argument(help="An arrangement.json produced by arrange-guitar."),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            help="Where to write the ASCII tabulature "
            "(default: <arrangement-stem>.tab.txt).",
        ),
    ] = None,
    midi_out: Annotated[
        Path | None,
        typer.Option(
            "--midi",
            help="Also convert the document back into a MIDI file at this path.",
        ),
    ] = None,
):
    """Convert an arrangement.json into an ASCII tab (and optionally MIDI).

    Pitch, onset and duration come verbatim from the document, so the MIDI is
    exactly what the arranger did to the source track. The tab uses a fixed
    16th-note grid and bar lines every 4 beats — the document carries no
    tempo or meter map.
    """
    import json

    from muscriptor.guitar_arrangement import (
        GuitarArrangementError,
        arrangement_json_to_midi,
        arrangement_json_to_tab,
    )

    try:
        document = json.loads(arrangement_json.read_text(encoding="utf-8"))
    except OSError as e:
        typer.echo(f"Error: cannot read {arrangement_json}: {e}", err=True)
        raise typer.Exit(1)
    except json.JSONDecodeError as e:
        typer.echo(f"Error: {arrangement_json} is not valid JSON: {e}", err=True)
        raise typer.Exit(1)

    try:
        tab_text = arrangement_json_to_tab(document)
        if midi_out is not None:
            midi_bytes = arrangement_json_to_midi(document)
    except GuitarArrangementError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    destination = output or arrangement_json.with_suffix(".tab.txt")
    destination.write_text(tab_text + "\n", encoding="utf-8")
    if midi_out is not None:
        midi_out.write_bytes(midi_bytes)
        typer.echo(f"MIDI written to {midi_out}", err=True)
    typer.echo(f"Tab written to {destination}", err=True)


def main():
    app()


if __name__ == "__main__":
    main()

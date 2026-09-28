<p align="center">
  <img src="web/logo_muscriptor_final.png" alt="MuScriptor Plus" width="300">
</p>

<h1 align="center">MuScriptor Plus</h1>

<p align="center"><a href="README.md">🇷🇺 Русская версия</a></p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/OS-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey" alt="OS">
  <img src="https://img.shields.io/badge/GPU-CUDA%20%7C%20Metal-76b900" alt="GPU">
</p>

**MuScriptor Plus** is an enhanced fork of [MuScriptor](https://github.com/muscriptor/muscriptor) —
the multi-instrument music transcription model by [Kyutai](https://kyutai.org)
and [Mirelo](https://www.mirelo.ai). Give it a recording and get MIDI plus
per-instrument sheet music. The web UI is available in Russian and English.

## What Plus adds over upstream

- **Bilingual web UI** (Russian / English, switcher in the header)
- **Volume controls**: master, independent original/MIDI levels, per-instrument
- **Live model switching** from the web UI (small / medium / large) — plus
  **unloading the model from VRAM** (manual button or automatic after idle)
- **Opt-in lead-vocal removal** before transcription (see below)
- **Engrave any MIDI file** to sheet music from the welcome screen
- **Windows fixes**: automatic MuseScore detection, GPU (cu128) PyTorch, UTF-8
- **`install.bat` / `start.bat`** — a setup wizard and a one-click launcher

Everything else is unchanged: model accuracy, CLI, Python API, output formats.

## Quick start (Windows)

Prerequisites: Windows 10/11, [Git](https://git-scm.com/download/win), and a
[HuggingFace](https://huggingface.co) account with the model license accepted.

```bat
git clone https://github.com/leadpioneer/muscriptor-plus
cd muscriptor-plus
install.bat   :: setup wizard: hardware assessment, uv, Node, deps, web UI, HF weights access, model choice
install_en.bat :: the same wizard with an English UI
start.bat     :: start the server + open the web UI at http://127.0.0.1:8222
```

Manual setup (any OS) is described in [QUICKSTART.md](QUICKSTART.md).

## HuggingFace login (required)

The weights are gated under **CC BY-NC 4.0** (non-commercial use):

1. Accept the license on the [small](https://huggingface.co/MuScriptor/muscriptor-small),
   [medium](https://huggingface.co/MuScriptor/muscriptor-medium) or
   [large](https://huggingface.co/MuScriptor/muscriptor-large) model page
   (access is granted automatically).
2. Authenticate locally:

   ```bash
   uv run hf auth login
   # or: export HF_TOKEN=hf_...
   ```

Weights are downloaded on first use and cached.

## Models

| Variant | Params | Layers | Dim | HuggingFace |
|---|---|---|---|---|
| `small` | 103M | 14 | 768 | [muscriptor-small](https://huggingface.co/MuScriptor/muscriptor-small) |
| `medium` (default) | 307M | 24 | 1024 | [muscriptor-medium](https://huggingface.co/MuScriptor/muscriptor-medium) |
| `large` | 1.4B | 48 | 1536 | [muscriptor-large](https://huggingface.co/MuScriptor/muscriptor-large) |

`small` suits CPU-only machines, `medium` is the speed/accuracy trade-off, and
`large` is the most accurate but needs a GPU (~12 GB VRAM of 16 GB). The model
can be switched live in the web UI header; weights are cached after download.

### GPU memory: unloading the model

The loaded model keeps ~8–12 GB of VRAM resident even while the server is
idle. Two ways to free it:

- **Manually** — the "unload" button next to the model picker in the header.
- **Automatically** — after 5 minutes of idle time (default; change with the
  `--idle-unload <minutes>` flag of `serve`, `0` disables it).

The next request (a transcription or a model switch) transparently reloads
the model from the local cache in seconds — no network. Vocal separation
releases its own memory right after every run.

## Lead-vocal removal (opt-in)

Vocals in the mix are the main source of transcription errors: vocal notes
leak into the MIDI and interfere with guitars and bass. MuScriptor Plus can
**separate the vocals from the instrumental before transcribing** and
transcribe the instrumental instead.

- **Web UI**: a "Remove lead vocals before transcription" checkbox on the
  upload screen (off by default). Progress shows the stages: prepare → vocal
  removal → transcribing the instrumental → MIDI. The download menu gains
  **both stems** (vocals and instrumental, WAV), and the player gets an
  **Original / Instrumental / Vocals** switcher (defaults to "Instrumental"
  after such a run — so what you hear matches what the score was made from;
  stem timelines match the original).
- **CLI**: `uv run muscriptor transcribe song.mp3 --remove-vocals` — both
  stems are saved to `<song>_stems/` next to the input file, and the
  instrumental gets transcribed.
- **How it works**: the
  [audio-separator](https://github.com/karaokenerds/python-audio-separator)
  library with the **Mel-Band-RoFormer Vocals model by Kimberley Jensen**.
  Weights download on first use and are cached; the separation model is
  unloaded from memory right after every run. Separation runs under the same
  lock as transcription, so the two models never share the GPU.
- **Requirements**: ffmpeg on PATH (the `install.bat` wizard offers to
  install it via winget) and a few hundred MB for the weights on first run.
- **No silent fallbacks**: if separation fails, the job stops with a readable
  error — the original audio is never transcribed instead. First run needs
  internet (weight download); everything works offline afterwards.

## CLI

```bash
uv run muscriptor transcribe song.mp3            # MIDI
uv run muscriptor transcribe song.mp3 --format sheets --output score/   # sheet music
uv run muscriptor transcribe song.mp3 --remove-vocals   # without the lead vocal
uv run muscriptor serve --model large            # web UI
uv run muscriptor serve --idle-unload 10         # unload the model after 10 min idle
```

## Guitar fingering arranger (MIDI → strings/frets)

A separate symbolic module for guitar parts: it takes a **MIDI file (not
audio)** and, for one track, picks a string and a fret for every note.
Pitches, onsets and durations are **never changed** — no octave shifts, no
transposition, and no "suspicious" notes are dropped. The optimization is
global: phrases (separated by full silence of ≥ 1 beat) are solved as a whole
with dynamic programming, so early notes may be moved up the neck to avoid a
big jump at the end of a phrase. The result is an optimum with respect to the
current cost function (fret/string movement, a penalty for large position
changes, a weak high-fret penalty) — not "perfect fingering".

String numbering: **1 is the highest** (standard tuning: E4, B3, G3, D3, A2,
E2). The track is picked automatically when there is exactly one non-drum
note-bearing track; otherwise the module lists the candidates.

```bash
uv run muscriptor arrange-guitar song.mid --list-tracks   # what's inside
uv run muscriptor arrange-guitar song.mid --track 2 --output arrangement.json
uv run muscriptor arrange-guitar song.mid --track 2 \
    --tuning standard --max-fret 24 --phrase-gap-beats 1.0
```

Manual pins for the web-UI editor (`--overrides overrides.json`):

```json
{
  "version": 1,
  "locks": [
    {"note_id": "track:2/channel:0/note:17", "string": 2, "fret": 5}
  ]
}
```

A lock must sound exactly the note's original pitch (the module never
transposes); it leaves that note a single candidate and re-solves the whole
phrase — including the chord the note sounds in. Since **schema v3** the
solver's state is a full fingering: every
note carries `string`, `fret`, **`hand_position`** (the fret the index finger
sits at), **`finger`** (0 = open string, 1–4 = fingers), `locked` and both
`legal_positions` (string/fret) and `legal_fingerings` (full states). The
cost models the hand, not the notes' frets: moving between frets within one
hand position is free, a hand shift is visible in the
`position_change_count` / `total_hand_position_travel` metrics, and an open
string or a rest inside the phrase makes a shift cheaper. `--explain`
prints a per-phrase summary to stderr.

One to six simultaneous onsets are normal input: the chord solver keeps
**every** note (one per string, no transposition, no trimmed durations, no
arpeggiation). The optimization is global over the whole phrase — the solver
may pre-position an early chord high to serve the next one. Events of seven
or more notes raise a structured error instead of dropping notes. Asynchronous
overlaps (a ringing bass note) are not silence: they are kept as-is and
reported in the document's `polyphony_analysis`; strict voice separation is a
future stage.

Explicit single-line extraction (`--melody top` / `--melody bottom`) remains
an opt-in mode: the highest/lowest note is picked only among notes sharing
the same onset — it is not melody/bass voice separation.

From the resulting JSON:
- `uv run muscriptor guitar-tab arrangement.json --midi song.mid` writes an
  ASCII tab and the reverse MIDI (pitches, timings and velocities verbatim;
  MIDI never stores the chosen string/fret);
- `uv run muscriptor guitar-musicxml arrangement.json` writes **fingering-
  preserving MusicXML**: every note carries `<technical><string>/<fret>`,
  overlapping durations are laid out across voices, durations are never
  shortened (for unquantized input the engraved shape is the nearest dyadic
  `<type>` while `<duration>` stays verbatim, and short measures are padded
  with rests);
- feed arrangement.json to `POST /arrange/guitar/pdf` to get a score+tab PDF
  engraved by MuseScore with exactly the chosen string/fret — user locks
  included. Plain MIDI cannot do this: MuseScore's auto-tab would invent its
  own positions.

The web UI bundles all of this in the Guitar Arranger Lab (the
"Edit fingering" button — on the welcome screen and after a transcription):
an SVG fretboard with legal positions and locks (the whole chord on screen,
the selected note highlighted, barres), arrow-key navigation across onset
events and chord notes, audition playback (nominal 120 BPM), downloads for
arrangement.json / arrangement.mid / the ASCII tab / MusicXML, and a PDF
that keeps the chosen fingering.

The API exposes a mirror endpoint
`POST /arrange/guitar` (MIDI upload + the same parameters, structured
`{"code", "message", "details"}` errors), plus `POST /arrange/guitar/midi`,
`/tab`, `/musicxml` and `/pdf` — all of them take a confirmed
arrangement.json (schema v3; the converters also accept legacy v2 documents).

Frontend tests need Node 22.19+ (pinned in `web/package.json` and `.nvmrc`).

Sheet music (`--format sheets`) requires **[MuseScore 4+](https://musescore.org/en/download)**
installed (detected automatically on Windows; set `MUSCRIPTOR_MUSESCORE` for
non-standard locations). Works best on music with a steady tempo.

## Windows notes

- **GPU**: PyPI's Windows torch wheel is CPU-only, so this fork pins torch to
  the `cu128` index on Windows (required for RTX 50xx). `uv sync` handles it.
  On a machine **without an NVIDIA GPU** the `install.bat` wizard installs the
  CPU build instead (`uv sync --no-sources`) and writes `device.txt`; then
  `start.bat` launches the server with `uv run --no-sync` so the environment
  is not synced back to cu128.
- **Console encoding**: set `PYTHONUTF8=1` when redirecting output
  (`start.bat` does this) to avoid cp1251 crashes on non-ASCII debug output.
- **MuseScore**: detected automatically; override with `MUSCRIPTOR_MUSESCORE`.
- **FluidSynth** (WAV export): must be on PATH; `start.bat` picks up an
  unpacked official build placed in `tools\fluidsynth` (gitignored).
- **ffmpeg** (lead-vocal removal): the `install.bat` wizard offers to install
  it via winget (`Gyan.FFmpeg`); `start.bat` warns when it's missing from PATH.

## Bugs & feedback

Use the [issue templates](https://github.com/leadpioneer/muscriptor-plus/issues/new/choose)
in this repository.

## License

Code — [MIT](LICENSE) (© Kyutai × Mirelo, © LeadPioneer). Model weights on
[HuggingFace](https://huggingface.co/MuScriptor) —
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) (non-commercial).
The MuseScore General SoundFont used for playback ships under its own (MIT) license.

## Citation

```bibtex
@misc{rouard2026muscriptoropenmodelmultiinstrument,
      title={MuScriptor: An Open Model for Multi-Instrument Music Transcription},
      author={Simon Rouard and Michael Krause and Axel Roebel and Carl-Johann Simon-Gabriel and Alexandre Défossez},
      year={2026},
      eprint={2607.08168},
      archivePrefix={arXiv},
      primaryClass={cs.SD},
      url={https://arxiv.org/abs/2607.08168},
}
```

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
install.bat   :: setup wizard: uv, deps, web UI, HF login, model choice
start.bat     :: start the server + open http://127.0.0.1:8222
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

Sheet music (`--format sheets`) requires **[MuseScore 4+](https://musescore.org/en/download)**
installed (detected automatically on Windows; set `MUSCRIPTOR_MUSESCORE` for
non-standard locations). Works best on music with a steady tempo.

## Windows notes

- **GPU**: PyPI's Windows torch wheel is CPU-only, so this fork pins torch to
  the `cu128` index on Windows (required for RTX 50xx). `uv sync` handles it.
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

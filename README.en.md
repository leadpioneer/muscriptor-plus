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
- **Live model switching** from the web UI (small / medium / large)
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

## CLI

```bash
uv run muscriptor transcribe song.mp3            # MIDI
uv run muscriptor transcribe song.mp3 --format sheets --output score/   # sheet music
uv run muscriptor serve --model large            # web UI
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

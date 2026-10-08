# Быстрый старт / Quick start

Подробная документация — в каталоге [`docs/`](docs/README.md)
(Detailed guides: [`docs/`](docs/README.md)).

## Русский

### 1. Что понадобится

- **uv** — установите по [инструкции](https://docs.astral.sh/uv/getting-started/installation/).
- **Node + pnpm** — только для веб-интерфейса: Node (22.19+) ставится с [nodejs.org](https://nodejs.org), pnpm включается через `corepack enable`. На Windows всё это ставит мастер `install.bat`.
- **Аккаунт HuggingFace** — модель gated: примите лицензию CC BY-NC 4.0 на страницах [small](https://huggingface.co/MuScriptor/muscriptor-small), [medium](https://huggingface.co/MuScriptor/muscriptor-medium) или [large](https://huggingface.co/MuScriptor/muscriptor-large) (доступ выдаётся автоматически).

### 2. Установка

```bash
git clone https://github.com/leadpioneer/muscriptor-plus
cd muscriptor-plus
uv sync          # Python-зависимости; на Windows ставит PyTorch с CUDA (cu128) — для машин с NVIDIA GPU
cd web && pnpm install && pnpm run build && cd ..
```

На Windows-машине **без NVIDIA GPU** ставьте CPU-вариант PyTorch (без
2,5-ГБ CUDA-загрузки): `uv sync --no-sources` — и запускайте сервер командой
`uv run --no-sync muscriptor serve ...` (иначе uv перекатит окружение обратно
на cu128). Мастер `install.bat` делает весь этот выбор сам.

### 3. Авторизация HuggingFace

```bash
uv run hf auth login
# или: $env:HF_TOKEN = "hf_..."  (Windows PowerShell) / export HF_TOKEN=hf_... (Linux, macOS)
```

### 4. Запуск

Проще всего — три батника в корне репозитория:

```bat
install.bat   :: мастер установки: оценка железа, uv, Node, зависимости, сборка UI, доступ к весам HF, выбор модели
install_en.bat :: тот же мастер с интерфейсом на английском
start.bat     :: запуск сервера и открытие веб-интерфейса на http://127.0.0.1:8222
```

`install.bat` можно перезапускать; выбранная модель сохраняется в `model.txt`
(её потом можно менять и прямо в веб-интерфейсе). Ручной вариант:

```bash
uv run muscriptor serve                 # веб-интерфейс на http://127.0.0.1:8222
uv run muscriptor serve --model large   # сразу большая модель
uv run muscriptor transcribe song.mp3   # из командной строки
```

Модель переключается и прямо из веб-интерфейса (выпадающий список в шапке); веса скачиваются при первом выборе и кешируются. Через 5 минут простоя модель автоматически выгружается из видеопамяти (`--idle-unload <минуты>` у `serve`, `0` — выключить) и перезагружается по первому запросу.

### 5. Windows: известные нюансы

- **GPU**: в `pyproject.toml` torch на Windows уже привязан к CUDA-индексу `cu128` (нужно для RTX 50xx). Без GPU-карты всё работает на CPU, только медленно.
- **Кодировка консоли**: запуская через `Start-Process` с перенаправлением вывода, задайте `$env:PYTHONUTF8 = '1'` — иначе отладочный вывод модели падает на не-ASCII символах.
- **MuseScore (ноты в PDF)**: [MuseScore 4+](https://musescore.org/en/download) ставится отдельно; стандартные пути установки (`C:\Program Files\MuseScore 4\bin\…`) находятся автоматически, для нестандартного пути задайте `MUSCRIPTOR_MUSESCORE`. Мастер `install.bat` (шаг 9) предложит установить его через winget, если его нет.
- **FluidSynth (скачивание WAV)**: нужен бинарник `fluidsynth`; удобный способ — официальный [Windows-билд](https://github.com/FluidSynth/fluidsynth/releases), распакованный в `tools/fluidsynth` — `start.bat` добавит его в PATH сам, а мастер проверяет наличие на шаге 9.
- **ffmpeg (удаление ведущего вокала)**: нужен в PATH; `install.bat` предложит установить через winget (`Gyan.FFmpeg`). Опция включается галочкой на экране загрузки или флагом `--remove-vocals` в CLI; веса модели разделения скачиваются при первом запуске и кешируются.

### 6. Что дальше

- [Установка](docs/installation.md) — все способы, кэши, модели, Intel Mac.
- [CLI](docs/cli.md) — полный справочник команд и опций.
- [Веб-интерфейс](docs/web-ui.md) — как пользоваться плеером, нотами и гитарной лабораторией.
- [HTTP API](docs/api.md) — эндпоинты и SSE-протокол.
- [Диагностика](docs/troubleshooting.md) — если что-то не работает.

---

## English

### 1. Prerequisites

- **uv** — see the [installation guide](https://docs.astral.sh/uv/getting-started/installation/).
- **Node + pnpm** — only for the web UI: install Node (22.19+) from [nodejs.org](https://nodejs.org), then `corepack enable`. On Windows the `install.bat` wizard does this for you.
- **A HuggingFace account** — the model is gated: accept the CC BY-NC 4.0 license on the [small](https://huggingface.co/MuScriptor/muscriptor-small), [medium](https://huggingface.co/MuScriptor/muscriptor-medium) or [large](https://huggingface.co/MuScriptor/muscriptor-large) page (access is granted automatically).

### 2. Install

```bash
git clone https://github.com/leadpioneer/muscriptor-plus
cd muscriptor-plus
uv sync          # Python deps; on Windows torch comes from the CUDA (cu128) index
cd web && pnpm install && pnpm run build && cd ..
```

On a Windows machine **without an NVIDIA GPU**, install the CPU-only PyTorch
build instead (skips the 2.5 GB CUDA download): `uv sync --no-sources`, then
start the server with `uv run --no-sync muscriptor serve ...` (otherwise uv
syncs the environment back to cu128). The `install.bat` wizard makes this
choice for you.

### 3. HuggingFace login

```bash
uv run hf auth login
# or: export HF_TOKEN=hf_...
```

### 4. Run

The easiest way — three batch files in the repo root:

```bat
install.bat   :: setup wizard: hardware assessment, uv, Node, deps, web UI build, HF weights access, model choice
install_en.bat :: the same wizard with an English UI
start.bat     :: start the server and open the web UI at http://127.0.0.1:8222
```

`install.bat` can be re-run; the chosen model is stored in `model.txt`
(you can also switch models later right in the web UI). Manual option:

```bash
uv run muscriptor serve                 # web UI at http://127.0.0.1:8222
uv run muscriptor serve --model large   # start with the large model
uv run muscriptor transcribe song.mp3   # command-line transcription
```

The model can also be switched from the web UI (dropdown in the header); weights are downloaded on first use and cached. After 5 minutes of idle time the model is automatically unloaded from VRAM (`--idle-unload <minutes>` on `serve`, `0` disables) and reloaded on the next request.

### 5. Windows notes

- **GPU**: on Windows `pyproject.toml` already pins torch to the `cu128` index (required for RTX 50xx). Without a GPU everything runs on CPU, just slower.
- **Console encoding**: when launching with redirected output (`Start-Process`), set `$env:PYTHONUTF8 = '1'` — otherwise the model's debug output can crash on non-ASCII characters.
- **MuseScore (PDF sheet music)**: install [MuseScore 4+](https://musescore.org/en/download) separately; standard install locations (`C:\Program Files\MuseScore 4\bin\…`) are detected automatically, otherwise set `MUSCRIPTOR_MUSESCORE`. The wizard offers to install it via winget when missing (step 9).
- **FluidSynth (WAV downloads)**: needs a `fluidsynth` binary; the easiest way is the official [Windows build](https://github.com/FluidSynth/fluidsynth/releases) unpacked into `tools/fluidsynth` — `start.bat` adds it to the process PATH for you, and the wizard checks it in step 9.
- **ffmpeg (lead-vocal removal)**: must be on PATH; `install.bat` offers to install it via winget (`Gyan.FFmpeg`). Enable the option with the checkbox on the upload screen or the `--remove-vocals` CLI flag; separation weights download on first use and are cached.

### 6. Next steps

- [Installation](docs/installation.md) — every setup path, caches, models, Intel Mac.
- [CLI reference](docs/cli.md) — all commands and options.
- [Web UI guide](docs/web-ui.md) — player, sheet music, Guitar Arranger Lab.
- [HTTP API](docs/api.md) — endpoints and the SSE protocol.
- [Troubleshooting](docs/troubleshooting.md) — when something breaks.

# Быстрый старт / Quick start

## Русский

### 1. Что понадобится

- **uv** — установите по [инструкции](https://docs.astral.sh/uv/getting-started/installation/).
- **Node + pnpm** — только для веб-интерфейса: Node можно поставить через `pnpm` ([инструкция](https://pnpm.io/installation)), pnpm включается через `corepack enable pnpm`.
- **Аккаунт HuggingFace** — модель gated: примите лицензию CC BY-NC 4.0 на страницах [small](https://huggingface.co/MuScriptor/muscriptor-small), [medium](https://huggingface.co/MuScriptor/muscriptor-medium) или [large](https://huggingface.co/MuScriptor/muscriptor-large) (доступ выдаётся автоматически).

### 2. Установка

```bash
git clone https://github.com/leadpioneer/muscriptor-plus
cd muscriptor-plus
uv sync          # Python-зависимости; на Windows torch ставится с CUDA (cu128)
cd web && pnpm install && pnpm run build && cd ..
```

### 3. Авторизация HuggingFace

```bash
uv run hf auth login
# или: $env:HF_TOKEN = "hf_..."  (Windows PowerShell) / export HF_TOKEN=hf_... (Linux, macOS)
```

### 4. Запуск

Проще всего — два батника в корне репозитория:

```bat
install.bat   :: мастер установки: uv, зависимости, сборка UI, HF-логин, выбор модели
start.bat     :: запуск сервера и открытие браузера на http://127.0.0.1:8222
```

`install.bat` можно перезапускать; выбранная модель сохраняется в `model.txt`
(её потом можно менять и прямо в веб-интерфейсе). Ручной вариант:

```bash
uv run muscriptor serve                 # веб-интерфейс на http://127.0.0.1:8222
uv run muscriptor serve --model large   # сразу большая модель
uv run muscriptor transcribe song.mp3   # из командной строки
```

Модель переключается и прямо из веб-интерфейса (выпадающий список в шапке); веса скачиваются при первом выборе и кешируются.

### 5. Windows: известные нюансы

- **GPU**: в `pyproject.toml` torch на Windows уже привязан к CUDA-индексу `cu128` (нужно для RTX 50xx). Без GPU-карты всё работает на CPU, только медленно.
- **Кодировка консоли**: запуская через `Start-Process` с перенаправлением вывода, задайте `$env:PYTHONUTF8 = '1'` — иначе отладочный вывод модели падает на не-ASCII символах.
- **MuseScore (ноты в PDF)**: [MuseScore 4+](https://musescore.org/en/download) ставится отдельно; стандартные пути установки (`C:\Program Files\MuseScore 4\bin\…`) находятся автоматически, для нестандартного пути задайте `MUSCRIPTOR_MUSESCORE`.
- **FluidSynth (скачивание WAV)**: нужен бинарник `fluidsynth` в PATH; удобный способ — официальный [Windows-билд](https://github.com/FluidSynth/fluidsynth/releases), распакованный в `tools/fluidsynth` и добавленный в PATH процесса.

---

## English

### 1. Prerequisites

- **uv** — see the [installation guide](https://docs.astral.sh/uv/getting-started/installation/).
- **Node + pnpm** — only for the web UI: install Node [via pnpm](https://pnpm.io/installation), then `corepack enable pnpm`.
- **A HuggingFace account** — the model is gated: accept the CC BY-NC 4.0 license on the [small](https://huggingface.co/MuScriptor/muscriptor-small), [medium](https://huggingface.co/MuScriptor/muscriptor-medium) or [large](https://huggingface.co/MuScriptor/muscriptor-large) page (access is granted automatically).

### 2. Install

```bash
git clone https://github.com/leadpioneer/muscriptor-plus
cd muscriptor-plus
uv sync          # Python deps; on Windows torch comes from the CUDA (cu128) index
cd web && pnpm install && pnpm run build && cd ..
```

### 3. HuggingFace login

```bash
uv run hf auth login
# or: export HF_TOKEN=hf_...
```

### 4. Run

The easiest way — two batch files in the repo root:

```bat
install.bat   :: setup wizard: uv, deps, web UI build, HF login, model choice
start.bat     :: start the server and open http://127.0.0.1:8222
```

`install.bat` can be re-run; the chosen model is stored in `model.txt`
(you can also switch models later right in the web UI). Manual option:

```bash
uv run muscriptor serve                 # web UI at http://127.0.0.1:8222
uv run muscriptor serve --model large   # start with the large model
uv run muscriptor transcribe song.mp3   # command-line transcription
```

The model can also be switched from the web UI (dropdown in the header); weights are downloaded on first use and cached.

### 5. Windows notes

- **GPU**: on Windows `pyproject.toml` already pins torch to the `cu128` index (required for RTX 50xx). Without a GPU everything runs on CPU, just slower.
- **Console encoding**: when launching with redirected output (`Start-Process`), set `$env:PYTHONUTF8 = '1'` — otherwise the model's debug output can crash on non-ASCII characters.
- **MuseScore (PDF sheet music)**: install [MuseScore 4+](https://musescore.org/en/download) separately; standard install locations (`C:\Program Files\MuseScore 4\bin\…`) are detected automatically, otherwise set `MUSCRIPTOR_MUSESCORE`.
- **FluidSynth (WAV downloads)**: a `fluidsynth` binary must be on PATH; the easiest way is the official [Windows build](https://github.com/FluidSynth/fluidsynth/releases) unpacked into `tools/fluidsynth` and added to the process PATH.

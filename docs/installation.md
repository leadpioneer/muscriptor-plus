# Установка

Документ описывает все способы установки MuScriptor Plus: автоматический мастер
для Windows, ручную установку на Windows/Linux/macOS, доступ к весам
HuggingFace, выбор модели и сопутствующие программы.

- [Windows: мастер установки](#windows-мастер-установки)
- [Windows: запуск](#windows-запуск)
- [Ручная установка (все ОС)](#ручная-установка)
- [Особые случаи: Intel Mac и Apple Silicon](#особые-случаи-intel-mac-и-apple-silicon)
- [Доступ к весам HuggingFace](#доступ-к-весам-huggingface)
- [Модели](#модели)
- [Устройство и PyTorch](#устройство-и-pytorch)
- [Сопутствующие программы](#сопутствующие-программы)
- [Что и где кэшируется](#что-и-где-кэшируется)
- [Переменные окружения](#переменные-окружения)
- [Обновление](#обновление)
- [Docker](#docker)

## Windows: мастер установки

Понадобятся Windows 10/11, [Git](https://git-scm.com/download/win) и аккаунт
HuggingFace (см. [ниже](#доступ-к-весам-huggingface)).

```bat
git clone https://github.com/leadpioneer/muscriptor-plus
cd muscriptor-plus
install.bat      :: русский интерфейс мастера
install_en.bat   :: тот же мастер на английском
```

`install.bat` (и его англоязычная копия `install_en.bat`) проводит девять
шагов и **не пропускает шаг, пока он не выполнен**. Мастер можно безопасно
перезапускать: уже выполненные шаги проходятся за секунды.

1. **Оценка железа.** Смотрит число ядер, объём RAM, наличие NVIDIA GPU
   (через `nvidia-smi`) и объём видеопамяти, затем рекомендует модель:
   CPU → `small`; GPU с < 4 ГБ VRAM → `small`; GPU с ≥ 11 ГБ VRAM → `large`;
   остальным GPU → `medium`.
2. **winget.** Без него мастер не сможет ставить пакеты сам. Если winget нет,
   установите «App Installer» из Microsoft Store и запустите мастер заново.
3. **uv** — менеджер Python-зависимостей (ставится через
   `winget install astral-sh.uv`, если его нет).
4. **Node.js LTS** (нужен только для сборки веб-интерфейса). Мастер проверяет
   версию: требуется **22.19+**.
5. **Python-зависимости.** На машине с NVIDIA GPU — `uv sync` (torch с
   индексом `cu128`); без GPU — `uv sync --no-sources` (CPU-сборка torch с
   PyPI). На CPU-машинах мастер сохраняет и возвращает `uv.lock`, чтобы
   CPU-резолюция не заменила лок репозитория, и проверяет, что torch
   импортируется.
6. **Сборка веб-интерфейса** (`corepack pnpm install` + `pnpm run build`).
   Результат попадает в `muscriptor\web_dist`.
7. **Выбор модели по умолчанию.** Записывается в `model.txt`
   (`small` / `medium` / `large`). Потом модель можно менять прямо в
   веб-интерфейсе.
8. **Доступ к весам HuggingFace.** Мастер объясняет, как принять лицензию,
   предлагает войти (`hf auth login`), проверяет доступ скачиванием
   `config.json` выбранной модели и может заранее скачать веса, чтобы первый
   запуск был быстрым.
9. **Сопутствующие программы** — ffmpeg, MuseScore 4, FluidSynth (см.
   [ниже](#сопутствующие-программы)). Для каждой мастер предлагает установку
   через winget или открывает страницу загрузки и повторяет проверку.

В конце мастер пишет `device.txt` (`cpu` или `cuda`) — по нему `start.bat`
выбирает режим запуска. Файлы `model.txt` и `device.txt` добавлены в
`.gitignore` и не попадают в коммиты.

## Windows: запуск

```bat
start.bat
```

Что делает `start.bat`:

- включает UTF-8 (`chcp 65001`, `PYTHONUTF8=1`) — иначе вывод Python падает
  на cp1251 при перенаправленном выводе;
- добавляет `tools\fluidsynth` в `PATH`, если там распакован FluidSynth;
- предупреждает, если `ffmpeg` не найден (без него не будет удаления вокала);
- читает `model.txt` (по умолчанию `medium`) и `device.txt` (по умолчанию
  `cuda`);
- на CPU-машине запускает `uv run --no-sync`, чтобы uv не перекатил окружение
  обратно на CUDA-сборку torch;
- если сервер уже отвечает на `/health`, просто открывает браузер;
- иначе запускает `uv run [--no-sync] muscriptor serve --model <модель>
  --host 127.0.0.1 --port 8222` в отдельном свёрнутом окне, ждёт до 5 минут
  ответа `/health` и открывает <http://127.0.0.1:8222>.

Сервер живёт, пока открыто его свёрнутое окно `MuScriptor Plus server`;
закрытие окна останавливает сервер.

## Ручная установка

Если вы не на Windows или предпочитаете ставить всё сами:

```bash
git clone https://github.com/leadpioneer/muscriptor-plus
cd muscriptor-plus

# 1. Python-зависимости (нужен uv: https://docs.astral.sh/uv/)
uv sync

# 2. Веб-интерфейс (нужен Node 22.19+; pnpm включается через corepack enable)
cd web && pnpm install && pnpm run build && cd ..

# 3. Авторизация на HuggingFace
uv run hf auth login        # либо: export HF_TOKEN=hf_... / $env:HF_TOKEN = "hf_..."

# 4. Запуск
uv run muscriptor serve                 # http://127.0.0.1:8222
uv run muscriptor transcribe song.mp3   # из командной строки
```

Веб-интерфейс собирается один раз (если не менять фронтенд — больше не
понадобится). Без него `serve` поднимет только API без страниц.

**Windows без NVIDIA GPU.** Ставьте CPU-вариант torch, чтобы не качать
~2,5 ГБ CUDA-колёс, и дальше запускайте сервер с `--no-sync`:

```bash
uv sync --no-sources
uv run --no-sync muscriptor serve
```

`install.bat` делает этот выбор автоматически. Полный список команд CLI —
в [cli.md](cli.md).

## Особые случаи: Intel Mac и Apple Silicon

- **Apple Silicon (M1/M2/M3/…)** — всё работает из коробки; модель
  автоматически идёт через Metal (MPS), dtype по умолчанию `float16`.
- **Intel Mac** — PyTorch перестал выпускать колёса для x86_64 после 2.2.2, а
  torch 2.2.2 поддерживает только Python ≤ 3.12. Поэтому на Intel Mac
  нужно зафиксировать Python:

  ```bash
  uv sync --python 3.12
  uv run muscriptor serve
  ```

  Ограничения Intel Mac: pin `torch<2.3`/`numpy<2` исключает
  `audio-separator`, поэтому **удаление ведущего вокала недоступно** — при
  попытке включить его вы получите понятную ошибку о недостающей зависимости.
  Запуск без клонирования репозитория: `uvx --python 3.12 muscriptor serve`.

## Доступ к весам HuggingFace

Веса модели закрыты gated-доступом и лицензией **CC BY-NC 4.0**
(некоммерческое использование):

1. Войдите (или зарегистрируйтесь) на [huggingface.co](https://huggingface.co).
2. Примите лицензию на странице нужной модели:
   [small](https://huggingface.co/MuScriptor/muscriptor-small),
   [medium](https://huggingface.co/MuScriptor/muscriptor-medium) или
   [large](https://huggingface.co/MuScriptor/muscriptor-large) — доступ
   выдаётся автоматически.
3. Авторизуйтесь на машине одним из способов:
   - `uv run hf auth login` (команда `hf` входит в зависимости проекта);
   - либо создайте read-токен на
     [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
     и задайте его переменной `HF_TOKEN`:

     ```bash
     export HF_TOKEN=hf_...        # Linux/macOS
     $env:HF_TOKEN = "hf_..."      # PowerShell
     ```

Веса скачиваются при первом использовании и кэшируются. Если доступ не
подтверждён, и CLI, и сервер выводят пошаговую инструкцию вместо трассировки
стека. Разделение вокала качает собственную модель отдельно (см.
[Сопутствующие программы](#ffmpeg-и-удаление-ведущего-вокала)).

## Модели

| Вариант | Параметры | Слои | Dim | HuggingFace |
|---|---|---|---|---|
| `small` | 103M | 14 | 768 | [muscriptor-small](https://huggingface.co/MuScriptor/muscriptor-small) |
| `medium` (по умолчанию) | 307M | 24 | 1024 | [muscriptor-medium](https://huggingface.co/MuScriptor/muscriptor-medium) |
| `large` | 1.4B | 48 | 1536 | [muscriptor-large](https://huggingface.co/MuScriptor/muscriptor-large) |

- `small` — практичный выбор для CPU и слабых GPU;
- `medium` — баланс скорости и точности, значение по умолчанию;
- `large` — самая точная; занимает около 12 ГБ VRAM, поэтому нужен GPU.

Где можно выбирать модель (`--model` в CLI, `--model` у `serve`, выпадающий
список в шапке веб-интерфейса, `load_model()` в Python API):

- ключевое слово `small` / `medium` / `large` — веса скачиваются с
  HuggingFace и кэшируются;
- локальный файл `.safetensors`;
- URL `hf://<repo>/<файл>` или `http(s)://...`.

В веб-интерфейсе модель переключается **на ходу**: новые веса грузятся в фоне,
во время транскрипции переключение отклоняется, память старой модели
освобождается. Кнопка «выгрузить» рядом с выбором модели освобождает VRAM
вручную; после 5 минут простоя (по умолчанию) модель выгружается сама
(опция `serve --idle-unload <минуты>`, `0` — выключить). Перезагрузка той же
модели идёт из локального кэша, за секунды и без сети; переключение на модель,
которой ещё нет в кэше, сначала скачает её веса.

## Устройство и PyTorch

- **Автовыбор** (`--device auto`, по умолчанию): CUDA → MPS (только Apple
  Silicon) → CPU. Явно: `--device cpu`, `cuda`, `cuda:0`, `mps`, …
- **dtype** (`--dtype`): по умолчанию `float16` на MPS и `float32` на
  остальных устройствах; на CUDA модель считается в fp16 через autocast.
  Доступны `float32`, `float16`, `bfloat16`.
- **Windows + NVIDIA**: в `pyproject.toml` torch привязан к индексу
  `cu128` — это обязательно для RTX 50xx и подходит старым картам. `uv sync`
  делает это сам.
- **Windows без NVIDIA**: мастер ставит CPU-сборку (`uv sync --no-sources`).
- **CPU** работает без GPU, но медленнее; для CPU рекомендуется `small`.

## Сопутствующие программы

Все три необязательны по отдельности: без них MuScriptor работает, просто
теряется соответствующая функция. Но мастер `install.bat` считает шаг 9
обязательным и не завершится, пока каждая программа не найдена; если
какие-то из них вам не нужны, воспользуйтесь
[ручной установкой](#ручная-установка).

### MuseScore 4+ — ноты в PDF/MusicXML

Нужен для `--format sheets`, эндпоинта `POST /sheets` и PDF в гитарной
лаборатории. Скачать: [musescore.org/en/download](https://musescore.org/en/download)
(мастер предлагает `winget install MuseScore.MuseScore`).

Поиск выполняется автоматически: сначала `$MUSCRIPTOR_MUSESCORE`, затем PATH,
затем стандартные места установки (Windows: `%ProgramFiles%\MuseScore*`,
`%ProgramFiles(x86)%\MuseScore*`, `%LOCALAPPDATA%\Programs\MuseScore*`;
macOS: `/Applications/MuseScore 4.app`; Linux: AppImage в `$HOME`). MuseScore 3
отклоняется: он пишет другой формат проекта, и корректная табулатура из него
не получается.

### FluidSynth — экспорт WAV

Нужен для `--auralize` и `POST /auralize` (синтез MIDI в WAV). Бинарник должен
быть в `PATH`. Удобный вариант для Windows — официальный
[билд](https://github.com/FluidSynth/fluidsynth/releases), распакованный в
`tools/fluidsynth` (папка в `.gitignore`): `start.bat` сам добавит его в PATH.
Мастер проверяет наличие на шаге 9.

### ffmpeg и удаление ведущего вокала

Нужен для опции «Удалить ведущий вокал». Установка:
`winget install Gyan.FFmpeg` (мастер сделает это сам) и перезапуск консоли.
Первый запуск разделения скачает веса модели (несколько сотен МБ) в
`.../muscriptor/audio-separator` (см. ниже) и дальше работает офлайн.

## Что и где кэшируется

| Что | Где | Примечание |
|---|---|---|
| Веса модели (HF) | кэш `huggingface_hub`, обычно `~/.cache/huggingface` | путь переопределяется `HF_HOME` |
| Веса по прямым `http(s)://`-URL | `~/.cache/muscriptor/` (на Windows: `%USERPROFILE%\.cache\muscriptor`) | имя файла с префиксом-хэшем URL |
| SoundFont `.sf2` (для WAV) и `.sf3` (для браузера) | кэш `huggingface_hub`; `.sf2` дополнительно ищется в корне репозитория | отдаётся/грузится из `hf://MuScriptor/assets` |
| Веса разделения вокала | Windows: `%LOCALAPPDATA%\muscriptor\audio-separator`; macOS: `~/Library/Caches/muscriptor/audio-separator`; Linux: `~/.cache/muscriptor/audio-separator` | скачивает audio-separator |
| Стемы вокала/инструментала | системный temp: `muscriptor-stems-<id>` | живут 1 час, не более 8 прогонов (см. [api.md](api.md#get-stemsrun_idstem)) |

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `HF_TOKEN` | токен HuggingFace вместо `hf auth login` |
| `HF_HOME` | переопределить кэш HuggingFace |
| `MUSCRIPTOR_MUSESCORE` | путь к исполняемому файлу MuseScore 4+ |
| `PYTHONUTF8=1` | обязательна при перенаправленном выводе на Windows (cp1251) |
| `BACKEND_URL` | для `pnpm dev`: адрес бэкенда (по умолчанию `http://127.0.0.1:8222`) |
| `VITE_GA_MEASUREMENT_ID` | ID Google Analytics при сборке фронтенда; пусто — аналитика выключена |

## Обновление

```bash
git pull
uv sync                          # на CPU-Windows: uv sync --no-sources
cd web && pnpm install && pnpm run build && cd ..
```

После обновления перезапустите `start.bat` (или `uv run muscriptor serve`).

## Docker

В репозитории есть `Dockerfile`: он собирает веб-интерфейс, ставит MuseScore
(AppImage), FluidSynth и заранее скачивает звуковые шрифты.

```bash
docker build -t muscriptor .
docker run --gpus all -p 8000:8000 -e HF_TOKEN=hf_... muscriptor --port 8000
```

Точка входа — `uv run muscriptor serve --host 0.0.0.0`; аргументы после образа
добавляются к ней. Подробности о серверном развёртывании — в
[architecture.md](architecture.md#развёртывание-сервера).

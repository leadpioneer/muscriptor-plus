<p align="center">
  <img src="web/logo_muscriptor_final.png" alt="MuScriptor Plus" width="300">
</p>

<h1 align="center">MuScriptor Plus</h1>

<p align="center">
  <a href="README.en.md">🇬🇧 English version</a> ·
  <a href="QUICKSTART.md">Быстрый старт</a> ·
  <a href="https://github.com/leadpioneer/muscriptor-plus/issues/new/choose">Сообщить о баге</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/OS-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey" alt="OS">
  <img src="https://img.shields.io/badge/GPU-CUDA%20%7C%20Metal-76b900" alt="GPU">
</p>

**MuScriptor Plus** — расширенный форк [MuScriptor](https://github.com/muscriptor/muscriptor):
модели автоматической мультиинструментальной транскрипции от [Kyutai](https://kyutai.org)
и [Mirelo](https://www.mirelo.ai). Загружаете запись — получаете MIDI и нотный лист
по каждому инструменту. Поддерживается русский и английский интерфейс.

## Чем Plus отличается от оригинала

| Возможность | Оригинал | Plus |
|---|---|---|
| Интерфейс | английский | **русский + английский** (переключатель в шапке) |
| Громкость | общий кроссфейд | **мастер, оригинал/MIDI по отдельности, каждый инструмент** |
| Выбор модели | только флагом при запуске | **переключение прямо в веб-интерфейсе + выгрузка модели из VRAM** |
| MIDI → ноты | только из расшифровки | **любой ваш MIDI-файл** |
| Ведущий вокал | портит расшифровку | **opt-in удаление вокала перед транскрипцией** (см. ниже) |
| Windows | MuseScore/FluidSynth руками | **автоопределение MuseScore, GPU-сборка PyTorch (cu128), UTF-8** |
| Установка | вручную | **мастер `install.bat` + `start.bat`** |

Основа оригинала не тронута: точность модели, CLI, Python API, форматы.

## Быстрый старт (Windows)

Понадобятся: Windows 10/11, [Git](https://git-scm.com/download/win), аккаунт
[HuggingFace](https://huggingface.co) с принятой лицензией модели (см. ниже).

```bat
git clone https://github.com/leadpioneer/muscriptor-plus
cd muscriptor-plus
install.bat   :: мастер установки: uv, зависимости, веб-UI, HF-логин, выбор модели
start.bat     :: запуск сервера + открытие браузера на http://127.0.0.1:8222
```

`install.bat` проведёт по шагам и запомнит выбранную модель; `start.bat` дальше
запускает сервер одной командой. Всё то же самое вручную — в
[QUICKSTART.md](QUICKSTART.md).

## Вход в HuggingFace (обязателен)

Веса модели опубликованы под лицензией **CC BY-NC 4.0** (некоммерческое
использование) и закрыты gated-доступом:

1. Примите лицензию на странице модели: [small](https://huggingface.co/MuScriptor/muscriptor-small),
   [medium](https://huggingface.co/MuScriptor/muscriptor-medium) или
   [large](https://huggingface.co/MuScriptor/muscriptor-large) — доступ выдаётся автоматически.
2. Авторизуйтесь на машине (мастер `install.bat` сделает это за вас):

   ```bash
   uv run hf auth login
   ```

   либо задайте токен (создаётся на
   [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)):

   ```bash
   export HF_TOKEN=hf_...        # Linux/macOS
   $env:HF_TOKEN = "hf_..."      # PowerShell
   ```

Веса скачиваются при первом использовании и кешируются локально.

## Модели

| Вариант | Параметры | Слои | Dim | HuggingFace |
|---|---|---|---|---|
| `small` | 103M | 14 | 768 | [muscriptor-small](https://huggingface.co/MuScriptor/muscriptor-small) |
| `medium` (по умолчанию) | 307M | 24 | 1024 | [muscriptor-medium](https://huggingface.co/MuScriptor/muscriptor-medium) |
| `large` | 1.4B | 48 | 1536 | [muscriptor-large](https://huggingface.co/MuScriptor/muscriptor-large) |

- `small` — для машин без GPU; `medium` — баланс скорости и точности;
  `large` — самая точная, но требует GPU (на 16 ГБ VRAM занимает ~12 ГБ).
- В веб-интерфейсе модель переключается **на ходу** из выпадающего списка в
  шапке: новые веса грузятся в фоне, во время транскрипции переключение
  отклоняется, память старой модели освобождается. Веса кешируются.
- На Apple Silicon модель автоматически работает через Metal (MPS).

### Память GPU: выгрузка модели

Загруженная модель держит свои ~8–12 ГБ в VRAM, даже когда сервер простаивает.
Освободить память можно двумя способами:

- **Вручную** — кнопка «выгрузить» рядом с выбором модели в шапке.
- **Автоматически** — после 5 минут простоя (по умолчанию; меняется опцией
  `--idle-unload <минуты>` у `serve`, `0` — выключить).

Следующий запрос (транскрипция, смена модели) прозрачнo перезагружает модель
из локального кэша за несколько секунд — без сети. Разделение вокала тоже
освобождает свою память сразу после каждого прогона.

## Удаление ведущего вокала (opt-in)

Вокал в миксе — главный источник ошибок транскрипции: вокальные ноты
попадают в MIDI и мешают распознаванию гитар и баса. MuScriptor Plus умеет
перед транскрипцией **отделять вокал от инструментала** и расшифровывать
именно инструментал.

- **Веб-интерфейс**: на экране загрузки галочка «Удалить ведущий вокал перед
  транскрипцией» (выключена по умолчанию). Прогресс показывает стадии:
  подготовка → удаление вокала → транскрипция инструментала → MIDI. В меню
  скачивания появляются **оба стема** (вокал и инструментал, WAV), а рядом с
  плеером — переключатель прослушивания **Оригинал / Инструментал / Вокал**
  (по умолчанию после прогона включён «Инструментал» — чтобы слышимое
  совпадало с тем, по чему снята партитура; таймлайн стемов совпадает с
  оригиналом).
- **CLI**: `uv run muscriptor transcribe song.mp3 --remove-vocals` — оба стема
  сохраняются в `<song>_stems/` рядом с входным файлом, расшифровывается
  инструментал.
- **Как работает**: библиотека
  [audio-separator](https://github.com/karaokenerds/python-audio-separator) с
  моделью **Mel-Band-RoFormer Vocals от Kimberley Jensen**. Веса скачиваются
  при первом запуске и кешируются; модель выгружается из памяти сразу после
  разделения. Разделение выполняется под той же блокировкой, что и
  транскрипция, поэтому две модели никогда не делят GPU.
- **Что нужно**: ffmpeg в PATH (мастер `install.bat` предложит установить
  через winget) и ~несколько сотен МБ на веса при первом запуске.
- **Без тихих откатов**: если разделение не удалось, задание завершается
  понятной ошибкой — транскрипция оригинала не запускается. Первый запуск
  требует интернет (скачивание весов), дальше всё работает офлайн.

## CLI

```bash
uv run muscriptor transcribe song.mp3            # MIDI
uv run muscriptor transcribe song.mp3 --format sheets --output score/   # ноты
uv run muscriptor transcribe song.mp3 --remove-vocals   # без ведущего вокала
uv run muscriptor serve --model large            # веб-интерфейс
uv run muscriptor serve --idle-unload 10         # выгружать модель после 10 мин простоя
```
## Гитарный аранжировщик аппликатуры (MIDI → струны/лады)

Отдельный символьный модуль для гитарных партий: он принимает **MIDI-файл
(не аудио)** и для одной монофонической дорожки подбирает струну и лад для
каждой ноты. Высоты нот, начала и длительности **не изменяются** — октавных
переносов и транспозиции нет; «сомнительные» ноты не удаляются. Оптимизация
глобальная: фразы (разделённые паузой ≥ 1 бита) решаются динамическим
программированием целиком, поэтому ранние ноты могут быть сдвинуты выше по
грифу, чтобы избежать резкого скачка в конце фразы. Результат — оптимум
относительно текущей функции стоимости (переходы по ладам/струнам, штраф за
резкую смену позиции, слабый штраф за высокие лады), а не «идеальная
аппликатура».

Нумерация струн: **1 — самая высокая** (стандартный строй: E4, B3, G3, D3,
A2, E2). Первая версия работает только с монофонией: одновременные начала
нот дают понятную ошибку — сначала выделите мелодическую дорожку. Дорожка
выбирается автоматически, если недрамовая нотоносная дорожка одна; иначе
модуль перечислит кандидатов.

```bash
uv run muscriptor arrange-guitar song.mid --list-tracks   # что внутри файла
uv run muscriptor arrange-guitar song.mid --track 2 --output arrangement.json
uv run muscriptor arrange-guitar song.mid --track 2 \
    --tuning standard --max-fret 24 --phrase-gap-beats 1.0
```

Ручные фиксации для будущего редактора (`--overrides overrides.json`):

```json
{
  "version": 1,
  "locks": [
    {"note_id": "track:2/channel:0/note:17", "string": 2, "fret": 5}
  ]
}
```

Lock проверяет, что позиция звучит в точности исходную высоту (транспонировать
модуль не умеет), оставляет для ноты единственного кандидата и пересчитывает
всю фразу. В `arrangement.json` у каждой ноты есть `string`, `fret`,
`locked` и полный список допустимых позиций `legal_positions` — этого
достаточно, чтобы нарисовать интерактивный гриф следующим этапом. Сам JSON —
промежуточный формат: **это пока не готовая табулатура и не PDF**;
полифоническая аранжировка, ASCII-tab и экспорт в ноты — отдельные будущие
этапы. В API есть зеркальный эндпоинт `POST /arrange/guitar` (MIDI-файл + те
же параметры, структурированные ошибки `{"code", "message", "details"}`).



Полный список опций — `--help`.

### Нотный лист

`--format sheets` (или кнопка «Скачать → Нотный лист» в веб-UI) создаёт:

```
score/
├── score.mid                       расшифровка (квантованный MIDI)
├── score.musicxml                  партитура MusicXML
├── full_score.pdf                  все инструменты на одной системе
├── 01_electric_guitar.pdf          PDF по инструменту…
├── 01_electric_guitar_tab.pdf      …и табулатура для ладовых
├── 02_electric_bass.pdf
└── 03_drum_kit.pdf
```

Для нот нужен установленный **[MuseScore 4+](https://musescore.org/en/download)**:
стандартные пути установки находятся автоматически, иначе задайте
`MUSCRIPTOR_MUSESCORE`. Лучше всего работает музыка с устойчивым темпом —
тогда ноты квантуются по сетке; рубато-записи читаются хуже.

## Windows-нюансы

- **GPU**: PyPI-сборка PyTorch для Windows — CPU-only, поэтому в этом форке
  torch на Windows привязан к индексу `cu128` (обязательно для RTX 50xx,
  подходит и старым картам NVIDIA). `uv sync` делает это сам.
- **Кодировка консоли**: при запуске с перенаправлением вывода ставьте
  `PYTHONUTF8=1` (`start.bat` уже делает это) — иначе отладочный вывод может
  упасть на не-ASCII символах в cp1251.
- **MuseScore**: определяется автоматически (Program Files, пользовательская
  установка); нестандартный путь — через `MUSCRIPTOR_MUSESCORE`.
- **FluidSynth** (экспорт WAV): бинарник должен быть в PATH; официальный
  Windows-билд, распакованный в `tools\fluidsynth` (в `.gitignore`), — удобный
  вариант, `start.bat` подключает его сам.
- **ffmpeg** (удаление ведущего вокала): мастер `install.bat` предложит
  установить через winget (`Gyan.FFmpeg`); `start.bat` предупредит, если его
  нет в PATH.

## Разработка

```bash
uv sync
cd web && pnpm install && pnpm run build   # только если меняете фронтенд
```

Для горячего релоада фронтенда: `pnpm dev` в `web/` и
`uv run muscriptor serve --port 8222` рядом; открывать http://localhost:5173/.

## Баги и предложения

Используйте [шаблоны Issues](https://github.com/leadpioneer/muscriptor-plus/issues/new/choose)
этого репозитория.

## Лицензия

Код — под лицензией [MIT](LICENSE) (© Kyutai × Mirelo, © LeadPioneer).
Веса модели на [HuggingFace](https://huggingface.co/MuScriptor) — под
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)
(некоммерческое использование). Звуковой шрифт MuseScore General,
используемый для проигрывания, распространяется под своей лицензией (MIT).

## Цитирование

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

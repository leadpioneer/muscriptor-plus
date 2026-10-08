<p align="center">
  <img src="web/logo_muscriptor_final.png" alt="MuScriptor Plus" width="300">
</p>

<h1 align="center">MuScriptor Plus</h1>

<p align="center">
  <a href="README.en.md">🇬🇧 English version</a> ·
  <a href="QUICKSTART.md">Быстрый старт</a> ·
  <a href="docs/README.md">Документация</a> ·
  <a href="https://github.com/leadpioneer/muscriptor-plus/issues/new/choose">Сообщить о баге</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/OS-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey" alt="OS">
  <img src="https://img.shields.io/badge/GPU-CUDA%20%7C%20Metal-76b900" alt="GPU">
  <a href="https://github.com/leadpioneer/muscriptor-plus/actions/workflows/ci.yml"><img src="https://github.com/leadpioneer/muscriptor-plus/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
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
| Гитарная аппликатура | нет | **аранжировщик MIDI → струны/лады**: лаборатория аппликатуры в веб-UI, PDF/MusicXML/ASCII-tab с сохранённой аппликатурой (см. ниже) |
| Ведущий вокал | портит расшифровку | **opt-in удаление вокала перед транскрипцией**: стемы «оригинал/инструментал» и переключатель в плеере (см. ниже) |
| Windows | MuseScore/FluidSynth руками | **автоопределение MuseScore, GPU-сборка PyTorch (cu128), UTF-8** |
| Установка | вручную | **мастер `install.bat` (англ. копия — `install_en.bat`) + `start.bat`** |

Основа оригинала не тронута: точность модели, CLI, Python API, форматы.

## Документация

Подробные руководства — в каталоге [`docs/`](docs/README.md):

- [Установка](docs/installation.md) — мастер Windows, ручная установка на всех ОС, модели, кэши, Intel Mac;
- [CLI](docs/cli.md) — все команды и опции с значениями по умолчанию;
- [Веб-интерфейс](docs/web-ui.md) — экран загрузки, плеер, скачивания, лаборатория аппликатуры;
- [HTTP API](docs/api.md) — эндпоинты, SSE-протокол, коды ошибок, конкурентность;
- [Гитарный аранжировщик](docs/guitar-arranger.md) — алгоритм, фиксации, JSON schema v3;
- [Архитектура и разработка](docs/architecture.md) — внутреннее устройство, тесты, сборка, Docker;
- [Диагностика](docs/troubleshooting.md) — решение типичных проблем.

## Быстрый старт (Windows)

Понадобятся: Windows 10/11, [Git](https://git-scm.com/download/win), аккаунт
[HuggingFace](https://huggingface.co) с принятой лицензией модели (см. ниже).

```bat
git clone https://github.com/leadpioneer/muscriptor-plus
cd muscriptor-plus
install.bat   :: мастер установки: оценка железа (CPU/GPU), uv, Node, зависимости, веб-UI, HF-доступ к весам, выбор модели
install_en.bat :: тот же мастер с интерфейсом на английском
start.bat     :: запуск сервера + открытие веб-интерфейса на http://127.0.0.1:8222
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
- На Intel Mac нужен Python 3.10–3.12 (torch там привязан к 2.2.2) и
  недоступно удаление ведущего вокала — см.
  [docs/installation.md](docs/installation.md#особые-случаи-intel-mac-и-apple-silicon).

### Память GPU: выгрузка модели

Загруженная модель держит свои ~8–12 ГБ в VRAM, даже когда сервер простаивает.
Освободить память можно двумя способами:

- **Вручную** — кнопка «выгрузить» рядом с выбором модели в шапке.
- **Автоматически** — после 5 минут простоя (по умолчанию; меняется опцией
  `--idle-unload <минуты>` у `serve`, `0` — выключить).

Следующий запрос (транскрипция) прозрачно перезагружает ту же модель из
локального кэша за несколько секунд — без сети; переключение на модель,
которой ещё нет в кэше, сначала скачает её веса. Разделение вокала тоже
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
(не аудио)** и для одной дорожки подбирает струну и лад для каждой ноты.
Высоты нот, начала и длительности **не изменяются** — октавных переносов и
транспозиции нет; «сомнительные» ноты не удаляются. Оптимизация глобальная:
фразы (разделённые полной тишиной ≥ 1 бита) решаются динамическим
программированием целиком, поэтому ранние ноты могут быть сдвинуты выше по
грифу, чтобы избежать резкого скачка в конце фразы. Результат — оптимум
относительно текущей функции стоимости (переходы по ладам/струнам, штраф за
резкую смену позиции, слабый штраф за высокие лады), а не «идеальная
аппликатура».

Нумерация струн: **1 — самая высокая** (стандартный строй: E4, B3, G3, D3,
A2, E2). Дорожка выбирается автоматически, если недрамовая нотоносная
дорожка одна; иначе модуль перечислит кандидатов.

```bash
uv run muscriptor arrange-guitar song.mid --list-tracks   # что внутри файла
uv run muscriptor arrange-guitar song.mid --track 2 --output arrangement.json
uv run muscriptor arrange-guitar song.mid --track 2 \
    --tuning standard --max-fret 24 --phrase-gap-beats 1.0
```

Ручные фиксации для редактора в веб-интерфейсе (`--overrides overrides.json`):

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
всю фразу — в том числе весь аккорд, в котором нота звучит. Начиная с
**schema v3** состояние солвера — полная аппликатура: у каждой ноты есть
`string`, `fret`, **`hand_position`** (лад, напротив которого стоит
указательный палец), **`finger`** (0 — открытая струна, 1–4 — пальцы;
`null`, если аннотация пальцев получилась неполной),
`locked` и списки `legal_positions` (string/fret) и `legal_fingerings`
(полные состояния). Стоимость моделирует кисть, а не лады нот: переходы
между ладами в одной позиции бесплатны, смена позиции кисти — заметна и
видна в метриках `position_change_count` / `total_hand_position_travel`;
открытая струна и пауза внутри фразы делают перенос дешевле. Открытая струна
бесплатна, пока кисть у порожка (позиция ≤ 3) или когда нота звучит
одновременно с другими — аккорды, накладывающиеся голоса и залоченные ноты
всегда освобождены. Одиночная открытая струна в высокой позиции считается
ошибкой регистра: солвер предпочтёт зажатую ноту в той же позиции (штраф
меньше переезда кисти «туда-обратно», поэтому вынужденно открытые ноты —
например, низкое E — не заставляют руку ездить). `--explain`
печатает в stderr сводку по полифонии и по фразам с аккордами.

Полифония с 1 по 6 одновременно начинающихся нот — нормальный вход: chord
solver сохраняет **все** ноты (по одной на струну, без транспозиций, сокращений
длительностей и арпеджио). Оптимизация идёт глобально по всей фразе —
солвер может заранее поднять позицию ради следующего аккорда. События из
семи и более нот дают предметную ошибку, а не удаление нот. Асинхронные
перекрытия (звенящий бас) — это не пауза: они сохраняются как есть и
показываются в `polyphony_analysis` документа; strict voice separation —
задача будущего этапа.

Явное извлечение одной линии (`--melody top` / `--melody bottom`) остаётся
opt-in режимом: верхняя/нижняя нота выбирается только среди нот с одинаковым
временем начала — это не разделение мелодии и баса на голоса.

Из готового JSON дальше:
- `uv run muscriptor guitar-tab arrangement.json --midi song.mid` — ASCII-табулатура
  и обратный MIDI (высоты, тайминги и скорости — без изменений; MIDI не хранит
  выбранные струны/лады);
- `uv run muscriptor guitar-musicxml arrangement.json` — **MusicXML, сохраняющий
  аппликатуру**: каждая нота несёт `<technical><string>/<fret>`, перекрытия
  длительностей раскладываются по голосам, durations не сокращаются (для
  неквантованной записи engraved shape ноты — ближайший dyadic `<type>`, сам
  `<duration>` остаётся исходным, а неполные такты добиваются паузами);
- скормите arrangement.json эндпоинту `POST /arrange/guitar/pdf` — PDF
  (ноты + табулатура) через MuseScore ровно с выбранными string/fret, включая
  ваши lock'и. Обычный MIDI для этого не годится: авто-таб MuseScore подобрал
  бы свои позиции.

В веб-интерфейсе всё это собрано в «Гитарной лаборатории аппликатуры» (кнопка
«Исправить аппликатуру» — и на главном экране, и после транскрипции): SVG-гриф
с допустимыми позициями и lock'ами (весь аккорд на экране, выделенная нота,
барре), навигация стрелками по событиям и нотам внутри аккорда,
прослушивание результата (условные 120 BPM), скачивание arrangement.json /
arrangement.mid / ASCII-таба / MusicXML и PDF с сохранённой аппликатурой.

В API есть зеркальный эндпоинт `POST /arrange/guitar` (MIDI-файл + те
же параметры, структурированные ошибки `{"code", "message", "details"}`),
а также `POST /arrange/guitar/midi`, `/tab`, `/musicxml` и `/pdf` — все они
принимают подтверждённый arrangement.json (schema v3; конвертеры понимают и
старые v2-документы).

Для frontend-тестов требуется Node 22.19+ (закреплён в `web/package.json`
и `.nvmrc`).



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
  подходит и старым картам NVIDIA). `uv sync` делает это сам. На машине
  **без NVIDIA GPU** мастер `install.bat` ставит CPU-вариант
  (`uv sync --no-sources`) и записывает `device.txt` — `start.bat` тогда
  запускает сервер с `uv run --no-sync`, чтобы окружение не перекатилось
  обратно на cu128.
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
uv run pytest                              # герметичные тесты (интеграционные — по MUSCRIPTOR_TEST_*)
cd web && pnpm test                        # фронтенд-тесты (Node 22.19+)
```

CI (GitHub Actions, `.github/workflows/ci.yml`) на каждый push/PR гоняет
ruff, pytest (включая проверку ссылок в документации), vitest и сборку
фронтенда.

Для горячего релоада фронтенда: `pnpm dev` в `web/` и
`uv run muscriptor serve --port 8222` рядом; открывать http://localhost:5173/.
Vite проксирует все эндпоинты на `BACKEND_URL` (по умолчанию
`http://127.0.0.1:8222`); `pnpm run dev:proxy` подключает публичный
демо-бэкенд. Подробнее — [docs/architecture.md](docs/architecture.md#разработка).

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

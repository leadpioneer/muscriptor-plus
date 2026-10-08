# Архитектура и разработка

Документ для тех, кто читает или меняет код: как устроен пайплайн, из чего
состоит репозиторий, как гонять тесты и как проект собирается и
разворачивается.

## Пайплайн: аудио → MIDI

```
аудиофайл
  → load_audio            моно, 16 кГц, float32 ([1, T])
  → нарезка на чанки      по 5 секунд (сегмент обучения; последний — с паддингом)
  → conditioning          log-mel (512 бин), инструментальная группа, dataset
  → LMModel.generate      по одному токену на чанк за шаг; EOS завершает чанк
  → OpenNoteTracker       tie-пролог, окно next_seek_time, повторные удары, барабаны
  → NoteStartEvent / NoteEndEvent / ProgressEvent
  → validate + trim       фикс перекрытий, минимальная длительность
  → beat grid             beat_this → темп/размер/сдвиг онсетов
  → notes_to_midi         mido: темп, размер, тактовый сдвиг, квантование (опция)
```

### Модель

- `muscriptor/models/lm.py` — decoder-only трансформер `LMModel` с
  `ScaledEmbedding`, `TorchAutocast` и `generate()` (жадное/сэмплирование/beam
  search, `early_stop_on_token`, маскирование запрещённых токенов).
- `muscriptor/modules/` — conditioning (`MelSpectrogramConditioner`,
  `ClassConditioner`), стриминговый трансформер, mel-фронтенд.
- Варианты (`muscriptor/transcription_model.py`): `small` — 12 голов / 14
  слоёв / dim 768 / словарь 1393; `medium` — 16 / 24 / 1024 / 1395;
  `large` — 24 / 48 / 1536 / 1395.
- Аудио всегда 16 кГц, чанк 5,0 с, frame rate токенизатора — 100 тиков/с,
  бюджет генерации — 2000 токенов на чанк.
- `--dtype`: fp32 по умолчанию, fp16 на MPS (веса), fp16-autocast на CUDA.
  Conditioners остаются в fp32 (тихие пассажи в fp16 недопредставляются), а
  выход кастится на границе трансформера.
- **Prelude forcing** (по умолчанию): незакрытые к концу чанка ноты
  кодируются как `(program, pitch)…tie` и подаются промптом в следующий чанк —
  модель не может «переиграть» состав инструментов на стыке. Требует
  последовательной генерации (батч 1). `--no-prelude-forcing
  --batch-size 4` — обмен качества на скорость.
- `ProgressEvent(completed, total)` — грубые якоря прогресса (один в начале,
  один на чанк); UI сглаживает их и оценивает ETA.

### События

`muscriptor/events.py`:

- `OpenNoteTracker` — единый автомат декодирования: tie-пролог (не
  заявленные ноты закрываются на границе чанка), «сломанный» чанк (нет
  `tie` — закрыть всё и пропустить остаток), окно `next_seek_time` (события
  за окном отбрасываются), повторные удары (end + start на том же тике),
  барабаны (мгновенная пара start/end минимальной длительности).
- `decode_model_tokens` превращает действия автомата в
  `NoteStartEvent`/`NoteEndEvent` со сквозной нумерацией `index`.
- `transcribe()` гарантирует: события чанка N идут до событий чанка N+1;
  каждый `start` получает ровно один парный `end`.

### Темп и сетка (`muscriptor/utils/beats.py`)

- Детектор — [beat_this](https://github.com/CPJKU/beat_this), чекпойнт
  `final0` (у `small0` бывают лишние бейты до первого даунбита).
- Ограничения: минимум 1 с аудио и 8 бейтов; допустимый остаток от
  постоянного темпа — 5 % длительности доли; размер пишется, только если
  ≥ 90 % тактов согласны по числу долей (иначе `beats_per_bar = null`).
- `onset_delay` — измеренная устойчивая задержка онсетов относительно
  выбранной сетки (по фазовым векторам, не более 40 мс); из MIDI она
  вычитается, а UI получает число, чтобы сдвинуть уже нарисованные ноты.
- `bar_offset()` добавляет целые такты, чтобы бар 1 начинался с реального
  даунбита; сдвиг записывается маркером `muscriptor:bar_offset=` в MIDI —
  `/auralize` и auralization читают его обратно.
- Без темпа пишется заглушка 120 BPM без размера (`PLACEHOLDER_GRID`).
- `quantize=True` (только для нот) притягивает онсеты/офсеты к
  `beat_subdivision`, не позволяя ноте исчезнуть (минимум — один шаг).

### Удаление ведущего вокала (`muscriptor/preprocessing/`)

- `VocalRemovalPreprocessor` — обёртка над
  [`audio-separator`](https://github.com/karaokenerds/python-audio-separator)
  с моделью `vocals_mel_band_roformer.ckpt` (Kimberley Jensen, Mel-Band-RoFormer).
  Инструментал получается вычитанием вокала из микса.
- Импорт `audio_separator` ленивый: без зависимости пакет импортируется, а
  ошибка появляется только при включении функции (Intel Mac).
- Проверка `ffmpeg` до старта; веса кэшируются в per-OS каталоге
  (`default_model_cache_dir()`); после каждого прогона модель
  удаляется и вызывается `gc.collect()` + `torch.cuda.empty_cache()` —
  разделение и транскрипция никогда не держат VRAM одновременно.
- `PreprocessError` имеет человекочитаемые сообщения; тихих откатов на
  оригинал нет.
- `StemStore` — реестр `run_id → стемы` с TTL 1 час и лимитом 8 прогонов;
  `sweep_orphans()` подчищает директории `muscriptor-stems-*`, оставшиеся от
  прерванных запросов.

### MIDI, ноты, auralization

- `muscriptor/utils/midi.py` + `tokenizer/notes.py`: `Note` → `NoteEvent` →
  mido. Валидация (фикс отрицательных длительностей) и обрезка перекрытий —
  те же, что у «эталонного» декодера, поэтому байты не дрейфуют.
- `muscriptor/utils/sheets.py`: все операции с MuseScore — сабпроцессы
  (`-M import.xml`, `--score-parts-pdf`). Проверяются **файлы**, а не код
  возврата: MuseScore умеет выходить с 0, ничего не записав. Табулатуры
  получаются правкой копии партитуры (`convert_to_tab_staves`), а не вторым
  импортом. Версия ниже 4 отклоняется.
- `muscriptor/utils/auralization.py`: fluidsynth (`-ni -F -r 44100`),
  RMS-нормализация синтеза под оригинал, вычитание `bar_offset`.

## Структура пакета

| Модуль | Ответственность |
|---|---|
| `main.py` | CLI (typer): `transcribe`, `serve`, `list-instruments`, `arrange-guitar`, `guitar-tab`, `guitar-musicxml` |
| `server.py` | FastAPI: `/transcribe` (SSE), `/transcribe/midi`, `/sheets`, `/auralize`, `/arrange/guitar*`, `/stems`, `/model`, `/instruments`, `/health`, `/soundfonts/…`, статика |
| `transcription_model.py` | загрузка весов/конфигов, `transcribe`, `transcribe_and_postprocess`, `detect_beat_grid_for`, `events_to_midi_bytes` |
| `events.py` | событийная модель и декодер токенов |
| `accelerator.py` | `is_available`/`current_accelerator`/`synchronize` (torch.accelerator ≥ 2.6, иначе CUDA/MPS) |
| `tokenizer/mt3.py` | MT3-токенизатор, карта групп инструментов, резолвинг имён, запрещённые токены |
| `tokenizer/notes.py` | словарь событий, конвертация нот/MIDI |
| `utils/download.py` | `hf://`, `http(s)://` и локальные веса + единые ошибки доступа |
| `utils/beats.py` | детекция темпа, сетка, задержка онсетов, квантование |
| `guitar_arrangement/` | полностью независимый гитарный аранжировщик (см. [guitar-arranger.md](guitar-arranger.md)) |
| `preprocessing/` | удаление вокала и `StemStore` |
| `web_dist/` | собранный фронтенд (не в git; попадает в wheel) |

## Сервер

`create_app(...)` собирает приложение без глобального состояния на импорте,
поэтому тесты поднимают его с фейковой моделью.

- **Блокировка**: один `threading.Lock` на транскрипцию и разделение. Логика
  преемпции — в `acquire_transcribe_lock`: чужой клиент получает 503 сразу,
  свой (по `X-Client-Id`) отменяет предыдущий прогон и ждёт до 5 секунд.
- **Unload**: `model_state` — словарь (`model`, `size`, `status`, `error`);
  фоновый поток раз в ≤ 30 с выгружает модель после `idle_unload_s` простоя.
- **SSE**: `StreamingResponse` + генератор; терминальные сбои (ошибка
  препроцессинга, провал детекции темпа при `detect_tempo=true`) отдаются
  событием `error`, поэтому поток всегда заканчивается внятно;
  `release_lock` вызывается из `finally` генератора и из `BackgroundTask`
  (на случай отключения клиента до первой итерации) ровно один раз
  (`_make_release_once`).
- **Ограничения**: `/transcribe/midi` — 15 минут аудио; `/sheets` и
  `/arrange/guitar/pdf` требуют MuseScore; всё остальное — без аутентификации
  (см. [api.md](api.md#безопасность)).

## Веб-интерфейс

- React 19 + TypeScript + Vite + Tailwind 4; сборка — `tsc --noEmit && vite
  build` в `muscriptor/web_dist`.
- Аудио: `tone` (планирование нот, шины громкости) + `spessasynth_lib`
  (звуковой шрифт `.sf3` с `/soundfonts/…`) и оригинальный файл через Web
  Audio; piano roll — собственный canvas-модуль `pianoroll.ts`.
- SSE-клиент (`sse.ts`) разбирает кадры `data:` вручную, умеет автоповтор при
  503 каждые 5 секунд и передаёт `X-Client-Id` вкладки.
- i18n — словари `en.ts` / `ru.ts`, автоопределение языка браузера,
  сохранение выбора в `localStorage`.
- Тесты — Vitest + Testing Library (`web/src/**/*.test.tsx`), в частности
  полный тест диалога гитарной лаборатории.

## Разработка

```bash
uv sync                         # зависимости Python (+ dev-группа)
pre-commit install              # ruff + uv-lock
uv run pytest                   # быстрые герметичные тесты
cd web && pnpm install && pnpm test && pnpm run build
```

- Юнит-тесты не требуют весов и сети: сервер тестируется с фейковой моделью,
  гитарный модуль — на синтетических MIDI.
- Интеграционные тесты (маркер `integration`, `tests/test_integration.py`)
  включаются переменными окружения: `MUSCRIPTOR_TEST_WEIGHTS` — путь к
  `.safetensors` (иначе ищется `muscriptor_weights_*.safetensors` в корне),
  `MUSCRIPTOR_TEST_SONG` — аудио для сквозного прогона. Без них тесты
  скипаются, а не падают; `tests/test_guitar_musicxml.py` и
  `test_utils_musescore.py` также требуют MuseScore 4.
- `tests/test_docs_links.py` проверяет все относительные ссылки и якоря
  заголовков в Markdown — битая ссылка валит CI.
- `tests/test_server.py` использует `create_autospec(TranscriptionModel)`,
  поэтому подпись `create_app` обязана совпадать с реальными вызовами.
- CI (`.github/workflows/ci.yml`): `ruff check`/`format --check`, `pytest`
  (включая тест ссылок), `pnpm test` и `pnpm run build`.

### Горячий релоад фронтенда

```bash
uv run muscriptor serve --port 8222      # бэкенд
cd web && pnpm dev                       # фронтенд на http://localhost:5173
```

Vite проксирует на `BACKEND_URL` (по умолчанию `http://127.0.0.1:8222`)
все эндпоинты приложения: `/transcribe`, `/instruments`, `/model`, `/stems`,
`/auralize`, `/sheets`, `/arrange`, `/health`, `/soundfonts` (полный список —
в `web/vite.config.ts`). Скрипт `pnpm run dev:proxy` ходит на публичный
демо-бэкенд.

## Сборка и публикация

- `pyproject.toml` (hatchling): артефакт `muscriptor/web_dist` попадает в
  sdist/wheel, поэтому `uvx muscriptor serve` отдаёт интерфейс. Версия пакета
  — `0.3.0`.
- Release-workflow `.github/workflows/pypi.yml`: на создание GitHub Release
  собирает фронтенд, `uv build` и публикует в PyPI через Trusted Publishing.
- Для публикации без аналитики ничего задавать не нужно: без
  `VITE_GA_MEASUREMENT_ID` в бандл не попадает GA-код.

## Развёртывание сервера

- `Dockerfile` — двухстадийный: Node собирает фронтенд; Python-образ ставит
  зависимости, MuseScore AppImage (`/opt/musescore/AppRun`,
  `MUSCRIPTOR_MUSESCORE`), FluidSynth и заранее кэширует оба звуковых шрифта
  (.sf2 для `/auralize`, .sf3 для браузера). Точка входа —
  `uv run muscriptor serve --host 0.0.0.0`.
- `swarm.yml` — Docker Swarm для демо `muscriptor.kyutai.org`: Traefik с
  Let's Encrypt (HTTP→HTTPS, read timeout 30 м), одна реплика backend с
  `HF_TOKEN` из окружения и GPU-резервированием, кэш HF на volume.
- `deploy.sh` — сборка и `docker stack deploy` по SSH; требует
  `HF_TOKEN` в окружении.
- `.github/workflows/deploy.yml` — ручной workflow: кладёт SSH-ключ и
  registry-креды из секретов и запускает `deploy.sh`.

## Производительность и логи

- Прогресс и тайминги пишутся в stderr: `[muscriptor] load audio: …s`,
  `generate total: …s`, `transcribe total: …s`. Логгер сервера (INFO)
  сообщает о детекции темпа, выгрузке модели и завершении разделения.
- Время транскрипции примерно пропорционально длительности: ~1 чанк = 5 с
  аудио; GPU обрабатывает быстрее реального времени, CPU — заметно медленнее.
- VRAM: модель занимает память постоянно, пока не выгружена (вручную,
  по простою или при смене модели); разделение вокала отпускает память сразу
  после прогона.

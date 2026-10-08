# Документация MuScriptor Plus

**MuScriptor Plus** — расширенный форк открытой модели мультиинструментальной
транскрипции [MuScriptor](https://github.com/muscriptor/muscriptor) от
[Kyutai](https://kyutai.org) и [Mirelo](https://www.mirelo.ai): на входе
аудиозапись, на выходе — MIDI и нотный лист по каждому инструменту.
Этот форк добавляет русский интерфейс, раздельную громкость, переключение
модели на ходу и — главное — символьный гитарный аранжировщик аппликатуры.

Если вы впервые в проекте, начните с [быстрого старта](../QUICKSTART.md) или
раздела [Установка](installation.md); все подробности — в документах ниже.

## Карта документации

| Документ | О чём |
|---|---|
| [installation.md](installation.md) | Установка на Windows (мастер `install.bat`), ручная установка на всех ОС, HuggingFace, модели, кэши, сопутствующие программы |
| [cli.md](cli.md) | Полный справочник командной строки: `transcribe`, `serve`, `arrange-guitar`, `guitar-tab`, `guitar-musicxml`, `list-instruments` — все опции и значения по умолчанию |
| [web-ui.md](web-ui.md) | Руководство по веб-интерфейсу: загрузка, подсказки инструментов, удаление вокала, плеер, прогресс, скачивания, переключатель модели |
| [api.md](api.md) | HTTP API: все эндпоинты, SSE-протокол, коды ошибок, ограничения, конкурентность |
| [guitar-arranger.md](guitar-arranger.md) | Гитарный аранжировщик: алгоритм, функция стоимости, фиксации (locks), JSON-схема v3, экспорт MIDI/TAB/MusicXML/PDF |
| [architecture.md](architecture.md) | Как всё устроено изнутри, структура репозитория, разработка, тесты, сборка и развёртывание |
| [troubleshooting.md](troubleshooting.md) | Типичные проблемы и их решение |

## Что умеет проект — коротко

- **Транскрипция аудио**: MP3, WAV, FLAC, OGG, M4A, AIFF, Opus → MIDI
  (`midi`, `json`, `jsonl`) или ноты (`sheets`).
- **Нотный лист** через MuseScore 4+: PDF полной партитуры, PDF по каждому
  инструменту, табулатуры для гитары и баса, MusicXML.
- **Mid-транскрипция в плеере**: интерактивный piano roll, оригинал и MIDI
  раздельно, громкость и mute/solo по каждому инструменту.
- **Удаление ведущего вокала** (opt-in): стемы «вокал/инструментал»,
  переключатель прослушивания.
- **Любой MIDI в ноты**: кнопка «сделать ноты из готового MIDI-файла» на
  экране загрузки.
- **Гитарная лаборатория аппликатуры**: MIDI → струны/лады с глобальной
  оптимизацией, ручными фиксациями и выгрузкой arrangement.json / MIDI /
  ASCII-таба / MusicXML / PDF с сохранённой аппликатурой.
- **Переключение модели** small/medium/large прямо в веб-интерфейсе и
  выгрузка модели из видеопамяти (вручную или по простою).
- **Русский и английский интерфейс.**

## Требования — сводная таблица

| Компонент | Обязателен? | Где описан |
|---|---|---|
| Python 3.10+ и [uv](https://docs.astral.sh/uv/) | да (ставится мастером) | [installation.md](installation.md) |
| Аккаунт HuggingFace + принятая лицензия весов | да | [installation.md](installation.md#доступ-к-весам-huggingface) |
| Node.js 22.19+ и pnpm | только для сборки веб-интерфейса | [installation.md](installation.md#ручная-установка) |
| MuseScore 4+ | для PDF-нотов и `/sheets` | [installation.md](installation.md#сопутствующие-программы) |
| FluidSynth | для экспорта WAV (`/auralize`, `--auralize`) | [installation.md](installation.md#сопутствующие-программы) |
| ffmpeg | для удаления ведущего вокала | [installation.md](installation.md#сопутствующие-программы) |
| NVIDIA GPU / Apple Silicon | необязательно — есть CPU-режим | [installation.md](installation.md#устройство-и-pytorch) |

## Структура репозитория

```
muscriptor/                 Python-пакет
├── main.py                 CLI (typer): transcribe, serve, arrange-guitar, …
├── server.py               FastAPI-сервер (SSE, /sheets, /auralize, /model, /arrange/…)
├── transcription_model.py  TranscriptionModel: загрузка весов, генерация, MIDI
├── events.py               NoteStart/NoteEnd/Progress, декодер токенов
├── accelerator.py          выбор устройства (CUDA / MPS / CPU)
├── models/, modules/       архитектура трансформера
├── tokenizer/              MT3-токенизатор и инструменты
├── utils/                  аудио, MIDI, ноты, темп, скачивание, auralization
├── preprocessing/          удаление ведущего вокала (audio-separator)
└── guitar_arrangement/     гитарный аранжировщик (чистый Python, без torch)

web/                        React + Vite + Tailwind фронтенд
tests/                      pytest- и vitest-тесты
docs/                       эта документация
install.bat, install_en.bat мастера установки для Windows
start.bat                   запуск сервера + браузера
Dockerfile, swarm.yml       контейнер и развёртывание на сервере
```

## Версии и лицензии

- Код: MIT (© Kyutai × Mirelo, © LeadPioneer), см. [LICENSE](../LICENSE).
- Веса модели на [HuggingFace](https://huggingface.co/MuScriptor):
  CC BY-NC 4.0, только некоммерческое использование.
- Звуковой шрифт MuseScore General: собственная лицензия (MIT).
- Python: 3.10+ (на Intel Mac — 3.10–3.12), Node для фронтенда: 22.19+.

## Ссылки

- Основной README: [README.md](../README.md) (рус.) · [README.en.md](../README.en.md) (англ.)
- Быстрый старт: [QUICKSTART.md](../QUICKSTART.md)
- Статья о модели: [arXiv:2607.08168](https://arxiv.org/abs/2607.08168)
- Апстрим: [github.com/muscriptor/muscriptor](https://github.com/muscriptor/muscriptor)
- Проблемы и предложения: [Issues этого форка](https://github.com/leadpioneer/muscriptor-plus/issues/new/choose)

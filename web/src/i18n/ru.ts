/** Russian UI strings. Missing keys fall back to English (see i18n/index). */
import type { Dict } from "./en";

export const RU: Dict = {
  // Header / shell
  tagline: "Музыка в MIDI и ноты",

  // Welcome screen
  welcome_intro:
    "MuScriptor Plus — это форк MuScriptor, лучшей на сегодня открытой модели мультиинструментальной транскрипции: русскоязычный интерфейс, раздельная громкость по инструментам и переключение модели на ходу. Дайте ей запись — поп, классику, метал, джаз, что угодно — и она распознает ноты, сыгранные каждым инструментом, в MIDI и нотный лист, который можно скачать или исследовать в интерактивном плеере.",
  drop_audio_here: "Перетащите сюда",
  drop_audio_here_strong: "аудио-файл",
  drop_audio_here_tail: ", или",
  select_audio: "Выбрать аудио-файл",
  try_example: "или попробуйте пример трека",
  loading_example: "Загружаем пример…",
  choose_different: "Выбрать другой файл",
  server_unavailable: "недоступен",
  server_down_full:
    "Сервер MuScriptor временно недоступен. Попробуйте позже.",
  transcribe: "Расшифровать",
  transcribing: "Расшифровываем…",
  servers_busy: "Серверы заняты, повторяем…",
  servers_busy_in: "Серверы заняты, повтор через {n} с",
  drop_anywhere: "Просто бросьте файл",
  cancel: "Отмена",
  alert_example_failed: "Не удалось загрузить файл примера: {message}",

  // Conditioning panel
  cond_title: "Какие инструменты есть в этом треке?",
  cond_hint:
    "Необязательно. Оставьте пустым — модель распознает всё сама; если перечислить инструменты здесь, все остальные будут исключены.",
  cond_clear: "Очистить",
  cond_placeholder: "Добавьте инструмент…",
  cond_remove: "Убрать {name}",

  // Vocal removal (opt-in preprocessing)
  rv_title: "Удалить ведущий вокал перед транскрипцией",
  rv_hint: "Может улучшить распознавание инструментов и табулатур.",
  rv_caveat:
    "На отдельных композициях обработка может изменить тембр инструментов.",

  // Preprocessing stages (shown while transcribing with vocal removal on)
  stage_prepare: "Подготовка аудио…",
  stage_vocal_removal: "Удаление ведущего вокала…",
  stage_instrumental: "Подготовка инструментала…",
  stage_transcription: "Транскрипция инструментала…",
  stage_midi: "Создание MIDI…",

  // Result / stem downloads
  result_from_instrumental:
    "Транскрипция выполнена по инструменталу (ведущий вокал удалён).",
  download_stem_vocals: "Вокал (WAV)",
  download_stem_instrumental: "Инструментал (WAV)",
  alert_stem_failed: "Не удалось скачать стем: {message}",

  // Preview source (after a vocal-removal run)
  source_title: "Что слышно в предпросмотре",
  source_original: "Оригинал",
  source_instrumental: "Инструментал",
  source_vocals: "Вокал",

  // Controls bar
  play: "Играть",
  pause: "Пауза",
  follow_playhead: "Следовать за курсором",
  follow_off_title: "Перестать следовать за курсором",
  follow_on_title: "Прокручивать вместе с курсором",
  volume_original: "Оригинал",
  volume_midi: "MIDI",
  volume_master: "Общая",
  stereo: "Стерео",

  // Instrument list
  instruments: "Инструменты",
  model_label: "Модель",
  model_loading: "загружается…",
  model_error: "ошибка загрузки",
  model_retry: "повторить",
  model_unload: "выгрузить",
  model_unload_title:
    "Освободить видеопамять (модель перезагрузится из кэша по первому запросу)",
  model_unloaded: "выгружена",
  model_load: "загрузить",
  model_load_title: "Загрузить модель обратно в видеопамять",
  instruments_given_hint:
    "Указанные вами инструменты. Серые — не обнаружены в записи.",
  more_instruments: "Другие инструменты",
  more_instruments_hint:
    "Ещё инструменты, которые модель нашла в записи, даже если они не были указаны явно.",
  not_detected: "не обнаружен",
  help_aria: "Что это значит?",
  volume_title: "Громкость: {name}",
  solo_title: "Соло (заглушить остальные)",
  unsolo_title: "Отменить соло",
  mute_title: "Заглушить на MIDI-дорожке",
  unmute_title: "Вернуть на MIDI-дорожке",

  // Output bar
  download: "Скачать",
  download_midi: "Файл MIDI",
  download_wav_synth: "WAV — только расшифровка",
  download_wav_synth_title:
    "Только распознанные ноты, сыгранные саундфонтом (моно)",
  download_wav_mix: "WAV — стерео с оригиналом",
  download_wav_mix_title:
    "Оригинальное аудио (L) + распознанные ноты саундфонтом (R)",
  download_sheets: "Нотный лист",
  download_sheets_title:
    "Ноты: PDF по инструментам, табулатуры, MusicXML",
  synthesizing: "Синтезируем…",
  generating: "Генерируем…",
  transcribe_another: "Расшифровать другой файл",
  alert_wav_failed: "Не удалось создать аудио-файл: {message}",
  alert_sheets_failed: "Не удалось создать ноты: {message}",

  // Sheets dialog
  sheets_title: "Скачать ноты",
  sheets_not_quantized:
    "В этой записи не удалось найти устойчивый ритм, поэтому тактовые черты — догадка. Ноты могут читаться тяжело.",
  sheets_midi_file: "Файл MIDI",
  sheets_musicxml: "Партитура MusicXML",
  sheets_full_score: "Полная партитура — все инструменты",
  sheets_tablature: " — табулатура",
  sheets_download_all: "Скачать всё ({n} файлов, {size})",
  close: "Закрыть",

  // MIDI → sheets
  midi_sheets_idle: "или сделайте ноты из готового MIDI-файла",
  midi_sheets_busy: "Создаём ноты…",

  // Progress / feedback
  estimating: "оцениваем…",
  done_in: "готово через {time}",
  feedback_intro: "Нашли баг или есть идея? ",
  feedback_email: "Напишите нам",
  feedback_or: " или ",
  feedback_issue: "создайте issue на GitHub",

  // App dialogs
  confirm_discard: "Отбросить эту расшифровку и начать заново?",
  confirm_discard_dropped:
    "Отбросить эту расшифровку и начать заново с перетащенным файлом?",

  // Consent banner
  consent_text:
    "Мы используем cookie (Google Analytics), чтобы понимать, как пользуются демо: визиты страниц и анонимные события — например, длительность расшифрованного аудио и выбранные инструменты; само аудио никогда не передаётся. Подробнее — в политике конфиденциальности.",
  consent_accept: "Принять",
  consent_decline: "Отклонить",

  // Drop overlay
  drop_to_transcribe_intro: "Перетащите",
  drop_to_transcribe_strong: "аудио-файл",
  drop_to_transcribe_tail: "для расшифровки",

  // Footer
  footer_about_pre:
    "MuScriptor Plus — расширенный форк модели транскрипции MuScriptor: превращает исходное аудио в MIDI по инструментам. Модель обучена",
  footer_and: "и",

  // FAQ
  faq_title: "Частые вопросы",

  // Instrument display names (keys mirror the backend instrument ids)
  instr_acoustic_piano: "Фортепиано",
  instr_electric_piano: "Электропиано",
  instr_chromatic_percussion: "Клавишная перкуссия",
  instr_organ: "Орган",
  instr_acoustic_guitar: "Акустическая гитара",
  instr_clean_electric_guitar: "Чистая электрогитара",
  instr_distorted_electric_guitar: "Дисторшн-гитара",
  instr_acoustic_bass: "Аккустический бас",
  instr_electric_bass: "Бас-гитара",
  instr_violin: "Скрипка",
  instr_viola: "Альт",
  instr_cello: "Виолончель",
  instr_contrabass: "Контрабас",
  instr_orchestral_harp: "Арфа",
  instr_timpani: "Литавры",
  instr_string_ensemble: "Струнный ансамбль",
  instr_synth_strings: "Синтезаторные струнные",
  instr_voice: "Вокал",
  instr_orchestra_hit: "Оркестровый удар",
  instr_trumpet: "Труба",
  instr_trombone: "Тромбон",
  instr_tuba: "Туба",
  instr_french_horn: "Валторна",
  instr_brass_section: "Медная секция",
  instr_soprano_and_alto_sax: "Сопрано/альт-саксофон",
  instr_tenor_sax: "Тенор-саксофон",
  instr_baritone_sax: "Баритон-саксофон",
  instr_oboe: "Гобой",
  instr_english_horn: "Английский рожок",
  instr_bassoon: "Фагот",
  instr_clarinet: "Кларнет",
  instr_flutes: "Флейты",
  instr_synth_lead: "Синтезатор-лид",
  instr_synth_pad: "Синтезаторный пэд",
  instr_drums: "Ударные",

  // Guitar Arranger Lab
  guitar_open: "Исправить аппликатуру",
  guitar_title: "Гитарная лаборатория аппликатуры",
  guitar_open_midi: "Открыть MIDI",
  guitar_loading: "Считаю аппликатуру…",
  guitar_pick_track: "В этом MIDI несколько дорожек с нотами. Выберите одну:",
  guitar_track_option: "{name} — дорожка {track}, канал {channel} — нот: {n}",
  guitar_track_unnamed: "Дорожка без имени",
  guitar_phrase_option: "Фраза {n} · нот: {count}",
  guitar_string_fret: "стр.{s} лад {f}",
  guitar_finger_short: "п{n}",
  guitar_locked: "фикс.",
  guitar_midi_pitch: "MIDI-высота {pitch}",
  guitar_note_aria: "{note}: струна {s}, лад {f}",
  guitar_hand_position: "Позиция кисти: {n}",
  guitar_finger_label: "Палец: {n}",
  guitar_unlock: "Снять фиксацию",
  guitar_hint:
    "Все отмеченные позиции дают правильную высоту ноты. После фиксации соседние ноты будут пересчитаны для удобства всей фразы.",
  guitar_download: "Скачать arrangement.json",
  guitar_position_changes: "Смен позиции: {n}",
  guitar_hand_travel: "Переносы кисти: {n}",
  guitar_largest_shift: "Наибольший сдвиг: {n}",
  guitar_phrase_cost: "Стоимость фразы: {n}",
  guitar_error_line: "Ошибка аранжировки: {message}",
  guitar_no_source:
    "Загрузите MIDI-файл, чтобы посмотреть и поправить гитарную аппликатуру — расшифровка не нужна.",
  guitar_error_polyphonic_input:
    "В дорожке есть ноты, начинающиеся одновременно (тик {tick}, высоты {pitches}). Аранжировщик оптимизирует одну мелодическую линию — выберите монодорожку или сначала извлеките мелодию.",
  guitar_error_invalid_midi: "Файл не удалось прочитать как MIDI.",
  guitar_error_unplayable_note:
    "Высота {pitch} вне диапазона гитары в этой настройке ({low}–{high}).",
  guitar_error_track_not_found: "Среди дорожек нет подходящей с нотами.",
  guitar_error_invalid_overrides:
    "Фиксированная позиция противоречит исходному MIDI.",
  guitar_error_invalid_melody_policy:
    "Неизвестная политика извлечения мелодии.",
  guitar_take_top: "Взять верхний голос",
  guitar_take_bottom: "Взять нижний голос",
  guitar_melody_top: "верхний голос",
  guitar_melody_bottom: "нижний голос",
  guitar_melody_summary: "Мелодия: {policy} · отброшено нот: {n}",
  guitar_play: "Прослушать",
  guitar_pause: "Пауза",
  guitar_play_title:
    "Проигрывание на условных 120 BPM — в документе нет карты темпов.",
  guitar_download_midi: "Скачать arrangement.mid",
  guitar_tab_button: "Табулатура",
  guitar_tab_title: "Табулатура (сетка 16-х, черты каждые 4 доли)",
  guitar_download_tab: "Скачать таб (.txt)",
  guitar_pdf: "PDF (ноты + таб)",
  guitar_pdf_busy: "Генерирую PDF…",
  guitar_fretboard_title: "Гриф с выбранной нотой и её допустимыми позициями",
  guitar_fretboard_aria: "Гриф: {note} сейчас на струне {s}, лад {f}",
  guitar_aria_position:
    "{note}: струна {s}, лад {f}, позиция кисти {hp}, палец {fg}",
  guitar_aria_position_multi: "{note}: струна {s}, лад {f}, позиции кисти {hp}",
  guitar_fingering_combo: "кисть {hp} / палец {fg}",
};

/** FAQ pairs; answers support `[label](href)` links and `code` spans. */
export const FAQ_RU: { q: string; a: string }[] = [
  {
    q: "Что такое MuScriptor Plus?",
    a: "MuScriptor Plus — расширенный форк [MuScriptor](https://github.com/muscriptor/muscriptor), модели мультиинструментальной транскрипции, разработанной компаниями [Kyutai](https://kyutai.org/) и [Mirelo](https://mirelo.ai/): вы даёте ему запись, а он распознаёт ноты, сыгранные каждым инструментом, в MIDI и ноты. Форк добавляет русский интерфейс, раздельную громкость, переключение модели на ходу и исправления для Windows.",
  },
  {
    q: "Это бесплатно?",
    a: "Да. Приложение бесплатно, код — под лицензией MIT, а веса модели опубликованы на HuggingFace под CC BY-NC 4.0 (некоммерческое использование). Если хотите запустить локально, загляните в [репозиторий MuScriptor Plus на GitHub](https://github.com/leadpioneer/muscriptor-plus).",
  },
  {
    q: "Какие аудио-форматы можно загружать?",
    a: "MP3, WAV, FLAC, OGG, M4A, AIFF или Opus. Перетащите файл на страницу или выберите через проводник.",
  },
  {
    q: "Какие инструменты он умеет распознавать?",
    a: "Вокал, фортепиано, гитары, бас, струнные, духовые, ударные и многие другие. Для точности можно заранее подсказать, какие инструменты ожидать. Полный список — в выпадающем списке выбора инструментов. ",
  },
  {
    q: "Можно ли получить из песни нотный лист?",
    a: "Да. После расшифровки в меню скачивания доступны ноты в PDF — по инструментам или полной партитурой. Также скачивается MusicXML, если хотите редактировать в MuseScore, Sibelius или Guitar Pro.",
  },
  {
    q: "А гитарные табулатуры?",
    a: "Да. Для ладовых инструментов — гитары и баса — рядом со стандартной нотацией создаётся PDF с табулатурой. Скачайте его в меню нот после расшифровки. Аккордовых обозначений нет — только реально сыгранные ноты.",
  },
  {
    q: "Можно ли запустить локально или из Python?",
    a: "Да. Склонируйте [репозиторий MuScriptor Plus](https://github.com/leadpioneer/muscriptor-plus) и запустите `install.bat` / `start.bat` на Windows (либо см. QUICKSTART.md для ручной установки) — `muscriptor serve` открывает этот же веб-интерфейс на вашей машине, `muscriptor transcribe song.mp3` работает из командной строки. Работает на NVIDIA GPU, на Apple Silicon через Metal и на CPU с малой моделью.",
  },
  {
    q: "Насколько это точно?",
    a: "Это сильнейшая из известных нам открытых моделей транскрипции, но она не идеальна. Ожидайте очень хорошую заготовку, которую вы дочистите в DAW. MuScriptor обычно лучше справляется с акустической и гитарной музыкой, чем с электронной. Если нужен точный бенчмарк — [прочитайте статью](https://arxiv.org/abs/2607.08168).",
  },
  {
    q: "Что происходит с загруженным аудио?",
    a: "Оно расшифровывается на сервере и потом не сохраняется. Если не хотите, чтобы аудио покидало вашу машину, — [запустите MuScriptor Plus локально](https://github.com/leadpioneer/muscriptor-plus).",
  },
  {
    q: "Как это работает технически?",
    a: "MuScriptor — трансформер decoder-only: читает аудио 5-секундными чанками и генерирует поток токенов, описывающих начала и концы нот и инструменты, из которых затем собирается MIDI. Одна из главных причин качества — датасет: модель обучена на 170 тыс. песен — от классики до тяжёлого метала. [Подробнее в статье](https://arxiv.org/abs/2607.08168).",
  },
  {
    q: "Где найти код?",
    a: "На GitHub: [github.com/leadpioneer/muscriptor-plus](https://github.com/leadpioneer/muscriptor-plus) — форк [MuScriptor](https://github.com/muscriptor/muscriptor). Код — под лицензией MIT.",
  },
  {
    q: "Как сообщить о баге или отправить отзыв?",
    a: "Пожалуйста, [создайте issue на GitHub](https://github.com/leadpioneer/muscriptor-plus/issues/new/choose) — баги и предложения по этому форку принимаются в его собственном репозитории.",
  },
];
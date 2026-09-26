/** Russian UI strings. Missing keys fall back to English (see i18n/index). */
import type { Dict } from "./en";

export const RU: Dict = {
  // Header / shell
  tagline: "Музыка в MIDI и ноты",

  // Welcome screen
  welcome_intro:
    "MuScriptor — лучшая на сегодня открытая модель мультиинструментальной транскрипции. Дайте ей запись — поп, классику, метал, джаз, что угодно — и она распознает ноты, сыгранные каждым инструментом, в MIDI и нотный лист, который можно скачать или исследовать в интерактивном плеере.",
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
  feedback_intro: "Отзыв, вопрос, баг? ",
  feedback_email: "Напишите нам",
  feedback_or: " или ",
  feedback_issue: "создайте issue",

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
    "MuScriptor — модель автоматической мультиинструментальной транскрипции музыки: превращает исходное аудио в MIDI по инструментам. Разработано",
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
};

/** FAQ pairs; answers support `[label](href)` links and `code` spans. */
export const FAQ_RU: { q: string; a: string }[] = [
  {
    q: "Что такое MuScriptor?",
    a: "MuScriptor превращает музыку в MIDI и ноты: вы даёте ему запись, а он распознаёт ноты, сыгранные каждым инструментом. Модель разработана компаниями [Kyutai](https://kyutai.org/) и [Mirelo](https://mirelo.ai/).",
  },
  {
    q: "Это бесплатно?",
    a: "Да. Демо бесплатно, код — под лицензией MIT, а веса модели опубликованы на HuggingFace под CC BY-NC 4.0 (некоммерческое использование). Если хотите запустить локально, загляните в наш [репозиторий на GitHub](https://github.com/muscriptor/muscriptor).",
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
    a: "Да. `uvx muscriptor serve` запускает этот же веб-интерфейс на вашей машине, `uvx muscriptor transcribe song.mp3` — из командной строки, а Python API — пара строк. Работает на NVIDIA GPU, на Apple Silicon через Metal и на CPU с малой моделью. [Инструкции по установке — на GitHub](https://github.com/muscriptor/muscriptor).",
  },
  {
    q: "Насколько это точно?",
    a: "Это сильнейшая из известных нам открытых моделей транскрипции, но она не идеальна. Ожидайте очень хорошую заготовку, которую вы дочистите в DAW. MuScriptor обычно лучше справляется с акустической и гитарной музыкой, чем с электронной. Если нужен точный бенчмарк — [прочитайте статью](https://arxiv.org/abs/2607.08168).",
  },
  {
    q: "Что происходит с загруженным аудио?",
    a: "Оно расшифровывается на сервере и потом не сохраняется. Если не хотите, чтобы аудио покидало вашу машину, — [запустите MuScriptor локально](https://github.com/muscriptor/muscriptor).",
  },
  {
    q: "Как это работает технически?",
    a: "MuScriptor — трансформер decoder-only: читает аудио 5-секундными чанками и генерирует поток токенов, описывающих начала и концы нот и инструменты, из которых затем собирается MIDI. Одна из главных причин качества — датасет: модель обучена на 170 тыс. песен — от классики до тяжёлого метала. [Подробнее в статье](https://arxiv.org/abs/2607.08168).",
  },
  {
    q: "Где найти код?",
    a: "На GitHub: [github.com/muscriptor/muscriptor](https://github.com/muscriptor/muscriptor). Код — под лицензией MIT.",
  },
  {
    q: "Как сообщить о баге или отправить отзыв?",
    a: "Напишите нам на [почту](mailto:muscriptor@kyutai.org) или [создайте issue на GitHub](https://github.com/muscriptor/muscriptor/issues/new/choose).",
  },
];
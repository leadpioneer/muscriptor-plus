/**
 * English UI strings — the source of truth for the dictionary shape. Keys are
 * grouped by component. The `t()` helper falls back to these when the active
 * dictionary is missing a key, and to the key itself when both are.
 */
export type Dict = Record<string, string>;

export const EN: Dict = {
  // Header / shell
  tagline: "Music to MIDI and sheet music",

  // Welcome screen
  welcome_intro:
    "MuScriptor Plus is a fork of MuScriptor, the best open multi-instrument transcription model to date: it adds a Russian UI, per-instrument volume controls and live model switching. Give it a recording — pop, classical, metal, jazz, whatever — and it transcribes the notes played by every instrument into MIDI and sheet music, for you to download or explore interactively.",
  drop_audio_here: "Drop an",
  drop_audio_here_strong: "audio file",
  drop_audio_here_tail: "here, or",
  select_audio: "Select an audio file",
  try_example: "or try an example track",
  loading_example: "Loading example…",
  choose_different: "Choose a different file",
  server_unavailable: "unavailable",
  server_down_full: "The muscriptor server is temporarily unavailable. Please try again later.",
  transcribe: "Transcribe",
  transcribing: "Transcribing…",
  servers_busy: "Servers busy, retrying…",
  servers_busy_in: "Servers busy, retrying in {n}s",
  drop_anywhere: "Drop anywhere",
  cancel: "Cancel",
  alert_example_failed: "Couldn't load the example file: {message}",

  // Conditioning panel
  cond_title: "What instruments are there in this track?",
  cond_hint:
    "Optional. Leave empty to let the model detect anything; listing instruments here forbids every other instrument from appearing.",
  cond_clear: "Clear",
  cond_placeholder: "Add an instrument…",
  cond_remove: "Remove {name}",

  // Controls bar
  play: "Play",
  pause: "Pause",
  follow_playhead: "Follow playhead",
  follow_off_title: "Stop following the playhead",
  follow_on_title: "Scroll along with the playhead",
  volume_original: "Original",
  volume_midi: "MIDI",
  volume_master: "Master",
  stereo: "Stereo",

  // Instrument list
  instruments: "Instruments",
  model_label: "Model",
  model_loading: "loading…",
  model_error: "load failed",
  model_retry: "retry",
  instruments_given_hint:
    "The instruments you specified. Greyed-out ones weren't detected in the audio.",
  more_instruments: "More instruments",
  more_instruments_hint:
    "More instruments that the model detected in the audio, even without them being explicitly given.",
  not_detected: "not detected",
  help_aria: "What does this mean?",
  volume_title: "Volume of {name}",
  solo_title: "Solo (mute everything else)",
  unsolo_title: "Unsolo",
  mute_title: "Mute on MIDI track",
  unmute_title: "Unmute on MIDI track",

  // Output bar
  download: "Download",
  download_midi: "MIDI file",
  download_wav_synth: "WAV - transcription only",
  download_wav_synth_title:
    "Just the transcribed notes, played with a SoundFont (mono)",
  download_wav_mix: "WAV - stereo with original",
  download_wav_mix_title:
    "Original audio (L) + transcribed notes played with a SoundFont (R)",
  download_sheets: "Sheet music",
  download_sheets_title:
    "Engraved notation: PDFs per instrument, tablature, MusicXML",
  synthesizing: "Synthesizing…",
  generating: "Generating…",
  transcribe_another: "Transcribe another file",
  alert_wav_failed: "Couldn't create the audio file: {message}",
  alert_sheets_failed: "Couldn't engrave the sheet music: {message}",

  // Sheets dialog
  sheets_title: "Download sheet music",
  sheets_not_quantized:
    "We couldn't find a steady beat in this recording, so the bar lines are guesses. The score may be hard to read.",
  sheets_midi_file: "MIDI file",
  sheets_musicxml: "MusicXML score",
  sheets_full_score: "Full score – every instrument",
  sheets_tablature: " — tablature",
  sheets_download_all: "Download all ({n} files, {size})",
  close: "Close",

  // MIDI → sheets
  midi_sheets_idle: "or engrave a MIDI file you already have",
  midi_sheets_busy: "Generating sheet music…",

  // Progress / feedback
  estimating: "estimating…",
  done_in: "done in {time}",
  feedback_intro: "Found a bug or have an idea? ",
  feedback_email: "Email us",
  feedback_or: " or ",
  feedback_issue: "create an issue on GitHub",

  // App dialogs
  confirm_discard: "Discard this transcription and start over?",
  confirm_discard_dropped:
    "Discard this transcription and start over with the dropped file?",

  // Consent banner
  consent_text:
    "We use cookies (Google Analytics) to understand how this demo is used: page visits and anonymous usage events, e.g. the length of the transcribed audio and the instruments you select; never the audio itself. See the privacy policy.",
  consent_accept: "Accept",
  consent_decline: "Decline",

  // Drop overlay
  drop_to_transcribe_intro: "Drop an",
  drop_to_transcribe_strong: "audio file",
  drop_to_transcribe_tail: "to transcribe",

  // Footer
  footer_about_pre:
    "MuScriptor Plus is an enhanced fork of the MuScriptor transcription model: it turns raw audio into per-instrument MIDI. The model was trained by",
  footer_and: "and",

  // FAQ
  faq_title: "Frequently asked questions",
};

/** FAQ pairs; answers support `[label](href)` links and `code` spans. */
export const FAQ_EN: { q: string; a: string }[] = [
  {
    q: "What is MuScriptor Plus?",
    a: "MuScriptor Plus is an enhanced fork of [MuScriptor](https://github.com/muscriptor/muscriptor), the multi-instrument transcription model developed by [Kyutai](https://kyutai.org/) and [Mirelo](https://mirelo.ai/): it turns music into MIDI and sheet music — you give it a recording and it transcribes the notes played by every instrument. The fork adds a Russian UI, volume controls, live model switching and Windows fixes.",
  },
  {
    q: "Is it free to use?",
    a: "Yes. This app is free, the code is MIT-licensed, and the model weights are published on HuggingFace under CC BY-NC 4.0 (non-commercial use). If you want to run it locally, check out the [MuScriptor Plus GitHub repo](https://github.com/leadpioneer/muscriptor-plus).",
  },
  {
    q: "What audio formats can I upload?",
    a: "MP3, WAV, FLAC, OGG, M4A, AIFF, or Opus. Drop the file on the page or use the file picker.",
  },
  {
    q: "Which instruments can it transcribe?",
    a: "Voice, piano, guitars, bass, strings, brass, woodwinds, drums and many more. To improve accuracy, you can also tell it up front which instruments to expect. See the dropdown in the instrument selection for the full list. ",
  },
  {
    q: "Can I convert a song to sheet music with it?",
    a: "Yes. After transcribing, the download menu gives you the sheet music as PDFs, either per-instrument or the full score. You also get the MusicXML if you want to edit it in software like MuseScore, Sibelius or Guitar Pro.",
  },
  {
    q: "Can it give me guitar tabs?",
    a: "Yes. Fretted instruments like guitar and bass also yield a tablature PDF, next to the standard notation. Download it from the sheet music menu after transcribing. It does not write chord symbols, only the notes that are actually played.",
  },
  {
    q: "Can I run it locally or use it from Python?",
    a: "Yes. Clone [the MuScriptor Plus repo](https://github.com/leadpioneer/muscriptor-plus) and run `install.bat` / `start.bat` on Windows (or see QUICKSTART.md for the manual setup) — `muscriptor serve` runs this same web UI on your machine, `muscriptor transcribe song.mp3` does it from the command line. It runs on NVIDIA GPUs, on Apple Silicon via Metal, and on CPU with the small model.",
  },
  {
    q: "How accurate is it?",
    a: "It's the strongest open transcription model we know of, but it is not perfect. Expect a very good starting point that you clean up in a DAW. MuScriptor tends to work better on acoustic and guitar music than electronic music. If you'd like a more exact benchmark, [check out the paper](https://arxiv.org/abs/2607.08168).",
  },
  {
    q: "What happens to the audio I upload?",
    a: "It's transcribed on the server and not kept afterwards. If you'd rather it never leaves your machine, [run MuScriptor Plus locally](https://github.com/leadpioneer/muscriptor-plus).",
  },
  {
    q: "How does it work, technically?",
    a: "MuScriptor is a decoder-only transformer that reads the audio in 5-second chunks and generates a token stream describing note onsets, offsets and instruments, which is then assembled into MIDI. A major reason why it works so well is the dataset: MuScriptor is trained on 170k songs spanning classical music to heavy metal. [Read more in the paper](https://arxiv.org/abs/2607.08168).",
  },
  {
    q: "Where can I find the code?",
    a: "On GitHub: [github.com/leadpioneer/muscriptor-plus](https://github.com/leadpioneer/muscriptor-plus) — a fork of [MuScriptor](https://github.com/muscriptor/muscriptor). The code is MIT-licensed.",
  },
  {
    q: "How do I report a bug or send feedback?",
    a: "Please [open an issue on GitHub](https://github.com/leadpioneer/muscriptor-plus/issues/new/choose) — bugs and suggestions for this fork are handled in its own repository.",
  },
];
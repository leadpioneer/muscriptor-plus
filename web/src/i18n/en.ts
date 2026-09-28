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

  // Vocal removal (opt-in preprocessing)
  rv_title: "Remove lead vocals before transcription",
  rv_hint: "May improve instrument and tablature transcription.",
  rv_caveat: "On some tracks, separation may alter instrument timbre.",

  // Preprocessing stages (shown while transcribing with vocal removal on)
  stage_prepare: "Preparing audio…",
  stage_vocal_removal: "Removing lead vocals…",
  stage_instrumental: "Preparing instrumental…",
  stage_transcription: "Transcribing instrumental…",
  stage_midi: "Creating MIDI…",

  // Result / stem downloads
  result_from_instrumental:
    "Transcribed from the instrumental (lead vocals removed).",
  download_stem_vocals: "Vocals (WAV)",
  download_stem_instrumental: "Instrumental (WAV)",
  alert_stem_failed: "Couldn't download the stem: {message}",

  // Preview source (after a vocal-removal run)
  source_title: "What the preview plays",
  source_original: "Original",
  source_instrumental: "Instrumental",
  source_vocals: "Vocals",

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
  model_unload: "unload",
  model_unload_title:
    "Free GPU memory (the model reloads from cache on the next request)",
  model_unloaded: "unloaded",
  model_load: "load",
  model_load_title: "Load the model back into GPU memory",
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

  // Guitar Arranger Lab
  guitar_open: "Edit fingering",
  guitar_title: "Guitar Arranger Lab",
  guitar_open_midi: "Open MIDI",
  guitar_loading: "Arranging…",
  guitar_pick_track:
    "This MIDI has several note-bearing tracks. Pick one:",
  guitar_track_option: "{name} — track {track}, channel {channel} — {n} notes",
  guitar_track_unnamed: "Unnamed track",
  guitar_phrase_option: "Phrase {n} · {count} notes",
  guitar_string_fret: "s{s} f{f}",
  guitar_finger_short: "f{n}",
  guitar_locked: "locked",
  guitar_midi_pitch: "MIDI pitch {pitch}",
  guitar_note_aria: "{note}: string {s}, fret {f}",
  guitar_hand_position: "Hand position: {n}",
  guitar_finger_label: "Finger: {n}",
  guitar_unlock: "Unlock position",
  guitar_hint:
    "Every marked position produces the same pitch. Locking one position recalculates neighboring notes for the whole phrase.",
  guitar_download: "Download arrangement.json",
  guitar_position_changes: "Position changes: {n}",
  guitar_hand_travel: "Hand travel: {n}",
  guitar_largest_shift: "Largest shift: {n}",
  guitar_phrase_cost: "Phrase cost: {n}",
  guitar_error_line: "Arrangement failed: {message}",
  guitar_no_source:
    "Load a MIDI file to inspect and fix its guitar fingering — no transcription needed.",
  guitar_error_polyphonic_input:
    "Several notes start at the same moment (tick {tick}, pitches {pitches}). The arranger optimizes a single melodic line — pick a monophonic track or extract the melody first.",
  guitar_error_invalid_midi: "This file could not be read as a MIDI file.",
  guitar_error_unplayable_note:
    "Pitch {pitch} is outside the guitar's range ({low}–{high}) in this tuning.",
  guitar_error_track_not_found: "No note-bearing track matches this choice.",
  guitar_error_invalid_overrides:
    "A fixed position contradicts the MIDI input.",
  guitar_error_invalid_melody_policy:
    "Unknown melody reduction policy.",
  guitar_take_top: "Take the top voice",
  guitar_take_bottom: "Take the bottom voice",
  guitar_melody_label: "Melody",
  guitar_melody_off: "All notes",
  guitar_melody_top: "Highest note of each simultaneous-onset event",
  guitar_melody_bottom: "Lowest note of each simultaneous-onset event",
  guitar_melody_top_short: "top note",
  guitar_melody_bottom_short: "bottom note",
  guitar_melody_hint:
    "Top/bottom is selected only among notes with the same onset. It is not melody/bass voice separation.",
  guitar_melody_summary: "Melody: {policy} · {n} notes dropped",
  guitar_chord_notes: "Chord: {n} notes",
  guitar_single_note: "Note",
  guitar_barre: "Barre: fret {fret}, strings {from}–{to}",
  guitar_locked_count: "Locked: {n}/{total}",
  guitar_finger_unknown: "unknown",
  guitar_download_musicxml: "Download MusicXML",
  guitar_midi_tooltip:
    "MIDI keeps the notes and rhythm, but not the chosen strings and frets.",
  guitar_fingering_tooltip: "MusicXML and PDF keep the chosen fingering.",
  guitar_play: "Listen",
  guitar_pause: "Pause",
  guitar_play_title:
    "Play the arrangement at a nominal 120 BPM (the document has no tempo map).",
  guitar_download_midi: "Download arrangement.mid",
  guitar_tab_button: "Tablature",
  guitar_tab_title: "Tabulature (16th-note grid, bar lines every 4 beats)",
  guitar_download_tab: "Download tab (.txt)",
  guitar_pdf: "PDF (score + tab)",
  guitar_pdf_busy: "Generating PDF…",
  guitar_fretboard_title: "Guitar fretboard with the selected note and its legal positions",
  guitar_fretboard_aria: "Fretboard: {note} currently at string {s}, fret {f}",
  guitar_aria_position:
    "{note}: string {s}, fret {f}, hand position {hp}, finger {fg}",
  guitar_aria_position_multi: "{note}: string {s}, fret {f}, hand positions {hp}",
  guitar_fingering_combo: "hand {hp} / finger {fg}",

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
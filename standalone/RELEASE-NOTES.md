<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin 0.7.0b7 beta

- New installations use the system locale and a locked input language. English
  defaults to Base.en, other supported locales to multilingual Base. Small and
  Small.en remain quality choices. Turbo remains available for local import and
  is labelled as a large-encoder model, not a CPU speed option.
- Legacy Small + automatic-language defaults migrate to the locale and compact
  model. Explicit legacy language/model choices are retained; selecting
  Multilingual (auto) explicitly now detects once per recording session and locks
  subsequent phrases. Existing downloaded models are retained.
- CPU threads default to the detected physical core count and are configurable;
  inference retains one killable worker. The model stays loaded while enabled by
  default. The optional idle timeout increases from five minutes to one hour;
  legacy five-minute defaults migrate to one hour.
- Adaptive microphone noise calibration, 500 ms endpoint silence and an 8-second
  phrase cap replace the fixed energy gate. Endpointed input skips the redundant
  Whisper VAD pass. Ready tones use cached audio through memory/stdin.
- Ordered text insertion has its own bounded queue. Per-phrase focus verification
  and focus-change guards remain; keyboard events avoid per-key portal replies.
  No clipboard is used for dictation insertion.
- Numeric per-phrase speech/endpoint/recognition/typing timings are logged, without
  transcript text, and shown beside recent transcripts. Dictation status changes
  also reach the copyable status bar.

All new downloadable tiers use verified immutable
Systran revisions and retain their upstream MIT model cards. Hardware-specific
results and remaining target-device checks are recorded in backend/WHISPER-VALIDATION.md.


Dictation now takes priority over AKS speech: playback is temporarily suppressed
while recording/transcribing, including Speech Dispatcher output. Piper remains
available and saved volume is unchanged. Suppressed requests do not replay later.
The copyable status field now has a grey background.

Cloud measurements for five-second clips, two threads, warm medians: English
Small/auto 3.07 s versus Base.en/locked 0.61 s; German Small/auto 3.23 s versus
Base/locked 0.67 s. These are inference-only results, not Steam Deck latency claims.
Live microphone readiness and end-to-end insertion targets still need device tests.

Quit the old AKS from its tray before launching. Existing voices, models and
preferences are retained; no reset is required. The compact model may need its
one-time download when voice input is explicitly enabled. AppImage downloads
still exclude voice/model weights and bundle the clipboard readers.

For SteamOS testing, keep Orca running, choose Base.en and English, wait for Ready,
dictate a five-second sentence, then stop. Check speech resumes and copy the
transcript timings. Repeat with Base and Multilingual (auto), cancellation,
window changes and repeated start/stop cycles. Shortcut permission persistence,
LibreOffice direct selection and character-echo clipping remain follow-up work.

See the [beta checklist](https://github.com/jg00dman/akousousin/blob/main/standalone/BETA-TESTING.md)
and [full measurements](https://github.com/jg00dman/akousousin/blob/main/backend/WHISPER-VALIDATION.md).

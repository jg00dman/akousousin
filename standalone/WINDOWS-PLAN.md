<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Native Windows integration work plan

Status: 10 November 2026. Complete Windows support is forthcoming and not yet
working end to end. Linux 0.7.0b9 remains the current tested desktop baseline.
This work is separate from the proposed Linux rolling-transcription/overlay
experiment. Existing SAPI output and Windows CI coverage do not establish
interactive desktop readiness.

## Installation blockers

- [ ] Ship and verify the UTF-8 model JSON fix on a non-UTF-8 Windows locale.
  Tokenizer installation failed with a CP1252 UnicodeDecodeError. Local regression
  tests reproduce that default encoding; the source fix is not released yet.
- [ ] Ship and verify unique settings staging plus bounded file-lock retries.
  Preserve existing settings on failure, clean up staging and avoid shared
  settings.tmp collisions. Local regression tests pass; Windows desktop retest
  of starter voice installation is still required.
- [ ] Provide a console-free GUI launch while preserving CLI, SAPI service and
  multiprocessing behaviour. Avoid merely hiding exceptions; retain diagnostics.
- [ ] Investigate QObject timer shutdown warnings and ensure Qt-owned resources
  and timers are stopped/destroyed on their owning thread.
- [ ] Surface useful model-install/load failure details in selectable UI text.

## Native desktop integration

- [ ] Add RegisterHotKey-based global dictation, read-selection and read-copied
  text actions. Persist enablement and user-chosen bindings; restore on startup,
  unregister on quit and report shortcut conflicts. Test toggle listening and
  push-to-talk release handling; select an appropriate API for release tracking.
- [ ] Add Windows microphone enumeration and capture, including default device,
  unplug/disconnect, muted/silent input and privacy-denial feedback. Reuse bounded
  endpointing, ready cues, model workers, timeouts and cancellation.
- [ ] Retrieve selected text using UI Automation where supported. Keep copied
  text an explicit fallback; do not silently read an unrelated stale clipboard.
- [ ] Add Unicode SendInput insertion with foreground/focus guards, balanced key
  events, bounded queues and immediate Stop cancellation. Handle elevated-target
  restrictions honestly; do not request administrator rights as a blanket fix.
- [ ] Route reading through the shared speech backend, preserving read/stop
  ownership and cancellation without Linux Speech Dispatcher dependencies.
- [ ] Label unsupported controls clearly until each native path is implemented.

## Acceptance before claiming Windows support

- [ ] Clean first run under a standard account, starter voice download and sample.
- [ ] Pinned Whisper download, warm-up and transcription under Windows locales.
- [ ] Shortcut restoration after quit/relaunch and reboot; conflicts and disable.
- [ ] Dictation into Notepad, a browser and LibreOffice, including Unicode,
  focus changes, Stop during recognition/insertion and no delayed replay.
- [ ] Read selection/copy fallback and interruption in supported native apps.
- [ ] Clean quit closes panel, tray, capture, owned workers and shortcut sessions.
- [ ] Retest native SAPI speech, install/uninstall, diagnostics and documented
  limitations. Keep Linux regressions covered. No release/workflow redesign is
  required for this work plan.

## Linux next step (not implemented)

Create a separate branch for rolling Whisper hypotheses and stable-word
insertion, followed by a non-focus-taking provisional-text overlay. Benchmark
Steam Deck latency and accuracy before changing the released phrase pipeline.
Caret positioning is conditional on available accessibility information; retain
a movable fallback. No GPU backend or overlay has been implemented yet.

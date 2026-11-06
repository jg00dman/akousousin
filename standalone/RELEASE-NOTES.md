<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin 0.6.0b3 beta

This beta adds experimental local Whisper voice input on Linux while retaining
SAPI speech output on Wine/native Windows and native Linux Speech Dispatcher.
Voice input is not a SAPI recognition engine.

- Multilingual Small runs locally on CPU with int8 inference and neural VAD.
  Model weights download once or can be imported, and remain in the XDG-aware
  `~/.local/share/Akousousin/models/whisper/` cache across application updates.
  The AppImage does not bundle Whisper model weights.
- Voice Input provides named microphone selection, searchable language selection,
  automatic language display, Enable/Disable voice input and diagnostic recording.
  An approved shortcut can load recognition again after it was disabled.
- KDE Wayland dictation uses desktop shortcut/keyboard permission portals and
  guarded Unicode insertion. Toggle and push-to-talk are supported. Initial
  permission setup is still required; other compositors are not supported.
- The tray menu is Start/Stop Speech, Start/Stop Dictation, Default Voice,
  Configure, Quit. Single left-click opens the menu; double-click opens Configure.
- Normal Quit closes owned control panels, speech/input workers and portal
  sessions. The updater preserves its own panel only until replacement completes.
- Voice Input and Settings gain wheel scrolling; the voice library exposes its
  scrollbars. Window sizing better accommodates smaller screens.
- Ready feedback uses two 300 Hz tones at the maximum clean PCM level, plus a
  separate sound test. The gain is about +10.3 dB over the earlier trial; a full
  +12 dB at its former amplitude would clip.

Speech output, idle model unloading, the voice library and verified Linux AppImage
updates remain available. The reviewed LJSpeech starter voice downloads on demand
or can be included in an offline build. Licences, checksums and matching sources
accompany the packages. Native Windows
microphone capture and SAPI recognition are not implemented.

Whisper may infer punctuation, but spoken commands such as “question mark” can
remain literal. Automatic document proofing-language tagging is not implemented.
Recognition accuracy, non-Latin insertion and wider desktop interactions still
need testing. User testing confirmed microphone capture and insertion into Kate
and a chat text field on Kubuntu 26.04 Wayland. See COMPATIBILITY.md and TESTING.md,
and the [Voice Input guide](https://github.com/jg00dman/akousousin/blob/main/recognition/PANEL-TESTING.md).

## On-demand voice packaging

Default builds download Piper voices on first use instead of bundling LJSpeech.
Overview offers the reviewed starter voice or Voice library; existing downloads
and voice choices survive upgrades. Optional offline builds can include LJSpeech.
Voice, Whisper and AppImage downloads show byte-based progress in the panel and
a download indicator with details in the tray. Unknown-size and verification
stages show activity without a fabricated percentage.

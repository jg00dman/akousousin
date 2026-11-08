<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin 0.7.0b8 beta

This trial addresses corrupted text, repeating keys and insertion continuing
long after toggle-mode Stop in beta 7. Real Kate/LibreOffice delivery still needs
confirmation on the target desktop; protocol tests alone cannot establish that.

- Toggle Stop now cancels the session's pending/in-flight insertion. Later
  recognition results remain in the transcript, and a new session cannot replay
  them. Push-to-talk retains its explicit submit-on-release behaviour.
- Keyboard events each wait for a portal acknowledgement and are paced. Key
  release is protected against cancellation; failed release disables and closes
  the keyboard session. The no-reply burst path has been removed.
- Transcript history grows to up to 200 phrases, with an IPC size bound. The
  larger display has a scrollbar, Ctrl+A, preserved selection and Copy transcript
  includes timings. The display is read-only so incoming keys cannot overwrite it.
- Whisper performs a real encoder/decoder warm-up before Ready. This moves lazy
  first-inference initialization before microphone capture; it does not remove
  startup cost. Cached workers remain available between sessions.
- Ready tones use seekable WAV playback with a 200 ms device-wake lead-in. Linux
  normally uses an anonymous RAM file. Tone amplitude is fixed; audible playback
  and device routing still need verification on SteamOS.
- Speech suppression ends when microphone capture closes, rather than waiting
  for delayed transcript-only recognition. No microphone gain/sensitivity control
  or system-wide microphone changes are introduced.

Quit the old AKS from its tray before launching this build, to close its old
keyboard session. Existing voices/models/preferences are retained; no reset or
model redownload is required.

Test Base.en + English with two CPU threads first. Check exact text in Kate and
LibreOffice, then stop with Ctrl+Alt+Space while work is pending. After Stop, no
further text should be automatically typed. Delayed results should be retained
only in Voice Input. Copy the diagnostics, check Ctrl+A, and test the ready tones.
Then start a new session and check that no old text reappears.

Small or unsuitable thread settings can still exceed real-time processing speed.
This remains phrase-based recognition: a three-second bound during uninterrupted
speech is not claimed. Church Cap's MIT-licensed rolling-caption design has been
reviewed, but no Church Cap code is included in this repair.

See the [beta checklist](https://github.com/jg00dman/akousousin/blob/main/standalone/BETA-TESTING.md)
and [recognition measurements](https://github.com/jg00dman/akousousin/blob/main/backend/WHISPER-VALIDATION.md).

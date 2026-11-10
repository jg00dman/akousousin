<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Unreleased

- A saved Wine executable/AppImage that no longer exists no longer blocks
  registration refresh, application updates or AppImage relocation. Skip only
  that registration, keep its record for repair, and show a persistent warning
  in the panel status and Updates page. Other refresh failures still stop the
  operation. Relocation retains the original AKS download when a skipped
  registration may still use it. This fix is not in the beta 10 downloads.

# Akousousin 0.7.0b10 beta

- Add `Akousousin-Linux-x86_64.tar.gz` as a no-FUSE alternative. AppImage remains
  the default. The tar includes a per-user installer/uninstaller, private runtime,
  desktop/menu integration and matching bundled licence notices. Installation and
  upgrades preserve shared settings/models; failed replacement rolls back.
- Every format can check for updates and show notifications. Only an actual
  AppImage launch offers self-installation; tar and other installations open the
  release download page and use their installer or package manager.

**Complete native Windows application support is forthcoming and is not yet
working end to end.** The Windows ZIP is experimental: user testing found
voice-install settings failures and Whisper tokenizer decoding failures. Windows
global dictation/reading shortcuts, native microphone capture and desktop text
integration are not implemented. SAPI speech-output components have automated
coverage, but that is not evidence of a working complete Windows application.
See the [Windows work plan](WINDOWS-PLAN.md).

- Fix model JSON reads to use UTF-8 rather than the Windows default code page.
- Use unique settings staging files and bounded retries for Windows file locks.
  These fixes address failures reported in 0.7.0b9; Windows desktop retesting is
  still required before claiming complete Windows support.

# Akousousin 0.7.0b9 beta

**Windows support is forthcoming, not yet working end to end.** This beta's
Windows ZIP is experimental and lacks native dictation capture and global
reading/dictation shortcuts. User testing also identified voice-install and
Whisper-download failures; do not treat package CI success as desktop readiness.

- Use a single deterministic Whisper decoding attempt instead of retrying at
  multiple temperatures. Noisy fixtures reproduce substantial retry overhead;
  this does not guarantee accurate recognition of noise or a fixed response time.
- Add speech-end-to-recognition and speech-end-to-first/last-key diagnostics.
  Speech end is estimated from the last above-threshold captured frame. Key
  timestamps measure KDE acknowledgements, not application rendering. Copy
  transcript includes the new measurements. Reliable acknowledged delivery and
  Stop cancellation are preserved; shortcut defaults and Orca STOP are unchanged.

- Remember approved dictation and reading shortcut enablement across AKS restarts.
  Quit closes the live sessions while preserving that preference; explicit Disable
  prevents restoration. Startup restores shortcuts without starting recording.
- Request persistent RemoteDesktop keyboard permission on portal version 2 and
  save/rotate its restore token in a private settings sidecar. Desktop backends
  without restoration support may still prompt. Existing users must enable once
  after upgrading because earlier builds did not save this preference.

Trial checks: quit the old instance, enable each desired shortcut once, then
quit/relaunch and reboot. Verify shortcuts restore without opening the panel and
without recording automatically. Test first and subsequent dictation phrases in
Kate and the browser; copy all timings and compare with perceived delay. Stop
while recognition is pending and confirm no later typing occurs. Desktop prompt
restoration and visible text latency require testing on the target KDE system.

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

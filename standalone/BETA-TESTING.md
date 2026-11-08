<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Testing the 0.7.0b7 beta

Download the [Linux AppImage or Windows ZIP](https://github.com/jg00dman/akousousin/releases).
Linux trial users need only the AppImage; source archives are separate downloads.
Quit the previous instance from its tray, replace the application and launch it.
Keep existing preferences and models; a configuration reset is not required.
See [installation and storage](README.md#linux-installation-and-storage).

## Beta 7 dictation checks on SteamOS

1. Enable voice input explicitly; allow the one-time Base.en/Base download if
   migration selected a compact model. Existing Small models remain cached.
2. With Orca running, select Base.en and English. Start dictation, wait for Ready,
   speak a five-second sentence and pause. AKS speech should yield to recording,
   and resume after Stop without replaying suppressed announcements.
3. Copy the transcript's speech, endpoint, queue, recognition and insertion timings.
   Record the perceived shortcut-to-ready and end-of-speech-to-text delay too.
4. Repeat using Base and Multilingual (auto); the first nonempty phrase should
   determine the language for that session, with later phrases locked to it.
5. Test Cancel, switching windows, and repeated start/stop. Wrong-window text must
   remain in Voice Input. Saved playback volume must remain unchanged.

## AppImage installation and menu shortcut

Launch from Downloads: the panel should offer to move the AppImage to the
recommended XDG data location and add a menu shortcut. Declining should leave the
file in place; Settings → AppImage installation can retry. Accepting should verify
the copy, refresh existing registrations, restart and remove the unchanged source.
Check the menu shortcut opens AKS and displays its icon after the old temporary
AppImage mount disappears. An existing destination requires confirmation. Running
from the recommended location should create the shortcut without asking to move.
The panel header should show the AKS artwork, without a bars text character.

## First run and speech output

1. With a fresh profile, Overview should offer Download starter voice (about
   64 MB) or Choose another voice. Existing profiles should retain voices/defaults.
2. Watch the real byte progress and tray download indicator. Wait for verification
   to finish, then play a preview. Try another voice, speed and volume.
3. Replace/restart the app and confirm the installed voice is reused. The default
   AppImage contains runtimes but no Piper voice or Whisper model weights.
4. If testing SAPI, close the target Wine/Windows application before installing
   support in Settings. Test speech, rate, cancellation and restart. For Wine, use
   the [private SAPI checks](PRIVATE-SAPI-TESTING.md); Wine system DLLs and PATH
   should remain unchanged.
5. On Linux, install Speech Dispatcher support in Settings and test `spd-say`.
   If restart fails, use the panel's Copy command button or the
   [manual restart instructions](SPEECH-DISPATCHER.md#manual-restart-if-registration-was-saved).

## KDE Wayland dictation

Install `pulseaudio-utils` if needed; PipeWire remains the audio server.

1. In Voice Input, choose Small and Enable voice input. The first download is
   about 485 MB; subsequent starts reuse it. Watch download/loading/ready states.
2. Choose a named microphone or System default. Test ready sound should play two
   short 300 Hz tones. Record ten seconds, waiting for Listening before speaking;
   check text and detected language. Try Stop recording, Cancel and another language.
3. Enable desktop shortcuts and approve KDE's shortcut and keyboard dialogs.
   Confirm the actual assigned key (suggested Ctrl+Alt+Space). Toggle listening is
   the default; test in Kate before a more complex application.
4. Test left-click on the tray to toggle dictation and right-click for its menu.
   Disable voice input, then activate the shortcut: it should reload the cached
   model. Check push-to-talk separately if you use it.
5. Test changing focus while recognizing. AKS should retain the transcript when
   focus is uncertain; switching during insertion can leave partial text.

If the portal reports App info not found despite a working launcher, see the
[portal troubleshooting guide](../recognition/PANEL-TESTING.md). Do not delete
settings or model caches. Spoken punctuation commands and document language
tagging are not implemented. SAPI support remains text-to-speech only.

## Global reading

1. Install/import a voice. Enabling reading shortcuts should automatically
   install Speech Dispatcher support, select AKS and verify the voice before KDE
   asks for shortcut permission. Test a missing voice or failed restart: shortcuts
   should remain disabled with a useful recovery instruction. The AppImage bundles Wayland and X11 clipboard readers; test without installing host clipboard packages.
2. In Read selection choose Enable global reading shortcuts. Approve or change
   Ctrl+Alt+R (selected text) and Ctrl+Alt+Shift+R (copied text) in KDE.
3. Highlight text in Kate, focus the document and press the selected-text shortcut.
   Press again during reading to stop. Repeat with the panel closed.
4. Copy different text and test the copied-text shortcut. Test Wine/Logos
   separately: some applications do not publish a primary selection, so use the
   explicit copied-text action. AKS should not silently read an old clipboard.
5. Check reading and dictation shortcuts still work after enabling both. Stop
   reading should affect only the AKS reader, not another Speech Dispatcher client.
6. Quit and relaunch AKS, enable shortcut sessions again and check KDE retains
   your chosen assignments.

Live shortcut dispatch and primary-selection availability in native/Wine apps
still require desktop confirmation. Automated portal, clipboard and real-daemon
checks do not establish those cases.

## Voice deletion, speed and latency

- Delete an installed downloaded voice after confirmation; its managed cache
  folder should disappear. Remove an imported voice and confirm its original
  ONNX/config files remain. Deleting the default should select another installed
  voice; deleting the last voice should show first-run choices without silently
  reimporting the bundled starter. Apply voice registration and check SAPI lists.
- Change speed using the slider and value control. Both should use 0.5–4.0 in
  quarter steps without long decimals; confirm the preference affects new speech.
- With the same voice in AKS and Orca, compare a warm sample with short interrupted
  speech. Confirm Stop is prompt, later speech recovers and other clients continue.
- Test dictation with a short phrase and include the displayed audio/queue/
  recognition/insertion timings in the report. The SteamOS delays remain under
  investigation; do not assume this trial resolves every latency cause.

## Panel and shutdown

- Open Configure repeatedly: the same panel should be raised. Close it and confirm
  the tray, reading and approved dictation shortcuts remain available.
- Check wheel scrolling and scrollbars in Voice Input, Voice library and Settings,
  including a smaller window. Errors should offer selectable text and copy actions.
- Quit from the tray: owned panels, capture, recognition, speech workers and portal
  sessions should close. Downloaded voices/models should remain on disk.

Report application version, OS/desktop, input/output device, assigned shortcut,
steps and copyable technical details. Screenshots of the setup pages are in the
[screenshot gallery](../docs/SCREENSHOTS.md). Broader control-panel accessibility
and Orca compliance are future work; no accessibility redesign is included here.

Check that long status messages can be selected and copied, including with the
status bar’s Copy button. Test selected and copied Unicode text on the target desktop.

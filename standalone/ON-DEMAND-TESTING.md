<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# On-demand voice trial

Download the AppImage alone. The default build includes the speech/dictation
runtimes and catalogue, with no Piper voice or Whisper weights. Existing voices,
settings and Whisper models are reused; nothing needs downloading again for an
upgrade.

On a fresh installation, Overview offers **Download starter voice (64 MB)** and
**Choose another voice**. The first installed/imported voice becomes the default.
Later downloads preserve an existing default. To test first-use behaviour without
disturbing your library, use a separate XDG data/config directory.

Downloads display actual received/total bytes and percentage in the control panel
on every page. Unknown-size or preparation/verification stages show activity
without a guessed percentage. The tray shows a blue download arrow/progress ring,
with download details in its tooltip and menu; failures show a red indicator.
This applies to voice models, Whisper models, licence cards and AppImage updates.

After downloading a voice, use Settings → Install / apply voice registration for
Wine, then test Logos Read Aloud and Preview. Check that existing desktop
dictation still works. The private SAPI installation from the preceding trial is
included and leaves Wine system DLLs and PATH untouched.

Left-click the tray icon to toggle desktop dictation. Right-click opens its menu;
choose Configure there to open the control panel. Speech Dispatcher registration
clears AppImage library overrides before calling host systemctl. If a restart
still fails, the error has a selectable recovery command, Copy command, and
separately expandable/copyable technical details. Other panel errors are also
selectable and copyable.

For offline first use, build with `python standalone/package.py --bundle-starter-voice`,
or tick **bundle_starter_voice** in the Standalone
Akousousin workflow. This includes the approved LJSpeech voice and its upstream
licence/provenance files. Unticked builds are model-free. The package still
contains its Python, Piper, Qt and recognition runtimes, so removing the voice
reduces the download rather than making it a tiny launcher.

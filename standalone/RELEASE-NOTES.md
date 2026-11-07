<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin 0.7.0b2 beta

This beta fixes Speech Dispatcher registration hiding eSpeak and makes the final
steps of an AppImage update visible. It adds optional weekly update checks and
stable/beta selection for AppImage installations.

- **Keep eSpeak available:** AKS joins Speech Dispatcher's discovered engine list
  instead of disabling discovery with its own AddModule entry. Existing explicit
  engine lists and defaults are preserved. After updating, choose **Settings →
  Install Speech Dispatcher support** again to repair an earlier AKS-only
  registration, then reopen Orca preferences. AKS and eSpeak should both appear.
- **Clear update progress:** download percentages describe only the download.
  Verification and installation show activity indicators, followed by an explicit
  restarting warning for three seconds. The relaunched panel briefly confirms
  the installed version. Failed registration still restores the previous image.
- **Optional weekly checks:** the Updates page provides Check for updates weekly
  and Show beta testing updates. Notifications offer Update now… (opens Updates
  for review) and Remind me later (one week), and wait while AKS is speaking or
  dictating. Nothing is installed automatically.
- **Stable/beta selection:** beta installations initially include beta updates;
  stable installations initially exclude them. Saved choices survive upgrades.
  Turning betas off never downgrades an installed beta: it waits for a newer
  stable release. Manual checks respect the same choice.
- **AppImage-only self-updating:** controls require an AppImage package marker and
  an executable APPIMAGE launch path. Other formats defer to their software
  manager or installation source. Voice and Whisper downloads remain independent.

The default AppImage contains runtimes but no Piper voice or Whisper model
weights. Existing downloads, preferences and selected voices are retained. New
users can download the starter voice (about 64 MB) or choose another voice;
Whisper Small is a separate one-time download (about 485 MB).

Global reading shortcuts, KDE Wayland dictation, private Wine SAPI installation,
Linux Speech Dispatcher output and Windows SAPI output remain available. This is
still a beta: native/Wine selection availability and wider desktop behaviour need
user testing. SAPI recognition, Windows microphone capture and comprehensive
control-panel accessibility are not implemented.

See the [beta checklist](https://github.com/jg00dman/akousousin/blob/main/standalone/BETA-TESTING.md)
and [installation guide](https://github.com/jg00dman/akousousin/blob/main/standalone/README.md).
Licences, matching sources and checksums accompany the packages.

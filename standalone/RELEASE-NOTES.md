<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin 0.7.0b3 beta

This beta adds optional AppImage installation and replaces the bars character in
the control-panel header with the actual Akousousin icon.

- Launching the AppImage outside its recommended XDG-aware location offers to
  move it to `~/.local/share/Akousousin/Akousousin-x86_64.AppImage` and create an
  application-menu shortcut. Choose No to continue running portably; retry later
  from Settings → AppImage installation.
- Existing destination files require replacement confirmation. The copy is
  verified and active registrations are refreshed before restarting. The original
  download remains until the restart command succeeds. Voices, models and
  preferences are retained.
- The menu shortcut uses a persistent icon and the installed AppImage path.
  Running an already-installed AppImage refreshes its shortcut. Custom desktop
  entries are preserved, and ordinary portal registration keeps the menu entry
  visible. No root privileges are required.
- Saved Speech Dispatcher launchers are refreshed when the AppImage path changes.
  Existing engines and module defaults remain unchanged.
- The header now shows the same AKS artwork used by the tray and window icon.

The 0.7.0b2 fixes remain included: eSpeak and AKS stay available together in Speech
Dispatcher; AppImage updates provide optional weekly checking, stable/beta
selection and explicit verification, installation and restart feedback. For an
older AKS-only Speech Dispatcher registration, install support again in Settings
and reopen Orca preferences.

The default AppImage contains runtimes but no Piper voice or Whisper model
weights. Existing downloads are reused. Native/Wine selection availability and
wider desktop behaviour remain beta testing items. Spoken punctuation commands,
SAPI recognition and GNOME global shortcut integration are not added in this
release.

See the [installation guide](https://github.com/jg00dman/akousousin/blob/main/standalone/README.md)
and [beta checklist](https://github.com/jg00dman/akousousin/blob/main/standalone/BETA-TESTING.md).
Licences, matching sources and checksums accompany the packages.

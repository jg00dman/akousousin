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

## Reading setup fixes on main after 0.7.0b3

Installing Speech Dispatcher support selects AKS as the default engine while
retaining eSpeak as an available choice. Removal restores the previous default;
application updates preserve later manual choices. Enabling global reading
shortcuts first installs and verifies speech support and the selected voice.
Permission setup proceeds only after success, with clear recovery on failure.
Readers explicitly select AKS and verify it before speaking; they do not silently
continue with eSpeak. Existing Orca profiles may require their engine selection
changed once in Orca preferences.

## HTTPS trust-store fix on main after 0.7.0b3

Licence reviews, voice/Whisper file downloads and update checks load the host's
standard CA bundle on SteamOS/Arch and other Linux distributions. Certificate and
hostname verification remain enabled; explicit custom trust stores are honoured.
This addresses frozen Ubuntu OpenSSL paths missing SteamOS's certificate store.

See the [installation guide](https://github.com/jg00dman/akousousin/blob/main/standalone/README.md)
and [beta checklist](https://github.com/jg00dman/akousousin/blob/main/standalone/BETA-TESTING.md).
Licences, matching sources and checksums accompany the packages.

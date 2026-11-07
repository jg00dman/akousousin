<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin 0.7.0b4 beta

This beta fixes certificate verification for downloads on SteamOS/Arch and makes
reading-shortcut setup install and verify its speech support automatically.

- **SteamOS HTTPS fix:** licence reviews, voice and Whisper file downloads, and
  update requests load the system's standard CA bundle, including SteamOS/Arch's
  certificate-store paths. Certificate-chain and hostname verification remain
  enabled. Explicit SSL_CERT_FILE / SSL_CERT_DIR settings are honoured.
- **Automatic reading setup:** Enable global reading shortcuts installs Speech
  Dispatcher support, selects AKS and verifies the engine and selected voice
  before requesting KDE shortcut permission. Download/import a voice first.
  Setup failures leave shortcuts disabled and report recovery instructions.
  Already-working support is verified without restarting the daemon.
- **AKS as the default engine:** installing Speech Dispatcher support selects AKS
  while keeping eSpeak available. Removing support restores the earlier default;
  later manual default choices survive application updates. Readers explicitly
  select AKS and verify the selection before speaking, rather than continuing
  through an unexpected engine.

If the older AppImage cannot check for this update because of its certificate
error, download the new AppImage directly using a browser. Quit the old AKS from
its tray before launching the new file. Voices, models and preferences are reused;
there is no need to clear configuration or download installed models again.

For existing speech support, choose Install Speech Dispatcher support again, or
Enable global reading shortcuts, to apply the new default. An Orca profile saved
explicitly to eSpeak may still need AKS selected once in Orca preferences.

AppImage relocation, application-menu integration, the proper header icon,
optional weekly update checks and stable/beta selection remain included. The
default package contains runtimes but no Piper voice or Whisper model weights.
GNOME global-shortcut integration, spoken punctuation commands and SAPI
recognition are not implemented in this release. SteamOS-specific desktop
behaviour still needs testing on the actual device.

See the [installation guide](https://github.com/jg00dman/akousousin/blob/main/standalone/README.md)
and [beta checklist](https://github.com/jg00dman/akousousin/blob/main/standalone/BETA-TESTING.md).
Licences, matching sources and checksums accompany the packages.

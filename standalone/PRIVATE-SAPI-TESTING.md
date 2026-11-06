<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Private SAPI compatibility trial

This trial installs the Wine 11.21 compatibility DLL at
`C:\Program Files\Akousousin\compat\x64\sapi.dll`. Wine's system SAPI files and
links remain untouched. SAPI COM default values point to the private DLL, with a
prefix-level `native,builtin` override. The prefix PATH is unchanged.

The normal AKS engine remains at
`C:\Program Files\Akousousin\akousousin-piper.dll`. Updating an installed private
compatibility DLL refreshes that private file even when the compatibility probe
already succeeds. Rollback/uninstall restores recorded COM default values and the
original override, preserving other registry values.

This trial targets fresh 64-bit Wine-prefix installations. Existing-install
migration is outside its scope. Choose the Wine executable/AppImage used by the
prefix in Settings, then install/apply voice registration. The compatibility
workaround is enabled only when needed or explicitly requested for testing, and
is limited to Wine 11.21. Native Windows system SAPI is not modified.

Quit the older AKS controller before launching this AppImage. The voice library,
Whisper model cache, speech output and Linux dictation remain available. No model
weights need to be downloaded again.

Checks cover two independent client directories, actual COM module locations,
SAPI speech/PCM generation and default-value restoration. Snapshots compare Wine
SAPI DLL bytes and symlinks before installation, after update and after uninstall.
No claim is made for 32-bit callers or every Wine version.

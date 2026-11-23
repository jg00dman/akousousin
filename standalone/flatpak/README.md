<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Flatpak compatibility trial

The proposed application ID is `io.github.jg00dman.akousousin`. The
desktop entry belongs in `/app/share/applications`, and the Spiel service
belongs in `/app/share/dbus-1/services`. A Flatpak installation exports both.
Spiel clients discover `io.github.jg00dman.akousousin.Speech.Provider`; the
provider uses the desktop user's selected voice in the client, and the sandbox
leaves the host libspiel default where the user set it.

The sandbox stores its own settings and model files and uses its application
runtime directory for IPC. The panel and the provider can connect to the same
controller across independent activations. The speech backend listens on
loopback and defaults to port 15041 in the sandbox.

The trial keeps the in-panel speech preview, voice library, recording and
transcript copy, and Spiel output. The host Wine/SAPI and Speech Dispatcher
registrations, global desktop shortcuts, cross-app dictation insertion, and
login autostart use the native distribution. The Flatpak uses the package
manager for updates.

## Remaining package work

A package still needs a supported runtime and Python 3.12 with Qt for Python,
Piper, and the pinned recognition dependencies. Install the resource tree
under `/app/share/akousousin`, compile its Qt catalogues and ship a reviewed
starter voice for a useful offline first launch. In-panel audio and microphone
capture use the package's PulseAudio client tools over the desktop audio
socket. Model downloads and the current loopback backend require network
sharing. Spiel fits the application's own D-Bus namespace.

Test the actual exported service, normal startup, voice preview, microphone
capture, model downloads, and coexistence with a native installation on a
Flatpak-capable desktop. The trial validates the provider through a filtered
D-Bus session, and Flatpak's filesystem and process isolation remain to be
tested. Add AppStream metadata and a store icon to the upstream project
before running Flathub's manifest and repository checks.

A Flathub submitter needs to author the manifest independently, disclose
applicable AI-generated material, and open the submission themselves.
See the [Flatpak export conventions](https://docs.flatpak.org/en/latest/conventions.html#d-bus-service-files),
[Flathub requirements](https://docs.flathub.org/docs/for-app-authors/requirements),
and [submission process](https://docs.flathub.org/docs/for-app-authors/submission).

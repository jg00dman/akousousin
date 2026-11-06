<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin — Neural Voice Engine

**akousousin:** *The unified neural speech engine for Linux, implementing Microsoft SAPI and Speech Dispatcher, based on Piper and Whisper.*

The 0.6.0b3 beta implements SAPI text-to-speech using Piper, native Linux Speech
Dispatcher output and experimental local Whisper voice input on Linux. SAPI
recognition and native Windows microphone capture are not implemented. See the
[compatibility table](../COMPATIBILITY.md) for the implemented capabilities.


[Beta downloads](https://github.com/jg00dman/akousousin/releases) · [Builds and validation](https://github.com/jg00dman/akousousin/actions).

One speech service and configuration per operating-system user. This beta contains
the standalone 64-bit SAPI engine, control panel, tray and Piper/Waitress backend.
It includes the reviewed en_US-ljspeech-medium starter voice, its model card,
checksum provenance and licence declarations. No Wine runtime or other voice weights
are bundled. Existing selected voices are preserved.

## Linux installation and storage

OuDedetai installs the AppImage to `~/.local/share/Akousousin/Akousousin-x86_64.AppImage`.
For manual installation, put the downloaded AppImage there and make it executable.
The Ubuntu 22.04 / x86-64 / glibc 2.35+ build target is unchanged.

- Preferences: `~/.config/Akousousin/settings.json`.
- Downloaded voices: `~/.local/share/Akousousin/voices/`.
- Whisper models: `~/.local/share/Akousousin/models/whisper/`, retained between upgrades.
- Imported Piper models remain in the location you explicitly select. Whisper
  imports are copied into the persistent Whisper cache.
- Logs: `~/.local/state/Akousousin/akousousin.log`.
- Private session/socket/control files: `$XDG_RUNTIME_DIR/Akousousin/`, with a
  private `/tmp/akousousin-<uid>/Akousousin/` fallback when no runtime directory exists.

XDG directory overrides are respected. Piper and Python stay inside the AppImage.
Its temporary extraction remains alive while Akousousin runs; no additional runtime
copy is stored in the data directory. Existing `runtimes/` copies from older betas
are no longer used. Old OuDedetai-specific settings are not copied implicitly.

Close Logos before registering an existing initialized 64-bit Wine prefix:

```bash
export APPIMAGE_EXTRACT_AND_RUN=1
IMAGE="$HOME/.local/share/Akousousin/Akousousin-x86_64.AppImage"
chmod +x "$IMAGE"
"$IMAGE" --wine-prefix "$HOME/wine-bisect-prefix/data/wine64_bottle" \
  --wine "$HOME/akousousin/wine-akousousin-piper-11.21-logos-x86_64.AppImage" --install-only
"$IMAGE"
```

The bundled LJSpeech voice is ready on a fresh installation. To use another
voice, import its `.onnx` file (matching `.onnx.json` alongside), or review and
download one in Voice library. Select Make default, then Settings → Install /
apply voice registration. Overview → Start server → Play sample tests real Piper and
playback. Next test Logos Read Aloud using the same Wine package.

## Tray and lifecycle

The original Akousousin waveform artwork is shared by the AppImage, window and tray.
A tray badge reports stopped, starting, running or error. Its menu provides
Start/Stop Speech, Start/Stop Dictation, Default Voice (grouped by readable
language names), Configure, Quit. A single left-click opens the menu; double-click
opens the control panel.
Default changes apply to subsequent speech; applications caching a SAPI voice may
need restarting. Newly downloaded voices need registration through Settings.

Closing the configuration panel leaves Akousousin/Piper running. Tray Quit stops
Piper, microphone capture, recognition/download workers and portal sessions, closes
control panels launched by that controller and exits Akousousin. It warns when
application speech sessions are active. An
application releasing the last session also stops Piper and exits Akousousin when
Akousousin was started automatically. An independent/manual start is left running.
On desktops without a tray, the panel and command interface remain usable.

## Launcher interface, version 2

```bash
"$IMAGE" --protocol-version                         # prints 2
"$IMAGE" --configure                                # configuration, no independent ownership
"$IMAGE" --acquire-session unique-id --owner-pid PID  # start/reuse and wait until ready
"$IMAGE" --release-session unique-id                 # release only that session
"$IMAGE" --status                                    # JSON status, does not start anything
"$IMAGE" --start-server                              # independent/manual start
"$IMAGE" --stop-server                               # explicit backend stop, tray remains
"$IMAGE" --quit                                      # stop speech/input, close panels and exit
"$IMAGE" --dictation-toggle                          # KDE dictation; starts permission setup if needed
"$IMAGE" --dictation-cancel                          # discard pending dictation
"$IMAGE" --dictation-status                          # shared voice-input status/transcripts
```

Use a distinct random ID per application session; repeat acquisition is idempotent.
The owner must be a running process. Akousousin checks its creation time and reaps
sessions whose owners exit, including launcher crashes. One session ending never
stops another's speech. The public commands return nonzero on errors; launchers
can still run their application without speech. Only Akousousin manipulates its own
private controller files. `--settings` remains a diagnostic/test override.

## Compatibility and rollback

This beta supports 64-bit callers only. Wine 11.21 prefixes missing the generic
SAPI enumeration fix use `C:\Program Files\Akousousin\compat\x64\sapi.dll`.
The installer redirects Wine SAPI COM default values to that private DLL and sets
`native,builtin`; Wine system DLL files and PATH remain unchanged. Original COM
default values and the override are saved for rollback/uninstall. Other Wine
versions needing that fix are refused rather than guessed.
Remove launcher-forced `sapi=b` when the compatibility DLL is required.

Settings → Uninstall & restore (or `--uninstall --wine-prefix ... --wine ...`)
restores original registry settings/defaults and removes or restores AKS-owned
private DLLs. It keeps voices
and preferences. Native Windows system SAPI is never replaced: extract the
Windows ZIP, use the same control panel/tray, and register with `--install` from
an administrator terminal. Windows data/config are under LocalAppData/Akousousin.

Language routing uses SAPI hints or a manually selected book language; automatic
foreign-word detection and full localisation are not implemented. Standard Piper
has no general pitch slider. Arabic/Hebrew auxiliary Piper output models are not distributed. This is separate
from multilingual Whisper input, which includes those language tokens but has
variable recognition accuracy. Model licences
vary; upstream cards and provenance are retained when downloading.

Original project code is GPL-3.0-or-later, copyright 2026 John Goodman, with
LGPL-2.1-or-later for the SAPI engine C code/API headers. Wine, Piper, Qt/PySide
and other dependencies retain their upstream terms and notices. Both application
packages include the GPL and LGPL texts and the component-licensing explanation. The source archive
includes matching Wine, Piper, eSpeak, Qt and PySide sources. Automated deterministic
WAV checks, real Piper output and session tests do not establish audible playback
or every Logos desktop behavior; test in a backed-up prefix.

## Checking for application updates

Open **Updates → Check for updates** in the control panel. Akousousin checks its
GitHub releases only when requested and offers newer versioned releases, including
betas. Cancel leaves the installation and speech untouched.

For Linux AppImages, accepting downloads and verifies the release asset's SHA-256
and size before stopping speech. Close Wine applications first. The AppImage is
replaced at its existing registered path, saved SAPI registrations are refreshed,
and the panel restarts. Voices and preferences are retained. The previous image
is kept alongside it as `.AppImage.previous`; a failed registration restores the
previous image and attempts to restore its registrations. A second simultaneous
update is refused. Restarted speech starts on demand as usual.

Windows ZIP and source installations offer the matching release download for
manual installation after quitting Akousousin. Automatic replacement is currently
available for Linux AppImages only. Release tags include the package version,
for example `standalone-beta-0.6.0b3-<build>-1`; older run-number-only tags are not
offered as updates. Each new release must increase the package version.

## Experimental Voice Input on Linux

Install `pulseaudio-utils` for `parec`/`paplay`; PipeWire remains your audio server
through its PulseAudio-compatible service. Open Voice Input and select Small
(default). Enable voice input downloads its pinned weights once if necessary and
loads them; Disable voice input stops recognition and frees model memory without
deleting the download. The ready status and two 300 Hz tones announce readiness;
Test ready sound checks playback separately on the system default output.

Choose a readable microphone or System default, and Automatic detection or a
language from the searchable, scrollable picker. The detected language is displayed
separately and does not silently lock the next recording. Start recording tests a
ten-second capture and displays text. Spoken punctuation commands are not interpreted.

On KDE Wayland, enable desktop shortcuts and approve KDE's shortcut and keyboard
input dialogs. The proposed shortcut is Ctrl+Alt+Space, subject to KDE approval.
Toggle listening is the default; push-to-talk is also available. A registered
shortcut can enable/load voice input again after it was disabled. Tray Start
Dictation can initiate permission setup when necessary. Stop/Cancel controls remain
in the panel, and cancellation is available from the command interface.

Voice Input and Settings support wheel scrolling and visible vertical scrollbars;
the voice library exposes vertical/horizontal scrollbars. The initial window fits
the available screen, and Settings remains accessible at smaller sizes.

[Voice Input testing and cache/portal troubleshooting](https://github.com/jg00dman/akousousin/blob/main/recognition/PANEL-TESTING.md)
explains the experimental limits. SAPI recognition, other Wayland compositors and
a general native input framework remain future work. No automatic word-processor
proofing-language tagging is implemented.

# OpenSAPI shared speech beta

One speech service and configuration per operating-system user. This beta contains
the standalone 64-bit SAPI engine, control panel, tray and Piper/Waitress backend.
It includes the reviewed en_US-ljspeech-medium starter voice, its model card,
checksum provenance and licence declarations. No Wine runtime or other voice weights
are bundled. Existing selected voices are preserved.

## Linux installation and storage

OuDedetai installs the AppImage to `~/.local/share/OpenSAPI/OpenSAPI-x86_64.AppImage`.
For manual installation, put the downloaded AppImage there and make it executable.
The Ubuntu 22.04 / x86-64 / glibc 2.35+ build target is unchanged.

- Preferences: `~/.config/OpenSAPI/settings.json`.
- Downloaded voices: `~/.local/share/OpenSAPI/voices/`.
- Imported models remain in the location you explicitly select.
- Logs: `~/.local/state/OpenSAPI/opensapi.log`.
- Private session/socket/control files: `$XDG_RUNTIME_DIR/OpenSAPI/`, with a
  private `/tmp/opensapi-<uid>/OpenSAPI/` fallback when no runtime directory exists.

XDG directory overrides are respected. Piper and Python stay inside the AppImage.
Its temporary extraction remains alive while OpenSAPI runs; no additional runtime
copy is stored in the data directory. Existing `runtimes/` copies from older betas
are no longer used. Old OuDedetai-specific settings are not copied implicitly.

Close Logos before registering an existing initialized 64-bit Wine prefix:

```bash
export APPIMAGE_EXTRACT_AND_RUN=1
IMAGE="$HOME/.local/share/OpenSAPI/OpenSAPI-x86_64.AppImage"
chmod +x "$IMAGE"
"$IMAGE" --wine-prefix "$HOME/wine-bisect-prefix/data/wine64_bottle" \
  --wine "$HOME/opensapi/wine-opensapi-piper-11.21-logos-x86_64.AppImage" --install-only
"$IMAGE"
```

The bundled LJSpeech voice is ready on a fresh installation. To use another
voice, import its `.onnx` file (matching `.onnx.json` alongside), or review and
download one in Voice library. Select Make default, then Settings → Install /
apply voice registration. Overview → Start server → Play sample tests real Piper and
playback. Next test Logos Read Aloud using the same Wine package.

## Tray and lifecycle

The original OpenSAPI waveform artwork is shared by the AppImage, window and tray.
A tray badge reports stopped, starting, running or error. Its menu provides
Start/Stop, installed voices grouped by readable language names, Configure, Quit.
Default changes apply to subsequent speech; applications caching a SAPI voice may
need restarting. Newly downloaded voices need registration through Settings.

Closing the configuration panel leaves OpenSAPI/Piper running. Tray Quit stops
Piper and exits OpenSAPI, warning when application sessions are active. An
application releasing the last session also stops Piper and exits OpenSAPI when
OpenSAPI was started automatically. An independent/manual start is left running.
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
"$IMAGE" --quit                                      # explicit stop and exit
```

Use a distinct random ID per application session; repeat acquisition is idempotent.
The owner must be a running process. OpenSAPI checks its creation time and reaps
sessions whose owners exit, including launcher crashes. One session ending never
stops another's speech. The public commands return nonzero on errors; launchers
can still run their application without speech. Only OpenSAPI manipulates its own
private controller files. `--settings` remains a diagnostic/test override.

## Compatibility and rollback

This beta supports 64-bit callers only. Wine 11.21 prefixes missing the generic
SAPI enumeration fix receive a prefix-local compatibility DLL, with originals
backed up. Other Wine versions needing that fix are refused rather than guessed.
Remove launcher-forced `sapi=b` when the compatibility DLL is required.

Settings → Uninstall & restore (or `--uninstall --wine-prefix ... --wine ...`)
restores original registry settings/defaults and replaced DLLs. It keeps voices
and preferences. Native Windows system SAPI is never replaced: extract the
Windows ZIP, use the same control panel/tray, and register with `--install` from
an administrator terminal. Windows data/config are under LocalAppData/OpenSAPI.

Language routing uses SAPI hints or a manually selected book language; automatic
foreign-word detection and full localisation are not implemented. Standard Piper
has no general pitch slider. Arabic/Hebrew auxiliary models are not distributed
and those languages remain unavailable in this program-only beta. Model licences
vary; upstream cards and provenance are retained when downloading.

Sources/licences accompany the release: engine LGPL-2.1-or-later; panel/Piper
GPL-3.0-or-later; Qt/PySide LGPL-3.0 and third-party notices. The source archive
includes matching Wine, Piper, eSpeak, Qt and PySide sources. Automated deterministic
WAV checks, real Piper output and session tests do not establish audible playback
or every Logos desktop behavior; test in a backed-up prefix.

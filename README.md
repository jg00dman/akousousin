# Akousousin — Neural Voice Engine

**akousousin:** *The unified neural speech engine for Linux, implementing Microsoft SAPI and Speech Dispatcher, based on Piper and Whisper.*

This is the project vision. The current beta implements SAPI text-to-speech with
Piper. This development branch adds experimental Speech Dispatcher output,
on-demand startup and idle model unloading. This Whisper branch also develops local recognition and KDE Wayland dictation; live desktop acceptance testing is pending.
See [branch testing instructions](standalone/SPEECH-DISPATCHER.md); the published
0.5 beta does not include these additions.

The name comes from Greek **ἀκούσουσιν**, “they will hear” (John 5:25).

| Capability | Current status |
| --- | --- |
| SAPI TTS in existing 64-bit Wine prefixes | Working beta; Logos Read Aloud, speed and navigation desktop-tested |
| Native Windows 64-bit SAPI TTS | Working beta; integration, failure/recovery and real Piper WAV tests in CI |
| Local Piper synthesis and bundled LJSpeech starter voice | Working beta |
| Shared per-user service, tray, voice library and session lifecycle | Working beta |
| Manual voice/book-language selection | Working beta; German reading tested |
| Automatic application-language hints | Partial; Logos language selection needs further investigation |
| Speech Dispatcher output module | Experimental on this branch; desktop validation pending |
| Streaming TTS, complete pause/resume and stream/word events | Not complete; future work |
| Whisper CPU recognition and Voice Input panel | Experimental on whisper; model import and diagnostic recording desktop-tested |
| KDE Wayland shortcut dictation and guarded text insertion | Implemented on whisper; private protocol/state tests pass, live KDE acceptance pending |
| SAPI recognition | Planned |
| macOS deployment, 32-bit callers and full UI localisation | Not currently supported |

See [COMPATIBILITY.md](COMPATIBILITY.md) for evidence, limits and the distinction
between deterministic audio tests, neural synthesis and audible desktop playback.

## Try the beta

Download the [Linux AppImage or Windows ZIP](https://github.com/jg00dman/akousousin/releases).
[Installation and configuration instructions](standalone/README.md) cover paths,
voices, Wine-prefix registration, launcher commands and rollback.

The Linux package contains the voice engine, control panel, tray and Piper backend,
plus the reviewed `en_US-ljspeech-medium` starter voice. It does not contain Wine.
Existing voice choices are preserved. Other models retain their own licence terms.
The build target remains x86-64 Linux with glibc 2.35+ (Ubuntu 22.04), and existing
working 64-bit Wine prefixes. Native Windows system SAPI is not replaced.

Akousousin uses one configuration per user. On Linux, config is under
`~/.config/Akousousin`, the AppImage and downloaded voices under
`~/.local/share/Akousousin`, and logs under `~/.local/state/Akousousin`.
XDG overrides are respected. Closing the panel leaves speech running; Quit stops
Piper and exits the resident application. Application sessions are managed through
the public launcher interface. OuDedetai stores only its Enable speech preference.

## Implementation and validation

The standalone [engine](engine/) implements public Windows COM/SAPI interfaces.
Those standard API names and contracts are unchanged by the project rebrand.
The [control panel and controller](standalone/) manage voices and backend sessions.
[CI](.github/workflows/standalone.yml) cross-compiles the engine and tests packages
on Wine and Windows without compiling Wine. It retains the 13 deterministic
integration tests, seven failure/recovery tests, real Piper WAV generation,
GUI launch, concurrent sessions, shutdown/restart and uninstall restoration.

The [Wine patches](patches/) and [Wine build workflow](.github/workflows/appimage.yml)
remain available for custom Wine builds. Wine compilation belongs in GitHub Actions,
not the cloud development environment. Matching sources and licence notices
accompany downloadable packages. Engine code is LGPL-2.1-or-later; panel/service
and Piper are GPL-3.0-or-later; dependency and voice notices are included.

This branch develops Speech Dispatcher output, lower first-audio latency and
service reliability. Complete streaming and accurate word events remain future
work; word offsets must be mapped to real model alignment data. Recognition is
separately scoped.

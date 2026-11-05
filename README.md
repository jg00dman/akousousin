# Akousousin — Neural Voice Engine

**akousousin:** *The unified neural speech engine for Linux, implementing Microsoft SAPI and Speech Dispatcher, based on Piper and Whisper.*

**Published beta: [0.6.0b2](https://github.com/jg00dman/akousousin/releases/tag/standalone-beta-0.6.0b2-41949762674-1).**
Core speech output works through 64-bit SAPI (Wine and native Windows) and the
native Linux Speech Dispatcher output module. On-demand startup, idle model
unloading and control-panel update checks are shipped. Neither interface has
full API coverage; recognition is not included in this beta.

The **`whisper` development branch** adds local Whisper recognition, a Voice Input
panel and KDE Wayland shortcut dictation. Microphone discovery, diagnostic recording
and dictation into Kate and this chat's text box have been desktop-tested on Kubuntu
26.04 Wayland. These input features are experimental and separate from the published
beta. See [Whisper trial instructions](recognition/PANEL-TESTING.md) and
[dictation implementation and acceptance checks](recognition/DICTATION.md).

The name comes from Greek **ἀκούσουσιν**, “they will hear” (John 5:25).

| API area | Implemented | Partial / remaining |
| --- | --- | --- |
| SAPI engine integration | COM activation, voice tokens/enumeration, `ISpTTSEngine` and `ISpObjectWithToken` | Application-facing SAPI is supplied by Windows/Wine; not a complete SAPI implementation |
| SAPI speech output | Text/Unicode, voices, rate, volume, silence, async host use, cancellation and cold startup | Language hints and limited XML effects; full pause/resume, skip, word events, pitch, phonemes/visemes and general SSML incomplete or unsupported |
| Speech Dispatcher output | Server audio, voice/language selection, rate/volume, text, characters/keys, cancellation and lifecycle events | Daemon owns queues/priorities; no separate speechd server |
| Orca and reading feedback | SSML text/entities, coarse index marks, punctuation and spelling fallback | Exact word highlighting, full resume-position validation, localized symbols and sound icons remain |
| Shared runtime and updates | Piper, voice library/preferences, on-demand loading, idle unloading, optional registration, update checks and Linux AppImage updates | Windows ZIP/source updates use manual downloads; speechd pitch and functional debug/log-level controls are absent |
| Speech input | Not included in the published beta | SAPI recognition and a future native input API are separately scoped |

See **[API coverage and implementation status](COMPATIBILITY.md)** for the
command/interface matrix, unsupported operations and validation evidence.
We report feature coverage rather than an invented percentage of the full APIs.

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
`~/.config/Akousousin`, downloaded voices under `~/.local/share/Akousousin`,
and logs under `~/.local/state/Akousousin`. The AppImage runs wherever you place
it; `~/.local/share/Akousousin/Akousousin-x86_64.AppImage` is the recommended path.
XDG overrides are respected. Closing the panel leaves speech available; Quit stops
Piper and exits the resident application. SAPI can start speech on demand without
launcher lifecycle hooks. An optional session interface remains available to clients.

## Implementation and validation

The standalone [engine](engine/) implements public Windows COM/SAPI interfaces.
Those standard API names and contracts are unchanged by the project rebrand.
The [control panel and controller](standalone/) manage voices and backend sessions.
[CI](.github/workflows/standalone.yml) cross-compiles the engine and tests packages
on Wine and Windows without compiling Wine. The released build passed 60 standalone and 8 backend tests, plus packaged
Wine/Windows checks covering 14 deterministic integration tests, seven failure
tests, real Piper output, GUI/service lifecycle, registration refresh and rollback.
Linux checks also exercise a real speechd daemon and verified AppImage updating.

The [Wine patches](patches/) and [Wine build workflow](.github/workflows/appimage.yml)
remain available for custom Wine builds. Wine compilation belongs in GitHub Actions,
not the cloud development environment. Matching sources and licence notices
accompany downloadable packages. Engine code is LGPL-2.1-or-later; panel/service
and Piper are GPL-3.0-or-later; dependency and voice notices are included.

The next output milestones are exact alignment-backed word events, more complete
pause/resume behaviour and broader speech markup/accessibility support.
SAPI recognition and a future native input framework remain separately scoped. See the
[Speech Dispatcher desktop checklist](standalone/SPEECH-DISPATCHER.md#desktop-acceptance-checklist)
for ongoing Orca and application testing.

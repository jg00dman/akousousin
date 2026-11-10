<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# API coverage and implementation status

Applies to main's **0.7.0b11 beta**, reviewed on 10 November 2026.
[Releases and downloads](https://github.com/jg00dman/akousousin/releases).

**Complete native Windows app support is forthcoming, not yet working end to
end.** The ZIP is experimental; user testing found voice installation and
Whisper model-install failures. Windows microphone capture, global shortcuts
and desktop dictation integration remain unimplemented. SAPI output coverage
below describes that component, not complete application readiness. See the
[Windows work plan](standalone/WINDOWS-PLAN.md).

**Core speech output works through SAPI and Speech Dispatcher; neither is a
complete implementation of its wider API. Linux Whisper voice input is experimental.
It does not implement SAPI recognition.**
There is no defensible overall coverage percentage: SAPI includes recognition and
many runtime interfaces, and our Speech Dispatcher component is an output module,
not a replacement for the daemon or its client API. Feature coverage follows.

## Microsoft SAPI

Akousousin implements a 64-bit COM TTS engine. Windows or Wine provides the
application-facing SAPI runtime (`ISpVoice`, automation, audio sinks and queues).
The engine implements `ISpTTSEngine` (`Speak`, `GetOutputFormat`) and
`ISpObjectWithToken` (`SetObjectToken`, `GetObjectToken`), with COM lifetime/class
factory support. Implementing these interfaces does not imply full support for
all speech fragment actions or the rest of SAPI.

| Capability / contract | Coverage in this beta | Evidence or limit |
| --- | --- | --- |
| COM activation, voice tokens, default voice and voice enumeration | Implemented | Wine and native Windows integration checks; 64-bit callers only. |
| Plain text and Unicode synthesis (`SPVA_Speak`) | Implemented | Piper synthesis; UTF-16 conversion and bounded chunks preserving surrogate pairs. Logos Read Aloud desktop-tested. |
| Synchronous / asynchronous application speech | Supported through host SAPI | Async and automation tests pass; the host supplies `ISpVoice`/automation, not Akousousin. |
| Explicit silence (`SPVA_Silence`) | Implemented | PCM silence fragments tested. |
| Output format negotiation / audio delivery | Implemented, limited format | Mono 16-bit PCM at the registered voice rate; validated WAV data and partial sink writes. Other engine output formats are unsupported. |
| Rate and volume | Implemented | Host rate/volume and fragment adjustments; rate is approximate and read per text chunk. Volume includes sink-time scaling. |
| Voice/language selection | Partial | Explicit voices, LCID hints and shared language preferences work. Automatic Logos language hints remain under investigation; no language guessing for individual words. |
| Abort / purge / cancellation | Implemented | Abort during network/output and request-specific inference cancellation; failures and recovery tested. |
| Cold startup and idle model unloading | Implemented | SAPI starts the service when needed; idle reload tested. No launcher lifecycle management is required. |
| SSML / XML effects | Partial, through host parsing | Text, silence, rate and volume fragments work. This is not general SSML support. |
| Pause/resume and skipping | Incomplete / unverified | Host audio behaviour may help, but complete compatibility is not established; the engine does not implement skip handling. |
| Word/sentence/bookmark/phoneme/viseme events | Not implemented by the engine | No engine `AddEvents` output. Host-generated lifecycle notifications do not establish accurate word timing or highlighting. |
| Pitch, pronunciation/phoneme input, spelling fragment actions, bookmarks and custom lexicons | Not implemented | Engine accepts speak/silence actions; other fragment actions return `E_NOTIMPL`. |
| Sample-by-sample synthesis streaming | Not implemented | Short text requests lower first-audio latency; each backend response is a complete WAV. |
| Recognition (`ISpRecognizer`, `ISpRecoContext`, grammars and recognition events) | Not implemented in this beta | Local Whisper dictation is separate from the unimplemented SAPI recognition interfaces. |

Source: [engine/piper.c](engine/piper.c), [COM support](engine/com.c),
[integration tests](tests/test_integration.py),
[failure/recovery tests](tests/test_failures.py).

## Speech Dispatcher (`speechd`)

Akousousin plugs into the distribution's existing Speech Dispatcher daemon.
The daemon provides SSIP/client connections, native queues, priorities and audio
playback. Akousousin implements the output-module side and returns PCM/events
through that same connection. It does not implement a second speechd server.

| Module command / capability | Coverage in this beta | Evidence or limit |
| --- | --- | --- |
| `INIT`, framing, settings handshake, `QUIT` and error replies | Implemented | Protocol/unit checks plus real-daemon packaged tests. |
| `AUDIO` / server audio | Implemented | Escaped mono 16-bit PCM is delivered to the daemon for playback. Direct module ALSA/PulseAudio playback is unsupported. |
| `SPEAK` | Implemented | Plain text and the Orca SSML subset described below. Chunked complete-WAV synthesis, not true streaming. |
| `LIST VOICES`, synthesis voice and language selection | Implemented | Installed voices, language filtering, case-insensitive language tags and regional fallback. Shared preferences apply. |
| `SET`: rate and volume | Implemented | Per-request controls combine with shared preferences. |
| `CHAR`, `KEY`, spelling and capitalization spelling | Implemented with fallback | English/Unicode symbol names; localized symbol dictionaries and capitalization icons are incomplete. |
| Punctuation `none`, `some`, `most`, `all` | Implemented with fallback | Includes speechd 0.12's `most` mode used by Orca. Fallback is not a complete localized punctuation dictionary. |
| Orca SSML text, entities and index marks | Partial | Markup is not spoken. Real marks are emitted at synthesis boundaries; intermediate word marks are omitted. General SSML/prosody is unsupported. |
| `701 BEGIN`, `702 END`, `703 STOP`, `704 PAUSE`, `700` marks and `705` audio | Implemented | Daemon queues audio/marks for playback. Marks are coarse, not exact per-word timings. |
| `STOP` / cancellation and recovery | Implemented | Prompt cancellation, late-audio suppression and request-scoped inference cancellation; real-daemon recovery tested. |
| `PAUSE` / resumed reading position | Partial | Module cancels current work and reports pause; the daemon resubmits text using its mark context. Full suspend/resume and precise Orca position are not established. |
| Priorities / interruption | Delegated to daemon | Native speechd priorities are not a global priority policy for SAPI playback. |
| `SET`: pitch / pitch range | Accepted, not applied | Piper has no general pitch control. |
| `LOGLEVEL`, `DEBUG` | Acknowledgement only | No functional module log-level/debug configuration; `DEBUG` reports debugging off. |
| `SOUND_ICON` | Unsupported | Returns an explicit unsupported error. |
| Native speech input / recognition | Outside this interface | Speech Dispatcher is an output interface; a future desktop-independent input API is separate. |

Source: [output module](standalone/akousousin_app/speech_dispatcher.py),
[module tests](standalone/tests/test_speech_dispatcher.py),
[real-daemon test](standalone/ci_speech_dispatcher.py).

## Shared service, platform support and validation

- Both output interfaces share Piper, voices and saved voice/language/speed/volume
  preferences. One inference worker is shared with bounded, cancellable waiting.
  Results and cancellation stay on the requesting interface/request; audio playback
  remains independent between SAPI and speechd.
- The panel supports voice import/download, shared preferences, service controls,
  optional SAPI/speechd registration and application update checks. Linux AppImages
  provide optional weekly checks, stable/beta selection, explicit installation
  and updates with verification and rollback; Windows ZIP/source builds
  use their installation source; Flatpak/distro builds defer to their software manager. speechd install/remove restarts the user
  service and reports restart failures.
- Supported packages: Linux x86-64/glibc 2.35+ with existing 64-bit Wine prefixes,
  and native Windows x86-64. macOS deployment, 32-bit callers and full UI
  localization are not supported in this beta.
- Earlier build [41949762674](https://github.com/jg00dman/akousousin/actions/runs/41949762674)
  passed 60 standalone tests and 8 backend tests on Linux; packaged validation on
  Wine and native Windows includes 14 deterministic integration and 7 failure tests,
  real Piper/SAPI audio generation, cold startup/idle reload, service/panel lifecycle,
  registration refresh and uninstall restoration. The Linux run also checks real
  speechd PCM delivery, cancellation/recovery, SSML marks and packaged updating.
- The user confirmed native speech works on Kubuntu 26.04 / KDE Wayland with Orca
  50.3, speechd 0.12.1 and AT-SPI2 2.60.4; testing was not exhaustive. Orca 50.3
  markup and speechd 0.12.1 source were reviewed. CI uses Ubuntu 22.04's dispatcher,
  so it does not establish complete conformance on every desktop/version.

These are functional test results, not API-conformance or line-coverage
percentages. Generated WAV/PCM checks do not establish audible desktop playback.
See the [desktop checklist](standalone/SPEECH-DISPATCHER.md#desktop-acceptance-checklist)
for the remaining interaction/listening checks. Development branches may contain
additional work; those features are not implied by this beta's coverage.

## Experimental Linux voice input

| Capability | Coverage and limits |
| --- | --- |
| Local recognition | faster-whisper, multilingual Small, CPU int8, two inference threads and neural VAD. Turbo can be imported; missing/broken Turbo falls back to Small when available. |
| Persistent models | First activation can download pinned Small; imported/downloaded weights remain in the XDG-aware `~/.local/share/Akousousin/models/whisper/` cache. AppImage updates do not bundle or remove those weights. |
| Language selection | Automatic detection with the last detected language displayed; searchable/scrollable explicit language selection locks recognition. Accuracy varies; no guarantee of reliable recognition for every supported language. |
| Microphone capture | PulseAudio-compatible `parec` capture through PipeWire/PulseAudio, named input selector and system default. Native Windows microphone capture is not implemented. |
| Model and recording controls | Enable/Disable voice input manages recognition and model memory. Recording and an already-approved shortcut can enable/load it again. Disable retains downloaded files; idle unloading retains enabled state. |
| KDE Wayland dictation | GlobalShortcuts and keyboard-only RemoteDesktop portals, plus a temporary KWin focus observer. Tray Start Dictation can initiate consent. Other compositors are not supported by this adapter. |
| Insertion and focus | Unicode key events without automatic Enter/Tab or clipboard paste. Focus changes retain transcripts; a scheduling race may leave partial insertion. Individual fields/cursor positions inside one window are not tracked. |
| Cancellation and Quit | Bounded audio queue, cancellable recognition/download worker, and capture cleanup. Normal Quit closes owned control panels, speech/input workers and portal sessions. The updater temporarily preserves only its own panel to finish replacement. |
| Ready cue and UI | Two 300 Hz tones, a separate sound test, wheel scrolling and scrollbars. Cue amplitude is about +10.3 dB over the earlier trial, limited below PCM clipping. |
| Spoken punctuation and language tagging | Whisper may infer punctuation. Spoken phrases such as “question mark” can remain literal; command interpretation and word-processor proofing-language tags are not implemented. |

The user confirmed microphone selection, the ten-second recording button and
KDE Wayland insertion into Kate and a chat text box. A valid launcher was initially
missing from the running portal's view; restarting `xdg-desktop-portal.service`
resolved it. The controller now installs identity earlier and retries transient
lookup failures. The ready cue was audible after the earlier volume adjustment;
the latest 300 Hz/max-clean-level cue still needs a listening check.

French was recognized in a reported test; Hebrew and Greek were not recognized
in that test. These observations are not a language-conformance assessment.
Push-to-talk, non-Latin insertion, focus changes, lock/unlock, speech feedback,
physical device failures and fifth-generation i5 performance need broader desktop
testing. See [dictation acceptance details](recognition/DICTATION.md).

## Global reading and control panel

The 0.7.0b1 release adds controller-owned selected/copied text reading through
Speech Dispatcher. KDE Wayland portal shortcuts suggest Ctrl+Alt+R and
Ctrl+Alt+Shift+R, with actual bindings approved by KDE. Reading works with the
panel closed while AKS runs. Repeat-to-stop and Quit stop only the AKS reader;
other clients are not globally cancelled. Wayland requires `wl-clipboard`; the
optional X11 desktop action requires `xclip`. Wine applications may need the
explicit copied-text action; there is no silent stale-clipboard fallback.

Configure reuses a single panel. Tray left-click toggles dictation; right-click
opens its menu. Copyable recovery commands and separate diagnostics are provided.
The panel is Tkinter, while the tray/controller uses PySide6 (Qt 6). Output-module
Orca support does not imply that Orca can read the panel; comprehensive panel
accessibility remains future work.

Release [42318174159](https://github.com/jg00dman/akousousin/actions/runs/42318174159)
passed Linux and Windows package checks, including private SAPI registration and
restoration, model-free packaging, real synthesis, panel reuse/shutdown, portal
protocol checks and real Speech Dispatcher reading/cancellation. Native/Wine
selection availability and global key dispatch still need target-desktop testing;
see the [current beta checklist](standalone/BETA-TESTING.md).

## Private Wine SAPI compatibility installation

For supported Wine 11.21 prefixes requiring the enumeration workaround, the
compatibility DLL lives at `C:\Program Files\Akousousin\compat\x64\sapi.dll`.
Standard Wine SAPI COM registrations are directed to that private file with a
prefix-level `native,builtin` override. The installer does not change prefix PATH
or replace Wine's system SAPI files. Other SAPI-named COM servers outside the Wine
system/AKS locations are left alone.

Original COM default-value types/data and the override are recorded and restored
on rollback/uninstall. Updates refresh an already-installed private compatibility
DLL even when the probe succeeds. Installer file writes are restricted to the AKS
directory. Existing system-DLL installations are outside this change's scope.

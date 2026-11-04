# Implementation status

This table describes the current beta. Planned interfaces are part of the roadmap,
not capabilities advertised as available in the current release.

| Interface / capability | Status | Evidence and limits |
| --- | --- | --- |
| Microsoft SAPI text-to-speech through Wine | Working beta | Logos Read Aloud tested on Kubuntu; speed and navigation tested. 64-bit existing prefixes. |
| Native Windows SAPI text-to-speech | Working beta | 64-bit COM engine; deterministic, failure/recovery and real Piper WAV tests in Windows CI. Wider application testing remains necessary. |
| Piper local neural synthesis | Working beta | Local inference; the reviewed LJSpeech medium starter voice is bundled. |
| Voice library, defaults and synthesis preferences | Working beta | Import/download, manual voice selection, speed, volume and synthesis variation. Individual model licences apply. |
| Shared per-user service and system tray | Working beta | Application sessions, start/stop, automatic cleanup and independent/manual operation. Desktop tray support varies. |
| Manual book-language selection | Working beta | Tested with German reading in Logos. |
| Automatic language changes from application hints | Partial / under investigation | SAPI language hints are supported; Logos did not automatically select German in the reported Bible test. No isolated-word language detection. |
| Failure handling and cancellation | Implemented / tested | Missing voice, backend unavailable/interrupted, malformed audio, server failures, bounded transport and cancellation have automated checks. |
| Streaming synthesis to reduce initial latency | Planned | The current backend returns complete WAV responses. |
| Full SAPI pause/resume and stream/word events | Not complete | Current async, rate, volume and cancellation tests do not establish complete SAPI event or pause/resume compatibility. |
| Speech Dispatcher output module | Next implementation milestone | Native Linux bridge is not implemented yet; requires output-module protocol, cancellation, event and screen-reader tests. |
| Whisper local recognition | Planned | No recognition model or microphone capture is currently included. |
| SAPI speech recognition (`ISpRecognizer`, `ISpRecoContext`) | Planned | Whisper transcription alone will not implement SAPI grammars, recognition contexts or events. |
| Native Linux dictation integration | Planned | Wayland and X11 text insertion require supported desktop-specific integration. |
| macOS deployment | Planned | No current macOS package or validation. |
| 32-bit SAPI callers / fresh WoW64 .NET installation | Not supported in this beta | Current packages target 64-bit callers and existing working prefixes. |
| Full UI localisation | Planned | Readable language names are available; the UI is currently English. |

Deterministic audio checks exercise protocol and PCM behavior with a substitute
backend. Real Piper WAV tests establish neural audio generation. Neither is a
substitute for audible playback and application testing on the user's desktop.

# Speech Dispatcher and on-demand speech: development branch

This branch is experimental. Keep your working beta until its packaged CI and
application tests pass. Ubuntu 22.04 remains the Linux build target; no Wine build
is required. Speech recognition, phonemes and visemes remain outside this change.

## SAPI startup and idle memory

Install/apply voice registration using this branch's package as usual, with
Logos closed. The registered engine records the package's launcher and your
settings path. Keep the AppImage at that location; if you move it, apply voice
registration again. Native Windows registers its installed executable.

A SAPI speech request starts the shared controller/backend if the connection is
unavailable. Startup is bounded and cancellable; a missing executable or model
returns an error. A failed synthesis response is not retried automatically.
OD may still start speech in advance; its existing session interface is unchanged.

Settings → Advanced synthesis → **Unload Piper after idle seconds** defaults to
300 seconds. Set 0 to retain the model. Idle expiry unloads the inference worker
and model, retaining the small controller and HTTP listener so the next request
can reload them. Health checks do not count as speech. Active synthesis is never
interrupted by idle expiry. The timeout also applies to manually started services;
explicit Stop/Quit still stop the backend. Closing the panel still leaves it running.

Long SAPI fragments are requested and played in bounded chunks. This reduces
first-audio waiting for long text, but is not sample-by-sample streaming, and chunk
joins/prosody need listening tests. It does not generate estimated word timings.
Accurate word events require an alignment source; current Piper model output
does not provide it. Full pause/resume and word highlighting remain incomplete.

## Install the Linux module

Install your distribution's Speech Dispatcher package first. Put the AppImage in
its permanent location, then run:

```sh
/path/to/Akousousin-x86_64.AppImage --install-speech-dispatcher
```

This creates a user-owned launcher in `$XDG_DATA_HOME/Akousousin` (normally
`~/.local/share/Akousousin`) and adds an `AddModule` entry to your user
`$XDG_CONFIG_HOME/speech-dispatcher/speechd.conf`. Existing settings and the default
output module are preserved. Restart your user Speech Dispatcher service, then:

```sh
spd-say -o akousousin -w 'Testing Akousousin through Speech Dispatcher.'
spd-say -o akousousin -L
```

Select the module in your screen reader's speech settings when ready. Synthesis
uses the same voice library/defaults as SAPI. Explicit synthesis voice and language
selection, rate and volume are supported. Piper has no general pitch control;
pitch, punctuation and spelling transformations are not implemented by this module.
Sound icons and SSML/index marks are not implemented. Plain text, character and
key requests are accepted. Do not enable this as your sole accessibility voice
until you have tested stop, priorities and recovery on your desktop.

Audio is delivered through Speech Dispatcher's server-audio protocol, allowing it
to own playback and priority handling. Direct ALSA/PulseAudio output from the
module is intentionally unsupported. STOP/PAUSE cancel the current request;
Speech Dispatcher is responsible for resubmitting remaining text on resume.
Model inference is cancelled only for the matching random request id; cancelling
one caller must not stop another caller's synthesis. Busy requests return an
error instead of creating an unbounded queue.

To remove module registration, remove the `AddModule "akousousin"` line from your
user speechd.conf and delete `~/.local/share/Akousousin/speech-dispatcher-module`.
Restart Speech Dispatcher. This leaves other modules and Akousousin settings intact.

## Validation

CI retains all original 13 integration and seven failure/recovery tests on Wine
and native Windows, plus long-fragment integrity, SAPI-triggered cold startup and
idle reload tests. Unit checks cover module framing/escaping, voices, cancellation,
idle expiry, backend recovery and preserving the user's dispatcher configuration.
Real Piper WAV generation is distinct from audible playback. Desktop screen-reader
and Logos listening checks are still required before promoting this branch.

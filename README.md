# OpenSAPI: Piper speech for Wine (beta)

For a step-by-step test session, start with [TESTING.md](TESTING.md).

Download the [Wine deployment beta](https://github.com/jg00dman/opensapi/releases/tag/piper-test-41391312177-1)
for an existing working 64-bit Logos/.NET prefix. It includes the AppImage,
checksums, matching patched Wine source, every patch and validation logs.
No local Wine compilation is needed.

The separate [Piper backend and bundled LJSpeech voice](https://github.com/jg00dman/opensapi/releases/tag/piper-backend-41388556427-1)
includes its Python runtime, Piper 1.8.0 and Waitress 3.0.2, with licence notices,
pinned voice provenance and corresponding sources. It remains outside Wine.
The [OuDedetai integration beta](https://github.com/jg00dman/OuDedetai/releases/tag/piper-beta-41389712590-1)
adds optional Install/Configure/Start/Stop/Disable controls and Logos lifecycle
management. See [backend instructions](backend/README.md) and
[deployment validation](DEPLOYMENT.md).

All 13 original deterministic tests and seven failure/recovery cases passed
against both Wine runtimes. The actual AppImage, frozen backend and bundled voice
also produced a non-silent speech WAV in CI; it is a separate release asset.
OuDedetai passed all 96 CI tests (16 existing skips). Downloads were independently
checksum-verified. Real neural WAV generation is distinct from audible playback.

The earlier working beta was desktop-tested on Kubuntu 26.04: Logos Read Aloud,
speed controls and jumping back worked. This deployment candidate still needs
Logos desktop checks with missing, stopped and restarted speech components.
See [TESTING.md](TESTING.md) for the manual Wine test workflow. The
[workflow](https://github.com/jg00dman/opensapi/actions/workflows/appimage.yml)
publishes uniquely tagged prereleases after its checks; an in-progress run is
not a completed release.

This prototype adds an opt-in SAPI TTS engine to Wine. Windows applications keep
using `ISpVoice` or `ISpeechVoice`; the engine calls a separately running Piper
1.8 HTTP server on `127.0.0.1`. Piper returns WAV audio, which the engine validates
and writes through SAPI's existing output stream. Speech recognition is out of scope.

The Wine changes are LGPL-2.1-or-later and contain no Piper implementation code.
Piper is GPL-3.0-or-later and remains a separate installation/process. Voice models
have their own licenses. This separation is an engineering choice, not a claim
that Wine maintainers have accepted this design or that redistribution obligations
have been settled for any particular bundle.

## Patch and build

CI uses the full `FaithLife-Community/wine` `logos-11.21` branch pinned at
`3b19eb0e45ac5f57301073fc9e721cac7829dc93`, including both WineD3D regression reverts, then applies the OpenSAPI patches. See
[Wine source provenance](scripts/ci/WINE-SOURCE.md) for all 17 branch commits.

The Piper patch also applies to clean upstream Wine 11.21 at
`2528aff26208257fdbf980666a4f0e66d47563ce`. To reconstruct the combined build from
that upstream revision, apply `patches/wine-logos-11.21.patch` first. On a clean
copy of the pinned Logos branch, apply the complete patch stack in this order:

```sh
for patch in wine-piper.patch wine-sapi-enum-values.patch wine-piper-site-write.patch wine-piper-lifecycle.patch; do
    git -C /path/to/wine apply "/path/to/opensapi/patches/$patch"
done
```

Configure and build Wine using its normal prerequisites and platform options.
No Piper headers or libraries are required to build Wine. The new engine uses
nonblocking loopback Winsock calls as a delayed import in the deployment candidate. A normal desktop build should
include an audio driver; a headless build can still synthesize to WAV files.

For an already configured Wine build, rebuild the DLL with:

```sh
make -C /path/to/wine-build -j4 dlls/sapi/all
```

This DLL needs the rest of the matching Wine runtime to run. Do not assume it can
be copied into an unrelated older Wine build.

## Start Piper

Prefer the prebuilt backend above. For a manual development setup, the following
commands use upstream Piper. The bundled voice selection and its licence basis
are documented separately in backend/README.md:

```sh
python3 -m venv /path/to/piper-venv
/path/to/piper-venv/bin/pip install 'piper-tts[http]==1.8.0'
/path/to/piper-venv/bin/python -m piper.download_voices \
    --download-dir /path/to/voices en_US-ljspeech-medium
/path/to/piper-venv/bin/python -m piper.http_server \
    --host 127.0.0.1 --port 5000 \
    --model /path/to/voices/en_US-ljspeech-medium.onnx
```

The official Piper 1.8.0 HTTP command uses Flask's development server, which
prints a production-deployment warning. These commands are for a loopback-only
experimental desktop test. A production background service should use a WSGI
server such as [Waitress](https://flask.palletsprojects.com/en/stable/deploying/waitress/)
with a compatible launcher; Piper 1.8.0 constructs its app inside `main()` and
exports no ready-made `app`/factory target. The separate backend package now provides and tests a Waitress service with
bounded synthesis and worker recovery. No Wine rebuild is needed to change the
external HTTP runner while retaining the same `/synthesize` JSON-to-WAV API.

Keep the server bound to loopback. Test it independently:

```sh
curl --fail --noproxy '*' http://127.0.0.1:5000/info
curl --fail --noproxy '*' -H 'Content-Type: application/json' \
    -d '{"text":"Hello from Piper"}' \
    http://127.0.0.1:5000/synthesize -o piper-direct.wav
```

The engine always calls `/synthesize` on `127.0.0.1`, bypasses HTTP proxy settings,
and refuses redirects. It does not send text to a remote speech service.

## Register a voice and try it

Use the patched loader, and start with a dedicated Wine prefix. Registration is
opt-in: building Wine alone neither adds a voice nor changes existing defaults.

```sh
export WINE=/path/to/wine-build/wine
export WINEPREFIX=/path/to/new-opensapi-prefix
"$WINE" wineboot.exe -u
python3 scripts/register-voice.py \
    --config /path/to/voices/en_US-ljspeech-medium.onnx.json \
    --make-default --output /tmp/piper-voice.reg
"$WINE" regedit.exe /S 'Z:\tmp\piper-voice.reg'
```

`--make-default` explicitly replaces Wine's `DefaultDefaultTokenId` value in this
prefix. Omit it to leave the default alone and select Piper in the application.
The script uses a single stable token, `OpenSAPI-Piper`; rerunning it updates that
token. Wine registers the private engine class at the installed SAPI DLL path
during prefix initialization/update. The sample rate is
read from the model configuration and must match the running server. Set
`--language` to the voice's hexadecimal SAPI language ID (default `409`, US English)
and `--port` if the server uses another port.

Build the diagnostic programs with MinGW-w64 and the configured Wine headers:

```sh
WINE_SRC=/path/to/wine WINE_BUILD=/path/to/wine-build sh scripts/build-probes.sh
"$WINE" build/sapi-probe.exe 'Z:\tmp\sapi.wav' 0 100 'Hello from SAPI and Piper'
"$WINE" build/sapi-probe.exe unused.wav 0 100 'Read this aloud' play
```

The WAV test exercises voice enumeration, explicit voice selection, engine
creation, synthesis, output negotiation, and stream output. It uses
`ISpStream::SetBaseStream` and adds a WAV header to the resulting PCM;
`ISpStream::BindToFile` is still a stub in this Wine tree. The `play` mode uses
Wine's default audio device. Other modes are `async`, `xml`, `default`, and
`automation`. The last one also exercises the automation voice API.

## Regression tests

```sh
WINE=/path/to/wine-build/wine sh scripts/test-wine.sh
```

This creates a marked disposable prefix under `build/test-prefix`, registers a
test voice, and runs the integration suite. It refuses to modify an existing
unmarked prefix. Port 5000 must be free: tests start their own deterministic HTTP
server, not Piper. The suite uses the actual compiled Wine engine to check PCM
samples, Unicode and JSON escaping, rate and volume, synchronous/asynchronous and
automation speech, SSML prosody, silence fragments, partial sink writes, cancellation during output,
sink failures, HTTP errors/redirects, and malformed or mismatched WAV responses.

These are transport and SAPI integration tests, not proof of neural speech quality.
A real Piper model and a separate real-synthesis smoke test are still necessary.

With a real server running and its voice registered in `WINEPREFIX`, run:

```sh
python3 scripts/smoke-piper.py --config /path/to/voices/en_US-ljspeech-medium.onnx.json
```

This checks direct Piper HTTP output and speech through Wine for the expected
format and non-silent samples, retaining both WAV files for listening. It does not
prove the spoken words or pronunciation are correct.

## Current limits

* One voice per local server/token; no speaker or language switching within text.
* Output is mono, signed 16-bit PCM at the token's configured sample rate. Audio
  with mismatched format is rejected rather than played at the wrong speed.
* SAPI rate -10 through +10 maps approximately to Piper length scale 2 through 0.5.
  Rate changes take effect between fragments; volume changes between output chunks.
* Synthesis buffers each fragment's WAV response, up to 64 MiB, before output.
  Fragments over one million UTF-16 code units are rejected. No persistent response
  cache is used. Large texts should be split into sentences by the caller.
* Cancellation is checked during response reads and PCM writes. A synchronous HTTP
  send/receive/read can delay cancellation until it returns (30-second I/O timeout).
* Speak and silence fragments work. Pronunciation, spell-out, bookmarks, word
  timings, phonemes, and visemes are not implemented. Unsupported fragment actions
  return `E_NOTIMPL`; the engine does not fabricate alignment events.
* This Wine revision separately has stubs for pause/resume and engine-site event
  delivery, and does not parse SAPI XML or SSML break elements. The engine does not
  fix them. Logos has not been tested.
* Desktop playback and 32-bit/WoW64 still need separate validation. The released
  AppImage passed the deterministic build-tree and packaged-runtime CI checks.

The existing `Wine-Builds` and `WINE_AppImage` workflows remain available for a
future WoW64/full bundle. The OpenSAPI workflow builds the patch directly because
the cloud credential cannot push to the Wine fork. It does not bundle Piper or a
voice model. The AppImage wrapper provides explicit voice registration and sample
speech/WAV commands; Piper startup and model installation remain separate.

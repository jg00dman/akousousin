# Experimental Logos-patched Wine/Piper test build

This is a prebuilt Wine 11.21 runtime containing the complete
`FaithLife-Community/wine` `logos-11.21` branch at
`9a962f8799c79149af0be85d8d8f7b92951c1cc5`, plus the experimental OpenSAPI TTS
engine and C sample. See `WINE-SOURCE.md` for all 15 included branch commits. You do not need to compile Wine. Piper and voice models are separate
downloads and are not included in this release.

Requirements: x86-64 Linux, glibc 2.35 or newer (Ubuntu 22.04, Mint 21, Debian 12
or newer), Python 3.9+, and normal Wine host libraries/audio support. This package
does not bundle the distribution's system libraries. It runs 64-bit Windows
programs only. It is not yet a verified Logos build.

## 1. Prepare the AppImage

Download the `.AppImage`, this file, and `SHA256SUMS`. Verify the downloaded file
against its entry in `SHA256SUMS`, then:

```sh
chmod +x wine-opensapi-piper-11.21-logos-x86_64.AppImage
export OPENSAPI_IMAGE="$PWD/wine-opensapi-piper-11.21-logos-x86_64.AppImage"
export APPIMAGE_EXTRACT_AND_RUN=1
export WINEPREFIX="$HOME/.wine-opensapi-piper-test"
"$OPENSAPI_IMAGE" --opensapi-info
```

Extraction mode avoids requiring FUSE. The alternative `.tar.xz` holds the same
folder; extract it into an empty directory and use its `AppRun` instead.
Keep this test prefix separate from your Logos prefix.

## 2. Obtain Piper and a development voice

```sh
python3 -m venv .piper-venv
.piper-venv/bin/pip install 'piper-tts[http]==1.8.0'
mkdir -p voices
.piper-venv/bin/python -m piper.download_voices \
    --download-dir voices en_US-ljspeech-medium
.piper-venv/bin/python -m piper.http_server --host 127.0.0.1 --port 5000 \
    --model "$PWD/voices/en_US-ljspeech-medium.onnx"
```

Keep that terminal open. LJSpeech is a licensing-review candidate, not a model
cleared for redistribution by this project. This release contains no model.

## 3. Test in a second terminal

Shell variables are per terminal. In this second terminal, set them again
(use the directory containing your downloaded AppImage):

```sh
cd ~/opensapi
export OPENSAPI_IMAGE="$PWD/wine-opensapi-piper-11.21-logos-x86_64.AppImage"
export APPIMAGE_EXTRACT_AND_RUN=1
export WINEPREFIX="$HOME/.wine-opensapi-piper-test"
test -x "$OPENSAPI_IMAGE" && "$OPENSAPI_IMAGE" --opensapi-info
```

Keep the Piper server running in the first terminal, then:

```sh
"$OPENSAPI_IMAGE" --opensapi-register "$PWD/voices/en_US-ljspeech-medium.onnx.json"
"$OPENSAPI_IMAGE" --opensapi-wav "$PWD/piper-sapi.wav" 'Hello from Wine and Piper.'
"$OPENSAPI_IMAGE" --opensapi-speak 'Hello from Wine and Piper.'
```

Listen to `piper-sapi.wav` with your normal player as well. If WAV output works
but live playback is silent, inspect Wine's audio configuration:

```sh
"$OPENSAPI_IMAGE" winecfg.exe
```

For diagnostics:

```sh
WINEDEBUG=+sapi,+winhttp "$OPENSAPI_IMAGE" --opensapi-wav "$PWD/debug.wav" \
    'Testing speech output.' >sapi-debug.log 2>&1
```

## Using an existing Logos/.NET test prefix

This build includes every commit from the pinned Logos branch; CI does not
install or launch Logos. Use your existing working Logos/.NET **test** prefix
and its usual launch arguments. Set `WINEPREFIX` to that prefix before registering
the Piper voice and launching Logos with this AppImage. The standalone prefix
above is for the initial audio check and does not contain Logos or native .NET.

Normal AppRun program launches preserve your DLL overrides and native .NET
configuration. Mono/Gecko suppression is scoped to the explicit voice-registration
prefix-initialization command. Native .NET is not installed or bundled by this
package. This runtime still runs 64-bit Windows applications only; it does not
supply WoW64 for 32-bit installers or helpers.

Successful deterministic CI tests do not establish Logos startup, document
rendering, video, printing or Read Aloud. Test those on your Kubuntu desktop.

## What the build verifies

CI additionally runs a registry-value enumeration probe against each runtime,
covering .NET-style voice attributes and enumeration edge cases. Logos desktop
behavior remains a separate test.

CI runs the 13 deterministic integration tests against both the build-tree Wine
and the packaged Wine runtime, plus an AppImage extraction/version/registration
check. CI disables compilation of Wine's unrelated regression test executables;
this does not disable either OpenSAPI integration run. Dependency setup runs in its own job and is retained as a Docker image in the
repository's Actions cache, keyed by the dependency Dockerfile. The image contains
only Ubuntu build dependencies; no credentials, Piper or voice models are included.
It is not uploaded to a public container registry. Change the Dockerfile revision
to refresh its signed distribution packages.

Source, configuration, compilation, installation, probes, both integration runs,
and packaging are separate workflow steps. The compiled source/build directories
are checkpointed immediately after compilation, keyed by the exact Wine base,
patch, configure recipe and verified toolchain image ID. A later test/packaging failure
can reuse that checkpoint on rerun, including after changes to the test or
packaging orchestration. For the inspected upstream-to-Logos transition, CI can restore the upstream/Piper
checkpoint only when the toolchain, configure recipe and Piper patch match. It
verifies ancestry and unchanged configuration/SAPI sources, advances the source
checkout while keeping Piper edits, and lets make rebuild affected dependencies.
The resulting Logos checkpoint is then saved under its own exact source key.
Cache eviction causes a clean rebuild, not a skipped test. No Wine prefix or test result is reused.

Stage output is streamed and retained as log artifacts, compilation uses the
runner's available CPUs, and initialization and integration runs have explicit
time limits. Prefix setup
disables optional Mono/Gecko downloads and dialogs.

These tests use synthetic PCM, not a real Piper voice. A successful build
does not prove neural synthesis, audible playback, or Logos compatibility.

Pause/resume, speech events, word highlighting, and several SAPI XML features
remain unsupported. Stop/cancel may be delayed by a synchronous HTTP request.

The matching patched Wine source archive, Piper patch, complete Logos-branch
diff and `WINE-SOURCE.md` provenance are release assets. The
OpenSAPI source and test instructions are on the `codex/piper-sapi-prototype`
branch of https://github.com/jg00dman/opensapi.

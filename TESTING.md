# Testing the prototype

For a prebuilt AppImage, first check the
[GitHub build](https://github.com/jg00dman/opensapi/actions/workflows/appimage.yml)
and [Releases](https://github.com/jg00dman/opensapi/releases), then follow
[APPIMAGE-TESTING.md](scripts/ci/APPIMAGE-TESTING.md). A successful workflow publishes
a test package that includes the sample program; you do not need to build Wine
locally. [Run 41372784570](https://github.com/jg00dman/opensapi/actions/runs/41372784570) succeeded and
published [this experimental release](https://github.com/jg00dman/opensapi/releases/tag/piper-test-41372784570-1). Both sets of 13 deterministic
integration tests passed. Piper and voice models remain separate; real speech
and audible playback have not been verified by CI.

The rest of this document covers building from source and using the headless
cloud build. Neither the VisualFBEditor sample nor Logos is needed for the first
test.

## Configure the voice in an existing Logos prefix

Close Logos first and keep the Piper server running. In the same terminal,
set `OPENSAPI_IMAGE` to the new `wine-opensapi-piper-11.21-logos-x86_64.AppImage`,
set `APPIMAGE_EXTRACT_AND_RUN=1`, and set `WINEPREFIX` to your actual existing
Logos prefix (the directory containing `drive_c` and `system.reg`). The standalone
speech-test prefix is separate and its voice registration does not carry across.

Keep native .NET and its `mscoree` settings. Set only SAPI to Wine's builtin
implementation, register the engine, and register the voice using your model's
configuration file:

```sh
"$OPENSAPI_IMAGE" reg.exe add 'HKCU\Software\Wine\DllOverrides' /v sapi /t REG_SZ /d builtin /f
"$OPENSAPI_IMAGE" regsvr32.exe /s sapi.dll
"$OPENSAPI_IMAGE" --opensapi-register "$HOME/opensapi/voices/en_US-ljspeech-medium.onnx.json"
"$OPENSAPI_IMAGE" --opensapi-speak 'Testing Piper inside the Logos prefix.'
```

The helper creates
`HKLM\SOFTWARE\Microsoft\Speech\Voices\Tokens\OpenSAPI-Piper` and sets
`HKLM\SOFTWARE\Microsoft\Speech\Voices\DefaultDefaultTokenId`. Manual CLSID
editing is not needed. This intentionally changes the default Wine SAPI voice
in the selected prefix. Then launch Logos itself through this same AppImage and
prefix, preserving the launcher's other settings. Registering with the new
AppImage while launching Logos through an older unpatched Wine will not load
the new engine. If Logos offers a voice selector, choose `Piper (OpenSAPI)`.

For the supplied wine-bisect print launcher, pass the new AppImage as the target
argument: its default still selects the older 11.20 runtime. That launcher also
replaces `WINEDLLOVERRIDES`, so use its `PRINT_DLLOVERRIDES` option to retain
`sapi=b`. In the pasted launcher, `PRINT_WINEDEBUG` is declared but never copied
to `WINEDEBUG`; pass `WINEDEBUG=+sapi,+winhttp` explicitly when capturing speech
traces. Leave native .NET's `mscoree` configuration intact.

If the sample speaks in the Logos prefix but Logos remains silent, capture its
SAPI/WinHTTP diagnostics; that is an application-integration issue to investigate,
not evidence that the standalone speech check validates Logos Read Aloud.

## 1. Recover the source

The handoff archive contains an `opensapi/` directory with the source, Wine patch,
and instructions, plus an `opensapi.bundle` Git backup. Extract it into a directory
of your choice. The bundle can alternatively restore the project with:

```sh
git clone /path/to/opensapi.bundle opensapi
```

For a fresh desktop source checkout, use the exact base revision and apply the
patch once:

```sh
mkdir -p "$HOME/opensapi-test"
cd "$HOME/opensapi-test"
git clone --single-branch --branch logos-11.21 https://github.com/FaithLife-Community/wine.git wine
git -C wine checkout 9a962f8799c79149af0be85d8d8f7b92951c1cc5
git -C wine apply /absolute/path/to/opensapi/patches/wine-piper.patch
```

## 2. Build a desktop Wine runtime

Install Wine's development prerequisites for your distribution, including a
MinGW-w64 x86-64 C compiler, GCC, Make, Bison, Flex, pkg-config, and the development
headers for X11, FreeType, ALSA/PulseAudio, and GnuTLS. Use the repository's build
documentation for distribution-specific package names and optional features.

Then, from the directory containing the `wine` source checkout:

```sh
mkdir wine-build
cd wine-build
../wine/configure --enable-win64 --disable-tests
make -j4
```

Check the configure summary: it must not say that no sound system was found if
you intend to test playback. This full build supplies the locale data, generated
Windows metadata, registrar, and runtime DLLs needed for prefix initialization.
The desktop build commands above have not been executed in this headless cloud
environment; the equivalent targeted headless build and its limitations are
recorded in `VALIDATION.md`.

## 3. Build the sample and run the deterministic tests

In the extracted/cloned `opensapi` directory:

```sh
export WINE_SRC="$HOME/opensapi-test/wine"
export WINE_BUILD="$HOME/opensapi-test/wine-build"
export WINE="$WINE_BUILD/wine"
export WINEPREFIX="$PWD/build/test-prefix"
sh scripts/build-probes.sh
sh scripts/test-wine.sh
```

Expect **13 passing integration tests**. They use a local synthetic-audio server
on port 5000, not Piper. Stop any Piper server on that port before running them.
This verifies transport, audio samples, SAPI/automation calls, and error handling,
but does not prove real speech works. The test prefix is disposable and separate
from your existing applications.

## 4. Install Piper and obtain a development voice

```sh
python3 -m venv .venv-piper
.venv-piper/bin/pip install 'piper-tts[http]==1.8.0'
mkdir -p voices
.venv-piper/bin/python -m piper.download_voices \
    --download-dir voices en_US-ljspeech-medium
```

LJSpeech is a candidate for licensing review, not a cleared redistribution asset.
Download it separately for this experiment; do not publish a bundle containing it
until its exact model card and redistribution terms have been checked. The cloud
environment currently blocks the Hugging Face download, so this real-model step
has not been verified here.

In one terminal, keep Piper running:

```sh
.venv-piper/bin/python -m piper.http_server --host 127.0.0.1 --port 5000 \
    --model "$PWD/voices/en_US-ljspeech-medium.onnx"
```

## 5. Register the voice and test real speech

In another terminal, in `opensapi`, set `WINE` as in step 3. Use a new prefix,
not your Logos prefix:

```sh
export WINE="$HOME/opensapi-test/wine-build/wine"
export WINEPREFIX="$HOME/opensapi-test/piper-prefix"
"$WINE" wineboot.exe -u
python3 scripts/register-voice.py --make-default \
    --config "$PWD/voices/en_US-ljspeech-medium.onnx.json" \
    --output "$PWD/build/piper-voice.reg"
"$WINE" regedit.exe /S "Z:$PWD/build/piper-voice.reg"
python3 scripts/smoke-piper.py \
    --config "$PWD/voices/en_US-ljspeech-medium.onnx.json"
```

The smoke test should report non-silent PCM for both direct Piper HTTP and Wine
SAPI. It saves `build/real-piper/direct.wav` and `build/real-piper/sapi.wav`.
Listen to both with your normal audio player. Then try Wine playback:

```sh
"$WINE" build/sapi-probe.exe unused.wav 0 100 'Hello from Wine and Piper.' play
```

If direct Piper fails, inspect the Piper terminal. If direct output works but SAPI
fails, capture this diagnostic and keep the two WAV files:

```sh
WINEDEBUG=+sapi,+winhttp "$WINE" build/sapi-probe.exe \
    "Z:$PWD/build/debug.wav" 0 100 'Testing Piper through SAPI.' \
    >build/sapi-debug.log 2>&1
```

If the WAVs sound right but `play` is silent, investigate Wine's audio-device
configuration. Pause/resume, speech events, and word highlighting are not yet
implemented; they are not acceptance criteria for this first experiment.

## Historical cloud workspace

These paths refer to the previous development environment, not the current
CI-only cloud setup. The previous workspace used these commands:

```sh
cd /workspace/opensapi
export PATH=/workspace/.build-tools/root/usr/bin:$PATH
export WINE=/workspace/build-wine/wine
export WINEPREFIX=/workspace/opensapi/build/test-prefix-v2
sh scripts/build-probes.sh
sh scripts/test-wine.sh
```

Use the prebuilt AppImage for the current test workflow. The historical source
validation is recorded in `VALIDATION.md`; no Wine compilation is required in
the current cloud environment.

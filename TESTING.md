# Testing the prototype tomorrow

This is a source prototype, not a ready-to-install AppImage. The cloud build can
run automated tests and write WAV files, but has no audio driver. To hear speech,
build the patch into a desktop Wine runtime on your Linux machine as below.
Neither the VisualFBEditor sample nor Logos is needed for the first test.

## 1. Recover the source

The handoff archive contains an `opensapi/` directory with the source, Wine patch,
and instructions, plus an `opensapi.bundle` Git backup. Extract it into a directory
of your choice. The bundle can alternatively restore the project with:

```sh
git clone /path/to/opensapi.bundle opensapi
```

The Wine patch is already applied in the cloud checkout; do not apply it twice.
For a fresh desktop checkout, use the exact base revision:

```sh
mkdir -p "$HOME/opensapi-test"
cd "$HOME/opensapi-test"
git clone --single-branch --branch master https://github.com/jg00dman/wine.git wine
git -C wine checkout 2528aff26208257fdbf980666a4f0e66d47563ce
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
../wine/configure --enable-win64
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

## Existing cloud workspace

You can rerun the already-built deterministic tests here with:

```sh
cd /workspace/opensapi
export PATH=/workspace/.build-tools/root/usr/bin:$PATH
export WINE=/workspace/build-wine/wine
export WINEPREFIX=/workspace/opensapi/build/test-prefix-v2
sh scripts/build-probes.sh
sh scripts/test-wine.sh
```

For real synthesis in the cloud, first apply the saved download-domain changes in
environment settings. See `VALIDATION.md`. Successful cloud WAV synthesis would
still not validate desktop speaker playback.

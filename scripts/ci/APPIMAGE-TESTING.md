# Experimental Wine/Piper test build

This is a prebuilt Wine 11.21 runtime with the experimental OpenSAPI TTS engine
and C sample. You do not need to compile Wine. Piper and voice models are separate
downloads and are not included in this release.

Requirements: x86-64 Linux, glibc 2.35 or newer (Ubuntu 22.04, Mint 21, Debian 12
or newer), Python 3.9+, and normal Wine host libraries/audio support. This package
does not bundle the distribution's system libraries. It runs 64-bit Windows
programs only. It is not yet a verified Logos build.

## 1. Prepare the AppImage

Download the `.AppImage`, this file, and `SHA256SUMS`. Verify the downloaded file
against its entry in `SHA256SUMS`, then:

```sh
chmod +x wine-opensapi-piper-11.21-x86_64.AppImage
export OPENSAPI_IMAGE="$PWD/wine-opensapi-piper-11.21-x86_64.AppImage"
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

Set `OPENSAPI_IMAGE`, `APPIMAGE_EXTRACT_AND_RUN`, and `WINEPREFIX` as above, then:

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

## What the build verifies

CI runs the 13 deterministic integration tests against both the build-tree Wine
and the packaged Wine runtime, plus an AppImage extraction/version/registration
check. These tests use synthetic PCM, not a real Piper voice. A successful build
does not prove neural synthesis, audible playback, or Logos compatibility.

Pause/resume, speech events, word highlighting, and several SAPI XML features
remain unsupported. Stop/cancel may be delayed by a synchronous HTTP request.

The matching patched Wine source archive and patch are release assets. The
OpenSAPI source and test instructions are on the `codex/piper-sapi-prototype`
branch of https://github.com/jg00dman/opensapi.

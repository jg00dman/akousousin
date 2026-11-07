<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin Piper backend

The current user-facing package is the [0.7.0b1 standalone application](../standalone/README.md).
It includes this backend and downloads voices on demand. The separate archive
instructions below describe the earlier headless backend distribution; they are
not the installation steps for the current AppImage. For speech input, see
[recognition development](RECOGNITION.md).

This is a separate GPL-3.0-or-later package, not part of the Wine AppImage or
OuDedetai's MIT-licensed application. It contains Piper 1.8.0, a Waitress 3.0.2
loopback HTTP service and an optional bundled en_US-ljspeech-medium voice.
It does not use Flask's development server. No system Python or pip is needed
for the prebuilt Linux x86-64 package (Ubuntu 22.04/glibc 2.35 or newer).

Extract the archive and run:

```
./akousousin-piper --model "$PWD/voices/en_US-ljspeech-medium.onnx"
```

It binds only 127.0.0.1:5000. Stop with Ctrl+C, or let OuDedetai own its lifecycle.
GET /health reports readiness and instance identity; POST /synthesize accepts
JSON text and length_scale between 0.5 and 2 and returns mono 16-bit PCM WAV.
No download, arbitrary model selection, or remote administration endpoints exist.
Only one synthesis runs at once; concurrent requests return 503. Requests are
limited to 64 KiB/16000 characters and responses to 64 MiB. A stalled inference
child is killed after 60 seconds; a later request starts a fresh child. Startup
model loading has a separate 60-second deadline. Health checks do not synthesize.

The voice is pinned by repository revision and ONNX SHA-256 in voice.json.
The upstream repository declares MIT in its README metadata. Its per-voice
MODEL_CARD identifies the LJ Speech public-domain dataset and training from
scratch; it lists no separate restriction. Both upstream documents and source
URLs are preserved under voices/. Attribution: Piper voice contributors and
Bryce Beattie (training); LJ Speech recordings transcribed from LibriVox.
This selection does not extend to other voices, which need individual review.

The matching sources archive includes our service/build scripts, Piper 1.8.0
and the eSpeak-ng revision it builds, plus the resolved dependency versions.
Dependency licence notices are under licenses/. Build the service with
`pip install ./backend pyinstaller==6.16.0; python backend/bundle.py` on Ubuntu
22.04 using Python 3.12. The binary includes its Python runtime and dependencies.

Automated fake-worker tests exercise HTTP validation and recovery. The packaging
workflow separately runs real synthesis and verifies WAV format using the frozen
binary and bundled voice. Audible playback and Logos remain desktop checks.

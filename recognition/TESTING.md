<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

> **Historical CLI-only snapshot, superseded by the main AppImage beta.** The
> instructions and glibc requirement below describe that older standalone archive.
> Use the [current Voice Input guide](PANEL-TESTING.md) for the AppImage, control
> panel and KDE Wayland dictation. Its Linux target is glibc 2.35+.

# Akousousin Whisper — experimental Linux test build

This snapshot contains command-line recognition, not SAPI recognition or hotkey
text insertion. It does not install or modify your existing Akousousin, Wine
prefixes, desktop configuration or keyboard layout. Speech models are stored separately in
`~/.local/share/Akousousin/models/whisper/` (respecting `XDG_DATA_HOME`).
They survive upgrades. Inference is local and does not need network access.

Target: x86-64 Kubuntu 26.04. Built on Debian glibc 2.41; requires glibc 2.41 or
newer. Keep the extracted directory together. No Python installation is required.

Extract the archive, open a terminal inside its directory, then run:

```sh
./akousousin-whisper --help
# One-time setup, or import Small from the earlier test bundle:
./akousousin-whisper --download-model
# ./akousousin-whisper --import-model /path/to/old-bundle/models/small
./akousousin-whisper --capture-seconds 5
```

Microphone capture requires `parec`, usually installed with:

```sh
sudo apt install pulseaudio-utils
```

PipeWire remains your audio server. The utility connects through pipewire-pulse.
Wait while the model loads and the microphone opens. Two short 250 Hz tones
and “Listening — speak now” announce the start of the five-second recording.
The cue is excluded from accepted audio. Use `--no-beep` for a visual prompt only.
The command then prints JSON containing the transcript, language and model.
Omit `--language` to detect language, or lock it explicitly:

```sh
./akousousin-whisper --capture-seconds 10 --language de-DE
```

Use the default microphone selected in KDE audio settings, or list sources and
choose one (avoid monitor sources, which record speaker output):

```sh
pactl list short sources
./akousousin-whisper --capture-seconds 5 --source YOUR_SOURCE_NAME
```

You can also test a mono 16 kHz 16-bit PCM WAV file of at most 30 seconds:

```sh
./akousousin-whisper --wav speech.wav
```

Conversion, if needed, requires an installed `ffmpeg`:

```sh
ffmpeg -i input.wav -ac 1 -ar 16000 -c:a pcm_s16le speech.wav
```

Please retain the command/output and note language, time to result, microphone,
and whether words were missed. Try silence, a normal sentence, and a sentence
in another language. A silent result should have empty text and no language tag.
The program does not type into any application; inspect the printed transcript.

Known limits: fixed-duration capture (1–30 seconds), two CPU inference threads,
no device recovery, no global hotkey, no SAPI recognizer, no automatic document
language tagging, no AKS speech suppression. Linux only; no Windows build is
claimed. Actual human-microphone accuracy and fifth-generation i5 performance
remain to be measured. See the current Voice Input guide and repository CI for subsequent test evidence.

Uninstall the program by deleting this extracted directory. Downloaded models
remain in the shared data directory until you remove them yourself. Build provenance is in build.json;
checksums and dependency licences are included.

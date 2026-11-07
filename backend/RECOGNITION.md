<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Whisper recognition development

The 0.7.0b1 beta includes experimental Linux recognition and KDE Wayland desktop
dictation. It uses **faster-whisper and CTranslate2**, CPU int8, two inference
threads, one worker, neural VAD and greedy decoding. It does not ship the original
OpenAI Whisper Python package or PyTorch. SAPI recognition and native Windows live
microphone capture remain unimplemented; Windows development supports WAV input.

For user setup, use the [Voice Input guide](../recognition/PANEL-TESTING.md).
For portal permissions, bounded capture, focus checks and acceptance evidence, see
[desktop dictation development](../recognition/DICTATION.md).

## Development setup and model management

Install from the repository root:

```sh
python -m pip install './backend[recognition]' './standalone[recognition]'
```

The default multilingual Small model is a one-time download of about 485 MB.
The panel's Enable voice input or recording/dictation activation downloads it
when needed; the ordinary inference API and WAV CLI do not download implicitly.
The model manager uses pinned assets, staging, an install lock, integrity checks
and retained model notices. Import existing model copies converted CTranslate2
assets into the persistent cache. These are complete multilingual models, not
independently installable language modules.

- Linux: `$XDG_DATA_HOME/Akousousin/models/whisper/`, normally
  `~/.local/share/Akousousin/models/whisper/`.
- Windows: `%LOCALAPPDATA%/Akousousin/models/whisper/`.
- Small and Turbo occupy `small` and `turbo` subdirectories. Turbo currently
  supports local converted-model import only; its download is not implemented.

The default application package contains no Whisper model weights; the small VAD
helper is bundled. Downloads/imports survive application replacement and model
unloading. Disable voice input frees model memory and retains files; idle
unloading defaults to 300 seconds. An approved shortcut can enable/load it again.
The resident controller owns the recognition worker, allowing reuse across
recordings and panels. Quit closes its worker and capture/portal sessions.

## Backend and diagnostic CLI

```sh
akousousin-whisper --help
akousousin-whisper --download-model
# Or: akousousin-whisper --import-model /path/to/converted/small
akousousin-whisper --wav speech.wav
akousousin-whisper --wav speech.wav --language de-DE
akousousin-whisper --capture-seconds 5
```

WAV input is mono 16 kHz signed 16-bit PCM, at most 30 seconds. The Linux diagnostic
capture adapter requires `parec` from `pulseaudio-utils`; it connects to the host
PulseAudio-compatible server, including PipeWire's `pipewire-pulse`. Omit `--source`
to use the default source, or pass an explicit source name. This CLI capture has a
fixed duration; the controller's desktop adapter provides toggle and push-to-talk.
The panel waits for actual microphone audio and plays an optional pair of 300 Hz
ready tones before accepting speech. It also provides a separate sound test.

Inference runs in a separate spawn process. An explicit application/user language
is normalized and locked, bypassing autodetection; omitted language requests
Whisper detection. Host locale is not silently used as a lock. Results preserve
text, language, language probability, explicit/detected source, active model and
fallback warnings. Probability under a forced language is not independent
detection evidence. The panel displays detected language separately from the
user's automatic/fixed language choice.

Turbo load failure falls back to Small; if Small also fails the request fails
cleanly. Missing/corrupt assets are diagnosed by model loading, not merely folder
presence. One inference is accepted at a time; timeout or worker death closes the
worker and a later request can restart it. Desktop audio queues are bounded.

## Remaining work and validation limits

- Recognition-side COM/SAPI engine and registration for Wine and Windows. It must
  accept application-provided audio and deliver verified recognition events/results
  before claiming SAPI compliance.
- Native Windows live capture and a broader native Linux input framework. The
  current global dictation adapter targets KDE Wayland.
- Spoken punctuation commands and document proofing-language tagging. Keyboard
  layout changes alone do not reliably set document language.
- Wider microphone, non-Latin, low-end CPU/RAM, focus-switching and desktop
  acceptance. French worked in a reported user test; Hebrew and Greek did not in
  that test. Whisper language support is not a per-language accuracy guarantee.

Run backend tests without downloading models:

```sh
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
```

## Real inference validation

In addition to the dependency-free lifecycle tests, opt-in tests exercise the real
CPU model, language detection, Windows LCID language locking, silence, missing
Turbo fallback and missing-model failure. They require provisioned local assets:

```sh
HF_HUB_OFFLINE=1 PYTHONPATH=backend \
AKS_TEST_WHISPER_MODELS=/path/to/models \
AKS_TEST_WHISPER_JFK_WAV=/path/to/jfk.wav \
AKS_TEST_WHISPER_GERMAN_WAV=/path/to/german.wav \
python -m unittest discover -s backend/tests -v
```

The JFK fixture is OpenAI Whisper's `tests/jfk.flac`, converted using
`ffmpeg -i jfk.flac -ac 1 -ar 16000 -c:a pcm_s16le jfk.wav`. German is optional;
when supplied, its expected phrases are `Guten Morgen` and `deutschen Text`.
See [validation evidence](WHISPER-VALIDATION.md) for the actual fixtures, versions,
results and deployment gaps. Mock capture tests verify invocation, PCM formatting,
timeout handling and forced cleanup; they do not validate a live audio server.

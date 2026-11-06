<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Whisper development validation — 2026-11-04

This is backend validation, not SAPI compliance or a release acceptance report.

## Environment and fixtures

- Linux x86-64 cloud worker, AMD EPYC 9V74; Python 3.12.
- faster-whisper 1.2.1, CTranslate2 4.8.5, ONNX Runtime 1.31.1.
- Systran/faster-whisper-small revision
  `536b0662742c02347bc0e980a01041f333bce120`.
- Actual CPU int8 inference, two CPU threads, VAD enabled, beam size 1.
- Inference tests run with `HF_HUB_OFFLINE=1`; models downloaded explicitly
  beforehand. No models, recordings or virtual environments are committed.
- English: OpenAI Whisper repository `tests/jfk.flac`, 11 seconds, source SHA256
  `63a4b1e4c1dc655ac70961ffbf518acd249df237e5a0152faae9a4a836949715`.
  Converted to mono 16 kHz signed 16-bit PCM WAV.
- German: synthesized using Piper 1.8.0 and the development-time
  `rhasspy/piper-voices` de_DE-thorsten-medium model. Text:
  “Guten Morgen. Dies ist ein Test der automatischen Spracherkennung. Heute
  schreiben wir einen kurzen deutschen Text mit dem Computer.” Same WAV format.
  Synthetic speech verifies language/inference plumbing; it does not establish
  accuracy on human speakers, accents or noisy microphones.

## Results

Real Small inference transcribed the expected English phrases, detected English
(probability approximately .939), and transcribed the German passage with German
detection (approximately .998). LCID 1033 locked English. Silence produced no text
or language. Missing Turbo fell back to real Small with an explicit warning.
Missing Small failed cleanly and created no downloaded assets.

Single-run timings for the English sample, sequentially in one worker:

| Case | Seconds |
| --- | ---: |
| Cold automatic detection, including worker/model startup | 4.887 |
| Warm automatic detection | 3.990 |
| Warm locked English | 2.096 |

Child process peak RSS was 651732 KiB (about 636 MiB), measured with Linux
`resource.getrusage(RUSAGE_CHILDREN)` after worker shutdown. This excludes parent,
GUI and other application memory. These are development observations, not a
benchmark on the target fifth-generation i5 or a latency guarantee. Measurements
include short-sample variance and must be repeated on target hardware.

Testing found and fixed misleading language confidence on explicitly locked
requests, language metadata on silent results, and native runtime semaphore leaks
caused by terminating idle workers. Idle workers now receive a graceful shutdown;
timeout/death paths retain bounded termination and recovery.

## Not verified / not implemented

- Live PulseAudio/PipeWire capture, physical microphones, device reconnects.
- KDE Wayland global shortcuts, toggle/push-to-talk and text insertion.
- Recognition-side SAPI COM contracts, events, audio streams, registration or
  real Wine/Windows application integration. Those adapters are not implemented.
- Native Windows inference and Windows/AppImage recognition packaging.
- Real Turbo inference, corrupted-model recovery, broad language accuracy.
- Background noise, mixed languages, AKS output suppression and long sessions.
- Fifth-generation i5 / 8 GB behavior.

The cloud workspace lacks a running PipeWire microphone/KDE session, Wine and
Windows. A passing backend suite must not be presented as validation of these
platform behaviors. Remaining implementation is listed in RECOGNITION.md.

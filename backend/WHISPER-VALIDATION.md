<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Whisper development validation — 2026-11-04

This is backend validation, not SAPI compliance or a release acceptance report.

## Latency addendum — 2026-11-07 (cloud, not Steam Deck)

Verified against faster-whisper 1.2.1 source: the regular transcription loop pads
segments to the encoder window; language detection invokes its own encoder path.
The bundled Silero wrapper's public call resets recurrent state on every call;
it has no stateful streaming interface. Desktop capture therefore uses the
specified adaptive-energy fallback, calibrated from startup microphone audio
before ready, with 25 quiet 20 ms frames (500 ms) and a 400-frame (8 s) cap.
The following real inference measurements do not measure that live microphone path.

Hardware: AMD EPYC 9V74 cloud VM, three exposed cores, cgroup CPU quota
`200000 100000` (two CPU equivalents), Linux x86-64, Python 3.12. Neither the Steam
Deck nor the reference fifth-generation i5 was measured. Physical core count and
CPU quota differ here; three threads were slightly slower than two.

Small revision remains `536b0662742c02347bc0e980a01041f333bce120`, CPU int8,
num_workers=1, beam_size=1. Same English JFK 11.000 s and synthetic German 6.478 s
fixtures described below. Each warm value is the median of two consecutive runs;
cold includes a fresh spawned worker, model load and first transcription.
Automatic + VAD reproduces the prior configuration; locked + endpointed disables
the second VAD pass. These are recognition timings, not end-to-end typing latency.

| Fixture | Threads | Mode | Cold seconds | Warm median seconds |
| --- | ---: | --- | ---: | ---: |
| en | 2 | auto-each-phrase | 4.403 | 3.087 |
| en | 2 | locked | 2.871 | 1.875 |
| en | 3 | auto-each-phrase | 4.700 | 3.407 |
| en | 3 | locked | 2.878 | 1.916 |
| de | 2 | auto-each-phrase | 4.197 | 3.156 |
| de | 2 | locked | 2.818 | 1.832 |
| de | 3 | auto-each-phrase | 4.634 | 3.346 |
| de | 3 | locked | 3.094 | 2.001 |

An additional run kept VAD enabled while locking the language, to isolate the
language-detection effect from the duplicate VAD cost:

| Fixture | Threads | Locked + VAD warm median seconds |
| --- | ---: | ---: |
| en | 2 | 1.933 |
| de | 2 | 1.877 |

The main measured saving is language locking; removing duplicate VAD saved only
about 0.05–0.06 s on these clean fixtures. The old 300-second idle policy only
expired an idle, non-busy recognizer; frequent cold loads during active dictation
were not demonstrated. The former per-character portal replies and insertion on
the recognition thread were confirmed in source, but their real KDE timing has
not yet been remeasured. The user's earlier insertion measurement was 0.229 s.

Reproduction (models must be installed explicitly first; benchmark never downloads):

```sh
PYTHONPATH=backend python backend/tools/benchmark_recognition.py \
  --models /path/to/models/whisper \
  --fixture en=/path/to/jfk.wav --fixture de=/path/to/german.wav \
  --tiers base base.en small small.en --threads 1 2 3 --runs 3 \
  --output recognition-benchmark.json
```

The script records hardware, CPU quota, library versions, cold/warm samples,
transcripts and unavailable models. It compares per-phrase auto detection,
locked-with-VAD, locked-endpointed and session-auto (first detection, subsequent
locked calls). It skips English-only tiers for non-English fixtures.

### New tiers: verified downloads and five-second fixtures

All Base, Base.en and Small.en assets were explicitly downloaded using the new
installer, with pinned metadata, file sizes and LFS SHA256/Git blob checks. Each
upstream model card declares MIT. Downloads retain the card and the original
OpenAI Whisper MIT licence; AppImage/Windows packages include that notice too.
No model weights are added to source control or bundled by default.

| Tier | Systran revision |
| --- | --- |
| small | `536b0662742c02347bc0e980a01041f333bce120` |
| base | `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66` |
| base.en | `3d3d5dee26484f91867d81cb899cfcf72b96be6c` |
| small.en | `d1d751a5f8271d482d14ca55d9e2deeebbae577f` |

The English and German fixtures above were also truncated to their first 5.000 s.
Same hardware and versions, three warm runs per case (median shown), int8 CPU,
num_workers=1. The one-thread run demonstrates the thread-count effect. Quality
choices are not claimed to have identical accuracy; these short clips do not
establish general recognition quality or noisy-room performance.

| Model | Fixture | Mode | Threads | Cold seconds | Warm median seconds |
| --- | --- | --- | ---: | ---: | ---: |
| base | en | auto-each-phrase | 1 | 2.564 | 1.768 |
| base | en | locked | 1 | 1.563 | 0.915 |
| base | en | auto-each-phrase | 2 | 1.712 | 1.126 |
| base | en | locked | 2 | 1.213 | 0.613 |
| base | en | auto-each-phrase | 3 | 1.715 | 1.154 |
| base | en | locked | 3 | 1.209 | 0.561 |
| base | de | auto-each-phrase | 1 | 2.527 | 1.909 |
| base | de | locked | 1 | 1.750 | 1.076 |
| base | de | auto-each-phrase | 2 | 1.941 | 1.148 |
| base | de | locked | 2 | 1.280 | 0.673 |
| base | de | auto-each-phrase | 3 | 2.056 | 1.272 |
| base | de | locked | 3 | 1.945 | 0.887 |
| base.en | en | locked | 1 | 1.566 | 0.911 |
| base.en | en | locked | 2 | 1.201 | 0.605 |
| base.en | en | locked | 3 | 1.146 | 0.599 |
| small | en | auto-each-phrase | 1 | 6.569 | 5.230 |
| small | en | locked | 1 | 4.012 | 2.833 |
| small | en | auto-each-phrase | 2 | 4.137 | 3.072 |
| small | en | locked | 2 | 2.668 | 1.584 |
| small | en | auto-each-phrase | 3 | 4.321 | 3.227 |
| small | en | locked | 3 | 2.987 | 1.708 |
| small | de | auto-each-phrase | 1 | 6.987 | 5.711 |
| small | de | locked | 1 | 4.227 | 3.209 |
| small | de | auto-each-phrase | 2 | 4.135 | 3.225 |
| small | de | locked | 2 | 2.826 | 1.844 |
| small | de | auto-each-phrase | 3 | 4.688 | 3.415 |
| small | de | locked | 3 | 2.968 | 1.836 |
| small.en | en | locked | 1 | 3.889 | 2.784 |
| small.en | en | locked | 2 | 2.608 | 1.523 |
| small.en | en | locked | 3 | 2.699 | 1.665 |

At two threads, the five-second English clip changes from Small/auto/VAD at
3.072 s to Base.en/locked/endpointed at 0.605 s; German changes from Small/auto/VAD
at 3.225 s to Base/locked/endpointed at 0.673 s. At this VM's detected three-core
default, Base.en was 0.599 s and German Base was 0.887 s. These are inference-only
warm medians. Adding a nominal 0.5 s endpoint wait suggests useful headroom, but
is not a measurement of committed text in an actual application.

An additional Base session-auto run (two threads, five-second fixtures) detected
the language on its first call and locked subsequent calls: English cold 1.777 s,
warm median 0.582 s; German cold 1.756 s, warm median 0.675 s. Application tests
also verify that empty results do not lock a session and starting a new recording
resets its language choice.

Still pending: actual Turbo CPU timing (no imported Turbo model), live microphone
readiness/noisy-room tests, and full KDE portal insertion on SteamOS. Neither
readiness within 500 ms nor committed text within 1.5 s after a five-second phrase
is claimed on the reference machine. The target-device result remains unverified.
Private-D-Bus tests verify ordered key messages and focus guards, not compositor
latency or text received by a real application.

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

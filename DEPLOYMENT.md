<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Deployment candidate status

The previously released Beta 1 (a128f2f) was desktop-tested in Logos on Kubuntu
26.04: Read Aloud, speed controls and jumping back worked. It remains available
unchanged. This deployment candidate adds failure handling and a separate service.

## Separate Piper service and voice

The first standalone package is available at
https://github.com/jg00dman/akousousin/releases/tag/piper-backend-41388556427-1

GitHub Actions built a Linux x86-64 application with embedded Python, Piper 1.8.0,
Waitress 3.0.2, and en_US-ljspeech-medium. Its frozen executable produced valid,
non-empty 22050 Hz mono 16-bit WAVs at length_scale 1.0, 0.5 and 2.0. Six fake-worker
unit tests passed, including worker death, timeout and recovery. Both downloaded
archives were independently checked against SHA256SUMS. This is real neural
synthesis verification, not a listening test or a Logos test.

Voice provenance: rhasspy/piper-voices revision
b4e358ffcb232591bf73a540e70f7de528e4174a declares MIT; the per-model card specifies
public-domain LJ Speech data and training from scratch. The package retains both
upstream declarations. Models with additional restrictions were not selected.
Piper and the wrapper are distributed separately under GPL-3.0-or-later, with
Piper/eSpeak sources and wheel licence notices. The packaging rebuild adds explicit embedded-Python and collected system-library
copyright notices; both binary and source archives are separately downloadable.

## Wine failure handling

Patch order: the pinned Logos branch, wine-piper.patch,
wine-sapi-enum-values.patch, wine-piper-site-write.patch, then
wine-piper-lifecycle.patch. Nonblocking Winsock transport checks abort every
50 ms; connection and send deadlines are 3 and 5 seconds, and each complete
request has a 65-second deadline, including trickling peers. It connects only to
127.0.0.1; it requires bounded Content-Length responses and rejects redirects,
transfer encoding, malformed WAV, unsupported format and incomplete bodies.

Uninitialized engines return SPERR_UNINITIALIZED. Removing the Piper voice
makes Akousousin-filtered enumeration return zero; a stale default is tested to
return SPERR_NOT_FOUND from speech. Wine's unrelated empty 'Wine Default Voice'
placeholder is not removed, and other vendors' installed voices are preserved.

All original 13 integration tests remain unchanged in scope and still run against
both build-tree and packaged Wine. A separate seven-test suite adds absent
backend, no registration/stale default, cancellation before headers/during body,
dropped response, same-engine retry after HTTP failure, uninitialized engine,
and a total timeout test. Run 41391312177 passed all 13 original cases, all seven failure/recovery cases,
and enumeration probes against both runtimes, plus actual AppImage wineserver
dispatch. The composed real-speech check also passed using the separate frozen
backend and bundled voice; its WAV and log are release assets.

The earlier async candidate is superseded: Wine's WinHTTP request-handle closure
does not interrupt pending reads. CI supports migrating that exact known source
checkpoint without compiling Wine from scratch. Local patch application and
repeat-source/cache verification pass without local Wine compilation.

## OuDedetai integration

The companion change is on jg00dman/OuDedetai branch codex/piper-lifecycle.
Install/Configure/Start/Stop/Disable actions are available through GUI, TUI and
CLI. Installation downloads a checksum-pinned standalone package and registers
its voice only in the configured Logos prefix. It preserves native .NET overrides.
Piper is optional and disabled by default. Startup failure does not prevent Logos
launch. PID creation time and instance token prevent stopping unrelated servers;
Logos launcher exit does not prematurely stop speech. See its PIPER.md.

Nineteen focused OuDedetai tests pass. GitHub Actions passed all 96 tests (16
existing skips) and built both x86-64 and ARM launcher binaries. Actual packaged
backend start/reuse/ownership-safe stop/restart checks passed locally. The local
full suite has one pre-existing backup filesystem-size assertion failure, also
reproduced on an unchanged baseline. Existing global type-check failures remain;
no claim of a clean full type check is made.

## Remaining release gates

Desktop-test absent/stopped/restarted
Piper and stale registration inside Logos. Automated error returns do not prove
that Logos handles every failure gracefully. Do not replace Beta 1 or mark this
candidate generally deployable until those checks are complete.

The final headless backend archives have been independently checksum-verified;
Python and system-library notices and pinned voice provenance are present, with
unused readline excluded. Real packaged-binary synthesis passed at three speeds.
Missing-model startup and recovery after killing active neural inference were
also checked: the interrupted request returned HTTP 503, and the next produced
real speech. OuDedetai AppImage dispatch now supports wineserver symlinks, with
an actual extraction-mode wineserver dispatch check in the Wine packaging stage.

## Verified downloadable beta set

- Wine and its matching source/checksums/logs/real-neural WAV:
  https://github.com/jg00dman/akousousin/releases/tag/piper-test-41391312177-1
- Backend, voice and corresponding sources:
  https://github.com/jg00dman/akousousin/releases/tag/piper-backend-41388556427-1
- OuDedetai x86-64 launcher and checksum:
  https://github.com/jg00dman/OuDedetai/releases/tag/piper-beta-41389712590-1

All downloaded Wine/AppImage/source/patch/log assets matched their published
SHA-256 digests. The complete manifest also matched all release asset digests.
The real-neural WAV has 77056 frames at 22050 Hz, mono 16-bit PCM. Backend and
launcher archives/checksums were independently verified as well. Sources stay
on feature branches for review; the prior main-branch beta remains unchanged.

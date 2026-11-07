<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Unreleased — dictation latency work

- New installations use the system locale and a locked input language. English
  defaults to Base.en, other supported locales to multilingual Base. Small and
  Small.en remain quality choices. Turbo remains available for local import and
  is labelled as a large-encoder model, not a CPU speed option.
- Legacy Small + automatic-language defaults migrate to the locale and compact
  model. Explicit legacy language/model choices are retained; selecting
  Multilingual (auto) explicitly now detects once per recording session and locks
  subsequent phrases. Existing downloaded models are retained.
- CPU threads default to the detected physical core count and are configurable;
  inference retains one killable worker. The model stays loaded while enabled by
  default. The optional idle timeout increases from five minutes to one hour;
  legacy five-minute defaults migrate to one hour.
- Adaptive microphone noise calibration, 500 ms endpoint silence and an 8-second
  phrase cap replace the fixed energy gate. Endpointed input skips the redundant
  Whisper VAD pass. Ready tones use cached audio through memory/stdin.
- Ordered text insertion has its own bounded queue. Per-phrase focus verification
  and focus-change guards remain; keyboard events avoid per-key portal replies.
  No clipboard is used for dictation insertion.
- Numeric per-phrase speech/endpoint/recognition/typing timings are logged, without
  transcript text, and shown beside recent transcripts. Dictation status changes
  also reach the copyable status bar.

This work is not released. All new downloadable tiers use verified immutable
Systran revisions and retain their upstream MIT model cards. Hardware-specific
results and remaining target-device checks are recorded in backend/WHISPER-VALIDATION.md.

# Akousousin 0.7.0b6 beta

This trial bundles clipboard readers for SteamOS and makes status text copyable.
It also includes the voice controls and speech timing improvements from beta 5.
The reported Orca and dictation performance issues are not declared fully resolved.

- **Bundled clipboard readers:** the Linux AppImage includes wl-paste and xclip
  plus their private libraries. Host clipboard packages are no longer required.
  X11 sessions use xclip even when an inherited Wayland socket is present. Desktop
  clipboard permissions and application selection support still apply.
- **Copyable status:** select the status text and press Ctrl+C, or use Copy.
  Long messages can be copied in full.
- **Delete installed voices:** select an installed entry in Voice library and
  choose Delete voice…. Confirmation is required. Managed downloaded files are
  deleted; imported originals are retained. Default/language preferences are
  updated. Apply voice registration in Settings afterwards to remove stale
  AKS-owned SAPI tokens; restart applications that cache voice lists.
- **Speed:** 0.5–4.0 in 0.25 steps, using a stepped slider and a readable value
  control. Existing application rate requests still combine with the default.
- **Interrupted speech:** cancelled audio is removed from estimated playback
  activity instead of accumulating unnecessary dictation pauses. Other clients'
  remaining playback activity is retained. Short interrupted inferences get up
  to 250 ms to finish and be discarded while retaining the model; slow/hung
  workers still use bounded termination.
- **Host audio tools:** preview playback, ready tones and microphone capture
  use host libraries rather than inheriting AppImage library paths, including
  paths left by an earlier nested AppImage launch.
- **Dictation diagnostics:** each transcript shows audio duration, queue wait,
  recognition time and insertion time. These remain in memory with the recent
  transcripts; no transcript log file is written. Please include these timings
  when reporting the approximately 30-second delay.

For Orca, select AKS and Apply to refresh its voice list, then select an actual
installed Piper voice and Apply/OK again. This sequence was confirmed on SteamOS
Plasma. Keep AKS's default and Orca's selected voice the same when comparing
latency: the shared engine currently keeps one Piper voice loaded.

The SteamOS certificate-store fix, automatic reading-shortcut setup, AppImage
installation/menu integration and stable/beta update preferences remain included.
Quit the old AKS from its tray before launching this build. Existing voices,
models and preferences are retained; no configuration reset is required.

See the [installation guide](https://github.com/jg00dman/akousousin/blob/main/standalone/README.md)
and [beta checklist](https://github.com/jg00dman/akousousin/blob/main/standalone/BETA-TESTING.md).
Licences, matching sources and checksums accompany the packages.

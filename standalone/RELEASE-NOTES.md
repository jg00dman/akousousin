<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin 0.7.0b5 beta

This trial adds voice deletion, simpler speed controls, cancellation improvements
and per-phrase timing information for investigating the reported SteamOS delays.
The reported Orca and dictation performance issues are not declared fully resolved.

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

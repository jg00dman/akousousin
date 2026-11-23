<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# voice-script

Chooses the recording script for a custom Piper voice: whole Bible passages,
picked so the reader covers every sound and pair of sounds. See
[docs/custom-voices](../../docs/custom-voices/README.md).

## Hebrew

```sh
git clone --depth 1 https://github.com/openscriptures/morphhb.git
python3 scripts/voice-script/make_hebrew.py --wlc morphhb/wlc
```

This writes:

- `docs/custom-voices/hebrew/session-*.md`: the reader's script.
- `scripts/voice-script/out/hebrew/metadata.tsv`: verse id, text and phonemes
  for every verse (the basis of the training metadata).
- `scripts/voice-script/out/hebrew/report.json`: passages per session, counts
  per sound, and coverage.

Options: `--minutes` (time budget for whole passages, default 60) and
`--rare-target` (how often every sound pair must be heard, default 2).

## Files

| File | What it does |
| --- | --- |
| `hebrew_g2p.py` | Pointed Hebrew to phonemes, Sephardic reading. Every pronunciation choice, including the divine name, is in the tables at the top. |
| `wlc.py` | Reads the OSHB/WLC OSIS XML; uses the qere where there is a ketiv/qere pair. |
| `select_script.py` | Language-independent selection: greedy coverage of sounds and sound pairs per second of reading. |
| `make_hebrew.py` | Builds the Hebrew script. |

Reading-time estimates assume 4 syllables a second plus 0.7 s between verses;
recalibrate them from the first test recording.

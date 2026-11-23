<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Hebrew recording script

Biblical Hebrew, read with Sephardic pronunciation. About 75 minutes of reading
in four sessions. Please read the [recording instructions](../RECORDING.md) first.

| Session | Contents | Reading time |
| --- | --- | --- |
| [Session 1](session-1.md) | Jonah 1–4, Ruth 1–4 | about 21 min |
| [Session 2](session-2.md) | Psalms 1, 2, 4, 6, 11, 12, 15, 17, 19, 20, 23, 43, 52, 54, 58, 61, 62, 64, 65, 70, 82 | about 20 min |
| [Session 3](session-3.md) | Psalms 87, 98, 107, 114, six stanzas of 119, 122, 123, 134, 137, 139, 141, 142, 147, 149, 150 | about 19 min |
| [Session 4](session-4.md) | 147 single verses from across the Psalms, for rare sound combinations | about 13 min |

Times are estimates and will be corrected after the first test recording.

## Text

The text is the Westminster Leningrad Codex, from the
[Open Scriptures Hebrew Bible](https://github.com/openscriptures/morphhb). Where
the text has a ketiv/qere pair, the script shows the qere, which is what is read
aloud. Cantillation marks are left out of the script to keep it readable; the
software still uses them to find the stressed syllable.

## Pronunciation

Sephardic, as taught in [Aleph with Beth](https://freehebrew.online/pronunciation/):

- ח and ע are real pharyngeals, distinct from כ and א.
- ו is [v]. ר is a tapped or trilled r.
- בּ/ב, כּ/כ and פּ/פ are distinguished (b/v, k/kh, p/f). ג, ד and ת sound the
  same with or without dagesh.
- Five vowels: a, e, i, o, u. Tsere and segol are both "e"; qamets qatan
  is "o".
- Vocal shewa is a short "e"; silent shewa is silent.
- A doubling dagesh is not pronounced as a double consonant.
- Stress follows the accents (usually the last syllable).
- **The divine name** יהוה: to be decided before recording, then read the same way
  every time.

## How the passages were chosen

[`scripts/voice-script`](../../../scripts/voice-script/) turns every verse
of Jonah, Ruth and the Psalms into sounds using the rules above, then:

1. includes all of Jonah and Ruth;
2. adds whole psalms (or eight-verse stanzas of Psalm 119), each time picking the
   one that adds the most missing sounds and sound pairs per minute of reading,
   up to about an hour;
3. adds single psalm verses until every sound pair that occurs anywhere in
   Jonah, Ruth or the Psalms is heard at least twice.

The result covers all 779 sound pairs in those books, 99.4% of the sound pairs in
running speech at least four times, and every sound at least 157 times.

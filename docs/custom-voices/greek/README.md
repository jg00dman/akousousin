<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Greek recording script

Koine Greek, read with the Polis Institute's modified Erasmian pronunciation.
About an hour and a half of reading in six sessions. Please read the
[recording instructions](../RECORDING.md) first.

> **Draft.** The pronunciation details below still need confirming against
> the freegreek.online videos. The choice of passages hardly depends on them,
> but the reader needs them settled before recording.

Most of the script is whole books, so the recordings also make a complete
audiobook of each one.

| Session | Contents | Reading time |
| --- | --- | --- |
| [Session 1](session-1.md) | 2 Thessalonians, Titus, Philemon | about 18 min |
| [Session 2](session-2.md) | James | about 17 min |
| [Session 3](session-3.md) | 2 Peter | about 12 min |
| [Session 4](session-4.md) | 1 John | about 19 min |
| [Session 5](session-5.md) | 2 John, 3 John, Jude | about 9 min |
| [Session 6](session-6.md) | 97 single verses from across the New Testament, for rare sound combinations | about 19 min |

Times are estimates and will be corrected after the first test recording.

## Text

[The Greek New Testament: SBL Edition](https://sblgnt.com) (SBLGNT),
© 2010 Society of Biblical Literature and Logos Bible Software, licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The script leaves out the
apparatus marks.

## Pronunciation

The [Polis Institute](https://www.polisjerusalem.org/koine-greek-pronunciation-%ef%bb%bf/)
pronunciation, as used by [freegreek.online](https://freegreek.online/pronunciation/).
Polis describes it as close to Erasmian, with φ [f], θ [θ] and χ [x], with
diphthongs kept distinct, and with circumflex and acute accents read differently.
The rest is a draft based on standard Erasmian:

| Letters | Draft | To confirm |
| --- | --- | --- |
| α ε ι ο | a, e, i, o | |
| η / ω | open "e" (as in "air") / open "o" (as in "saw") | Different vowel quality, or longer vowels? |
| υ | French "u" [y] | or "oo"? |
| αι, ει, οι, υι | "eye", "ay", "oy", "ü-ee" | ει as "ay" or "ei"? |
| ου | "oo" | |
| αυ, ευ, ηυ | "ow", "eh-oo", "air-oo" | |
| β γ δ κ λ μ ν π ρ σ τ | b, g, d, k, l, m, n, p, r, s, t | |
| ζ | "zd" | or "dz", or "z"? |
| θ φ χ | [θ] as in "thin", f, "ch" as in "loch" | |
| ξ ψ | ks, ps | |
| γγ γκ γξ γχ | "ng" | |
| rough breathing | h | also on ῥ? |
| iota subscript (ᾳ ῃ ῳ) | silent | |
| acute and grave | stress on that syllable | grave read like acute? |
| circumflex | stress with a falling tone | How exactly is it read differently from the acute? |

## How the passages were chosen

[`scripts/voice-script`](../../../scripts/voice-script/) turns every verse of the
New Testament into sounds using the rules above, then:

1. offers short books (up to about 22 minutes) whole and longer books chapter by
   chapter, with a strong preference for whole books;
2. adds the book or chapter that adds the most missing sounds and sound pairs per
   minute of reading, up to about an hour;
3. adds single verses until every sound pair that occurs at least three times
   in the New Testament is heard at least twice.

Sound pairs are counted ignoring accents; every accented vowel is still counted
on its own. The result covers 99.4% of the sound pairs in running speech at least
four times.

<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Custom voices: Biblical Hebrew and Koine Greek

Akousousin reads aloud with [Piper](https://github.com/OHF-Voice/piper1-gpl)
voices. There are no suitable voices for Biblical Hebrew or Koine Greek, so we
are making our own: Hebrew first, then Greek.

- **Want to help by reading?** Start with the [recording instructions](RECORDING.md).
- [Hebrew recording script](hebrew/README.md)
- [Greek recording script](greek/README.md) (draft: pronunciation details to confirm)

## Pronunciation

Each voice follows the pronunciation taught by the free courses many of our
readers learned from:

- **Hebrew:** Sephardic, as in [Aleph with Beth](https://freehebrew.online/pronunciation/).
  Details in the [Hebrew script](hebrew/README.md#pronunciation).
- **Greek:** the modified Erasmian pronunciation of the
  [Polis Institute](https://www.polisjerusalem.org/koine-greek-pronunciation-%ef%bb%bf/),
  as used by [Alpha with Angela](https://freegreek.online/pronunciation/).

The voice style is natural storytelling narration, like an audiobook reader,
not liturgical or chanted reading.

## How a voice is made

1. **Script.** Real Bible passages, chosen by
   [`scripts/voice-script`](../../scripts/voice-script/) so every sound and pair of
   sounds is covered: about 75 minutes of reading for Hebrew and 95 for Greek.
2. **Recording.** One reader per language, with the same setup every session
   ([instructions](RECORDING.md)).
3. **Splitting.** The recordings are split into one clip per verse
   automatically, by aligning the audio with the known text.
4. **Pronunciation rules.** Each language has its own rules for turning written
   text into sounds (the same rules used to choose the script). They are used
   both for training and when Akousousin reads text aloud.
5. **Training.** A Piper voice is fine-tuned from an existing voice checkpoint
   on the clips, then exported for Akousousin.
6. **In Akousousin.** Hebrew text and Greek text are recognised (by script and
   by Greek accents and breathings), split from surrounding English, and sent
   to the right voice.

## Why not existing recordings?

The freely available Hebrew Bible recordings are either chanted or declaimed
liturgically, under non-commercial or no-derivatives licences, or in modern
Israeli pronunciation. Recording our own gives the right pronunciation and
style, and a voice that can be freely distributed with Akousousin.

## Licensing

Readers license their recordings and the resulting voice openly (CC BY 4.0 or
CC0). The Hebrew text is the public-domain Westminster Leningrad Codex; the Greek text
is the SBL Greek New Testament (CC BY 4.0).

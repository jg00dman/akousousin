<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Recording a voice

Thank you for reading for us. Your recordings will be used to train a
text-to-speech voice for Akousousin that reads Biblical Hebrew (and later Koine
Greek) aloud. The voice will sound like you, so please read the
[agreement](#agreement) section before you start.

The scripts are real Bible passages, chosen so that every sound of the language
turns up often enough for the voice to learn it:

- [Hebrew script](hebrew/README.md): four sessions, about 75 minutes of reading in all
- [Greek script](greek/README.md) (draft): six sessions, about 95 minutes, mostly whole books

## How to read

- **Read it like a story to a listener.** Use a warm, unhurried voice, like an
  audiobook narrator. Avoid chanting, liturgical declamation and the
  "reading aloud in class" voice.
- **Keep the same pace and loudness** in every session. The voice copies
  whatever you do, including getting tired or rushing, so take breaks.
- **Pronounce carefully and consistently.** Every pronunciation habit you have
  becomes the voice's habit. See the pronunciation notes for
  [Hebrew](hebrew/README.md#pronunciation) and [Greek](greek/README.md#pronunciation).
- **Pause for about a second after each verse.**
- **If you stumble, stop, pause, and re-read the whole verse.** Don't patch the
  middle of a verse and don't stop the recording; the last take of each verse is
  the one we keep.
- **Read in the order of the script** and don't skip verses. If you need to
  skip one, say so on the recording ("skipping Psalm 23 verse 4").
- **Say the passage name at the start of each file** (for example "Psalm 23").
- The last session of each script jumps between single verses. Read each as a complete sentence
  on its own, in the same storytelling tone.

## Setup

- **The same room, mic, mic position and time of day for every session.** A
  furnished room (curtains, sofa, books) is better than a bare or echoey one.
  A wardrobe full of clothes is excellent.
- **Mic:** a decent USB mic is plenty. Put it about a hand-span from your mouth,
  slightly to the side, with a pop filter if you have one.
- **Quiet:** phones on silent, no fans, heaters, fridges or open windows, no
  clothing rustle or chair creaks. Keep the script on a screen or on paper that
  won't rustle.
- **Start every session with 10 seconds of silence** (just sit still). We use it to
  measure the room's background noise.
- Have water to hand.

## Format

- **WAV or FLAC, mono, 44.1 or 48 kHz, 24-bit** (16-bit is fine).
- **Not MP3, AAC, M4A or Opus.** Compressed audio damages the voice.
- **No processing at all:** no noise reduction, normalising, compression, EQ,
  "voice enhancement" or automatic gain. Many phone and video-call apps do this
  silently, so use a plain recorder such as [Audacity](https://www.audacityteam.org/).
- **Level:** the loudest peaks should reach about −12 to −6 dB and never clip.
  Set it once with a test reading, then leave it alone.
- **One file per passage or per few passages**, named with the session and the
  first passage, for example `S2_Psalm-023.wav`, `S1_Jonah-1.wav`.
- **Keep every raw file**, including takes with mistakes. Don't edit them.
- Write down the date, mic and room for each session in a `notes.txt` beside the
  files.

You don't need to line anything up with the text. As long as the verses are
read in order with a short pause between them, the recordings are split into
verses automatically and matched to the script.

## Before the full sessions

Record a short test first (**Jonah 1** for Hebrew, **Philemon** for Greek; a couple of minutes each) and send it in. From that we check
the levels and room noise, test the automatic splitting, measure your real
reading pace and can train a rough trial voice, before you commit hours to it.

## Agreement

The voice trained from your recordings will sound recognisably like you, and
anyone will be able to use it to read any text. Before recording, readers sign a
short release licensing the recordings and the voice openly (CC BY 4.0 or CC0),
so the voice can ship with Akousousin. If you're not comfortable with that,
please say so before you start; it's much harder to sort out afterwards.

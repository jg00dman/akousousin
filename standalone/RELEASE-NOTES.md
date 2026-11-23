<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin 0.9.1 beta 1

A test build of two fixes. Install it over 0.9.0; everything else is unchanged.

- **The tray icon is visible on dark panels.** The ready and reading icons were
  drawn in a fixed dark colour, so on a dark panel they only showed when you
  hovered over them. They are now installed as theme icons, which Plasma and
  GNOME colour to match the panel, like their own tray icons. The green
  microphone is unchanged.
- **The first word is no longer cut off, and the ready sound always plays.**
  After a few seconds of silence, your computer puts its sound output to
  sleep, and some outputs (monitor speakers, USB and Bluetooth) take a moment
  to wake. Whatever played in that moment was lost. After a quiet spell,
  Akousousin now starts with half a second of silence; straight after other
  speech, it doesn't.

[What's in 0.9](https://github.com/jg00dman/akousousin/releases/tag/v0.9.0)

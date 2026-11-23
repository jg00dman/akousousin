<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin 0.9.1 beta 2

A test build for one problem: **Orca silent when Akousousin is chosen as its
synthesizer.** It is 0.9.0 plus these changes only.

- If an app asks for a voice or language Akousousin doesn't have, it now
  speaks with the best installed voice (one for that language, then the
  default) instead of saying nothing.
- Asking for a regional language, such as English (United Kingdom), now also
  lists the other English voices.
- A speech setting Akousousin can't use is ignored on its own, instead of
  the whole set of settings, including the voice and language, being dropped.
- Problems in Akousousin's Speech Dispatcher module are written to its log
  (`~/.local/state/Akousousin/akousousin.log`), so they can be found.

[What's in 0.9](https://github.com/jg00dman/akousousin/releases/tag/v0.9.0)

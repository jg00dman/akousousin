<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin 0.9.1

Fixes for 0.9, and dictation that works on first use. Your voices, models and
settings carry over.

**Dictation works straight away.** A dictation model (Whisper Base, about
145 MB) now comes with Akousousin, so there is nothing to download first. It
works in every language and is the **Fastest** choice. Balanced and Most
accurate are still a download away.

**Orca and other screen readers**

- Orca speaks when Akousousin is chosen as its synthesizer. Before, it could
  stay silent if it asked for a voice or language Akousousin didn't have; now
  the best installed voice is used.
- After an update, Orca and other apps use the new version straight away,
  without logging out.

**Fixes**

- The first word is no longer cut off, and the ready sound plays every time.
- The tray icon is clear on dark panels, including Breeze Dark and Kubuntu's
  standard dark panel, and animates for speech from Windows apps such as Logos.
- Adding a Windows app lists the Wine prefixes found on your computer, and
  **Browse** shows hidden folders such as `.wine`.
- The tar.gz installer quits a running Akousousin itself, instead of asking you
  to, and `akousousin --quit` waits until it has fully exited.
- Links and update pages open in your browser from the tar.gz.

[What's in 0.9](https://github.com/jg00dman/akousousin/releases/tag/v0.9.0)

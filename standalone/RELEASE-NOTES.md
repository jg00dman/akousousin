<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin 0.9.1.4

Groundwork for word highlighting, and quicker speech when you interrupt or switch
languages. Your voices, models and settings carry over.

- **Interrupting is instant.** When a screen reader or app stops speech to say
  something new, the voice stays loaded. Before, it could take about a second
  to reload.
- **Switching languages doesn't reload voices.** Text in another language is
  spoken with that language's voice while your main voice stays ready. The
  second voice unloads after five minutes unused.
- **The newest speech wins.** If two apps speak at once, the newer one takes
  over and the older one stops, as screen readers expect.
- **Groundwork for following along.** Akousousin now knows where each word
  and sentence is heard. The next releases use this for word highlighting in
  Windows apps, Spiel and Orca. Each voice is updated once to report this, the
  first time it loads after the update.

[What's in 0.9.1.3](https://github.com/jg00dman/akousousin/releases/tag/v0.9.1.3)

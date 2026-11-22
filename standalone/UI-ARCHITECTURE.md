<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Control panel architecture

The panel lives in `akousousin_app/ui/`. It is a separate process from the
controller: closing the window never stops speech, reading or dictation.

```
ui/
  window.py        MainWindow: sidebar, page stack, status line, closing
  state.py         AppState: settings + live status, the only poller
  tasks.py         Tasks: background work, results back on the GUI thread
  actions.py       Preview and DictationTest, shared by several pages
  widgets.py       Card, SettingRow, Choices, Keys, ValueSlider, …
  flow.py          Columns that sit side by side or stack when narrow
  theme.py         light/dark palettes, the style sheet, line icons
  lang.py          language names and translated status sentences
  dialogs.py       confirm, document and error dialogs
  tray.py          the controller's tray icon, menu and animations
  pages/           one file per sidebar page, listed in pages/__init__.py
```

## Rules

1. **Pages never talk to each other.** A page reads `state.config` and
   `state.status`, listens to `settings_changed` and `status_changed`, and asks
   for another page with `state.navigate.emit('voices')`.
2. **Nothing blocks the GUI thread.** Controller calls, downloads, installs
   and file scans go through `Page.run(...)` (or `tasks.run`). Workers return
   values; they never touch widgets. A key stops the same task starting twice.
3. **One poller.** `AppState.poll` asks the controller for status once a
   second and emits `status_changed` only when something changed.
4. **Settings are saved through `state.save(**changes)`**, which writes the
   file atomically and tells every page.
5. **Closing is safe.** After the window starts closing, `Tasks` delivers no
   more results. If an install or download is still running the window hides
   and the process exits when it finishes.
6. **Accessibility is part of each widget.** Every control has a visible label
   or an accessible name; status changes go through `state.notice`, which the
   window announces to screen readers. Colour is never the only signal.

## Adding a page

Create `pages/example.py` with a `Page` subclass that sets `key` and `icon`
and implements `title()`, `subtitle()` and `build()`; add it to `PAGES`.

## Translations

Write user-visible text with `self.tr('…')` inside Qt classes, or
`translate('Context', '…')` (`translate = QCoreApplication.translate`)
elsewhere. Use whole sentences with `%1` placeholders, never sentences built
from pieces. Then:

```
python standalone/update_translations.py es           # update akousousin_es.ts
python standalone/update_translations.py --review es  # side-by-side review table
python standalone/update_translations.py --pseudo /tmp/pseudo  # layout check
```

Language names are shown in their own language ("Ελληνικά", "Español"), so
they are correct whatever the panel's language. The panel follows the system
language. Packaging compiles `.ts` catalogues to `.qm`.

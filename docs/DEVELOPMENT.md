<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# For developers and translators

## How it fits together

| Part | Where | What it is |
| --- | --- | --- |
| SAPI engine | [`engine/`](../engine/) | The 64-bit COM text-to-speech engine that Wine and Windows apps load (C, LGPL-2.1-or-later) |
| Speech and dictation backend | [`backend/`](../backend/) | Piper synthesis, Whisper recognition, microphone capture and Silero speech detection |
| Desktop app | [`standalone/`](../standalone/) | Controller (tray, shortcuts, sessions), control panel, Speech Dispatcher module and packaging |
| Control panel | [`standalone/akousousin_app/ui/`](../standalone/akousousin_app/ui/) | PySide6 (Qt 6) widgets; see [UI-ARCHITECTURE.md](../standalone/UI-ARCHITECTURE.md) |

One controller process per user owns the tray, shortcuts and speech service.
The window, the Speech Dispatcher module, Wine apps and the command line all
talk to it over a private local socket.

## Run from source

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -e ./backend -e './standalone[recognition]'
akousousin
```

## Tests

```sh
PYTHONPATH=backend python3 -m unittest discover -s backend/tests
PYTHONPATH=standalone:backend QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s standalone/tests
python3 scripts/check-licensing.py
```

Packages are built and tested in GitHub Actions
([standalone.yml](../.github/workflows/standalone.yml)): the engine is
cross-compiled, then the Linux and Windows packages are tested under Wine,
Windows, a real Speech Dispatcher and real Whisper inference. Releasing is
described in [RELEASING.md](../.github/RELEASING.md).

## Translating

The interface follows the system language. To add or update a language:

```sh
python standalone/update_translations.py fr           # creates or updates akousousin_fr.ts
python standalone/update_translations.py --review fr  # writes REVIEW-fr.md for proofreading
```

Translate `standalone/resources/translations/akousousin_fr.ts` with Qt
Linguist or any `.ts` editor. Packaging compiles it. To try it from source, run
`pyside6-lrelease` on the `.ts` file first. Please submit each language as its
own pull request so a fluent speaker can proofread it from the review file.

## Reference

- [COMPATIBILITY.md](../COMPATIBILITY.md): what each speech interface supports
- [SPEECH-DISPATCHER.md](../standalone/SPEECH-DISPATCHER.md): the Speech
  Dispatcher module, and the Orca checklist
- [CLI-REGISTRATION.md](../standalone/CLI-REGISTRATION.md): registering Wine
  prefixes from scripts
- [RECOGNITION.md](../backend/RECOGNITION.md) and
  [DICTATION.md](../recognition/DICTATION.md): how dictation works
- [WINDOWS-PLAN.md](../standalone/WINDOWS-PLAN.md): remaining Windows work
- [LICENSING.md](../LICENSING.md): component licences
- [Wine patches](../patches/) and [WINE-SOURCE.md](../scripts/ci/WINE-SOURCE.md):
  the custom Wine build
- [history/](history/): the original Wine prototype's testing and validation

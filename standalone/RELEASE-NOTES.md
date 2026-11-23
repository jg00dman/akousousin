<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin 0.9

A new control panel, more reliable dictation, and an app that is ready when you
are. Your voices, models, Wine registrations and Speech Dispatcher setup carry
over from 0.8.

**New control panel.** Eight clear pages: Home, Voices, Dictation, Shortcuts,
Apps, Advanced, Privacy and About. It follows your desktop's light or dark
colours and language, and works well with a keyboard and screen reader. Spanish
is the first translation. [See it](https://github.com/jg00dman/akousousin/blob/main/docs/SCREENSHOTS.md)

**Dictation**

- Fixed text being typed over and over ("Okay. Okay. Okay.").
- Background noise, such as fans, hum, music and typing, no longer turns into
  stray words.
- Uses PipeWire directly where available; PulseAudio still works.
- A live microphone level on the Dictation page.

**Ready when you are**

- Akousousin can start at login and wait in the tray with its shortcuts
  working. It asks the first time you open it.
- Your voice and dictation model stay loaded, so there is no wait. To save
  memory instead, see Advanced → Startup and memory.
- It quits cleanly when you log out.

**Also**

- Privacy page: what stays on your computer, the few uses of the internet, and
  a switch to block them all. Models download only when you ask.
- Tray: click or tap to dictate, or right-click or press and hold for the menu.
- `akousousin --version`.

Windows support remains experimental.

[Full history](https://github.com/jg00dman/akousousin/blob/main/CHANGELOG.md) ·
[User guide](https://github.com/jg00dman/akousousin/blob/main/standalone/README.md)

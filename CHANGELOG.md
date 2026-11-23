<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Changelog

Stable releases. Each beta's notes are on its
[release page](https://github.com/jg00dman/akousousin/releases).

## 0.9.1.2

- Spiel speech provider, alongside Speech Dispatcher.
- French, German, Portuguese, Korean, Simplified and Traditional Chinese.
- No polling while idle: the tray, voice service, control panel, Speech
  Dispatcher module and Spiel provider wait for changes instead of checking.

## 0.9.1

- Whisper Base is included, so dictation works without a download.
- Orca speaks with Akousousin chosen as its synthesizer; updates take effect
  without logging out.
- First word no longer cut off; ready sound plays reliably.
- Tray icon readable on dark panels; animates for SAPI speech.
- Wine prefixes are found for you; Browse shows hidden folders.
- tar.gz installer quits Akousousin itself; `--quit` waits; links open.

## 0.9.0

- New control panel with eight pages, light and dark colours, screen reader
  support and translations (Spanish first).
- Dictation: fixed repeated text; Silero speech detection ignores background
  noise; native PipeWire; microphone level meter.
- Start at login, models kept loaded, clean exit at logout.
- Privacy page, with a switch to block all internet use.
- `--version`.

## 0.8.3

- `akousousin --purge` removes Akousousin completely, including voices, models
  and settings. It asks first; `--yes` skips the question.

## 0.8.2

- The Wine compatibility DLL is no longer limited to Wine 11.21.

## 0.8.1

- Packages include an English starter voice, so a fresh install can speak
  without a download.

## 0.8.0

- First stable release: Piper voices for Windows apps in Wine (SAPI) and for
  Linux apps (Speech Dispatcher), global reading shortcuts, experimental
  Whisper dictation, the voice library and AppImage updates.

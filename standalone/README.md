<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin user guide

Akousousin reads text aloud and types what you dictate, in any app on your
Linux desktop, and gives Windows apps in Wine a voice. Everything runs on your
computer. [Screenshots](https://github.com/jg00dman/akousousin/blob/main/docs/SCREENSHOTS.md)

- [Install](#install) · [First start](#first-start) · [Voices](#voices) ·
  [Reading aloud](#reading-aloud) · [Dictation](#dictation) · [Apps](#apps)
- [Startup and memory](#startup-and-memory) · [Privacy](#privacy) ·
  [Updates](#updates) · [Removing Akousousin](#removing-akousousin)
- [Files](#where-things-are-kept) · [Command line](#command-line) ·
  [Troubleshooting](#troubleshooting)

## Install

Download from the [latest release](https://github.com/jg00dman/akousousin/releases/latest).
You need 64-bit Linux with glibc 2.35 or newer (Ubuntu 22.04, SteamOS 3 and
most current distributions) and PipeWire or PulseAudio.

**AppImage (recommended).** Make it executable and open it:

```sh
chmod +x Akousousin-x86_64.AppImage
./Akousousin-x86_64.AppImage
```

Akousousin offers to move itself to `~/.local/share/Akousousin/` and add a menu
entry. Choose No to keep it where it is.

**Linux tar.gz**, for systems without AppImage support. No root needed:

```sh
tar -xzf Akousousin-Linux-x86_64.tar.gz
Akousousin/install.sh
```

It installs to `~/.local` and adds a menu entry.

**Windows ZIP.** Experimental and not yet complete; dictation and shortcuts are
not available on Windows yet.

## First start

An English voice is included, so Akousousin can speak straight away. The first
time the window opens, it asks whether to **start at login**. Say yes, and
Akousousin waits in the tray with its shortcuts working, without a window.

The **Home** page shows whether reading aloud and dictation are ready. Try both
there before setting up shortcuts.

## Voices

The **Voices** page lists 178 voices in 53 languages.

- Select a voice to hear a sample, then **Download** it. Its licence is shown
  first.
- **Make default voice** sets the voice used when an app doesn't say which language
  it needs.
- **Use for [language]** sets the voice for that language. Apps that ask for a
  language get that language's voice.
- Speed and volume are on the same page.
- **Import a Piper voice…** adds a voice you already have (an `.onnx` file
  with its `.onnx.json` beside it).

## Reading aloud

On **Shortcuts**, choose **Turn on** for the reading shortcuts and approve them
when your desktop asks.

- **Ctrl+Alt+R** reads the text you have selected. Press it again to stop.
- **Ctrl+Alt+Shift+R** reads copied text. Use this for apps, including some
  Windows apps, where selecting is not enough: copy with Ctrl+C first.

You can change the keys in your desktop's shortcut settings. Turning on the
reading shortcuts also sets up [Speech Dispatcher](#linux-apps-and-screen-readers).
On desktops that don't offer to approve shortcuts, choose **Add desktop action**
on the Shortcuts page and bind it to keys yourself.

## Dictation

Dictation types what you say into the app you are using. It needs Plasma or
GNOME on Wayland. On GNOME, also set up the Akousousin Focus extension shown on
the Dictation page, so dictation knows which window to type into.

1. On **Dictation**, choose a model under **Speed and accuracy** and
   **Download** it: Fastest, Balanced or Most accurate. Larger models are more
   accurate but slower; Balanced suits most computers.
2. Choose **Set up shortcut** and approve it. The suggested keys are
   **Ctrl+Alt+Space**.
3. Choose **Hold to talk** (speak while holding the keys) or **Press to start
   and stop**.
4. Check the **language** and **microphone**. The level bars move when the
   microphone hears you.

Use **Try it** on the Dictation page to dictate without typing into another
app. You can also click or tap the tray icon to start and stop dictation.

## Apps

### Windows apps in Wine

On **Apps**, choose **Add a Wine prefix…**, pick the prefix your Windows app
is installed in, then **Register voices**. Restart the app so it sees the
voices. Logos users: choose your Logos prefix, then use Logos Read Aloud as
usual.

Akousousin doesn't change Wine's own files. **Remove…** restores the prefix as
it was. After downloading new voices, choose **Update** so Windows apps see
them.

### Linux apps and screen readers

On **Apps**, turn **Speech Dispatcher** on. Orca, Firefox's Read Aloud and
other apps that use Speech Dispatcher can then use Akousousin voices. Your
other speech engines stay available, and turning it off restores the previous
default. Speech Dispatcher restarts when you change this, so Orca pauses for a
moment.

## Startup and memory

By default your voice and dictation model load when Akousousin starts, and stay
loaded, so there is no wait the first time you read or dictate. To save memory
instead, go to **Advanced → Startup and memory**. There you can load them only
when first used, unload them after a period of not being used, or turn start at
login on or off.

Closing the window leaves Akousousin running in the tray. **Quit** in the tray
menu stops it. It also stops when you log out.

## Privacy

Text you hear and your voice when you dictate never leave your computer. The
recording is discarded once it has been written down. Akousousin uses the
internet only to check weekly for updates, to download voices and models you
choose, and to play voice samples. The **Privacy** page shows each of these,
and can block all of them.

## Updates

Akousousin checks for a new version once a week, which you can turn off in
Privacy. The AppImage can update itself from **Advanced → Updates**. For the
tar.gz and the Windows ZIP, download the new version and install it the same
way. Turn on **Include test versions** to try beta releases.

## Removing Akousousin

- **Everything:** **Advanced → Remove everything…** or `akousousin --purge`.
  This removes Akousousin from your Wine prefixes, Speech Dispatcher and start
  at login, along with its voices, models and settings.
- **Tar install only:** `~/.local/lib/akousousin/uninstall.sh` removes the
  program but keeps your voices, models and settings.
- **One Wine prefix:** **Apps → Remove…**.

## Where things are kept

| What | Where |
| --- | --- |
| Settings | `~/.config/Akousousin/settings.json` |
| Voices and dictation models | `~/.local/share/Akousousin/` |
| Log | `~/.local/state/Akousousin/akousousin.log` |
| Start at login | `~/.config/autostart/org.akousousin.Akousousin.desktop` |

On Windows, settings and voices are in `%LOCALAPPDATA%\Akousousin`.

## Command line

| Command | Does |
| --- | --- |
| `akousousin` | Open the window |
| `akousousin --read-selection` / `--read-clipboard` / `--stop-reading` | Read aloud, or stop |
| `akousousin --dictation-toggle` | Start or stop dictation |
| `akousousin --status` | Show whether Akousousin is running |
| `akousousin --quit` | Stop Akousousin |
| `akousousin --purge` | Remove everything (asks first; add `--yes` to skip) |
| `akousousin --version` | Show the version |

With the AppImage, use its path in place of `akousousin`. To register a Wine
prefix from a script, see [CLI-REGISTRATION.md](https://github.com/jg00dman/akousousin/blob/main/standalone/CLI-REGISTRATION.md).

## Troubleshooting

- **Something isn't working.** **Advanced → Copy diagnostic report** copies
  versions and settings, but nothing you have read or dictated. Include it
  in an [issue](https://github.com/jg00dman/akousousin/issues). **Open service
  log** shows the log.
- **A Windows app doesn't list the voices.** Restart the app. If you downloaded
  voices since registering, choose **Update** on Apps.
- **Shortcuts don't respond.** Check that Akousousin is in the tray, and that
  the keys are approved in your desktop's shortcut settings.
- **Dictation types nothing.** Check the microphone level bars on the Dictation
  page, and that the window you want to type into has focus.
- **Downloads fail with a certificate error on SteamOS** (older versions):
  start Akousousin with `SSL_CERT_FILE=/etc/ssl/cert.pem`.

What each speech interface supports is listed in
[COMPATIBILITY.md](../COMPATIBILITY.md).

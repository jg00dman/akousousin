<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Testing a beta

Thank you for testing. Turn on **Advanced → Include test versions** to be
offered betas, or download one from the
[releases page](https://github.com/jg00dman/akousousin/releases). Your voices,
models and settings are kept.

## A quick check

1. **Install:** open the AppImage, or run `install.sh` from the tar.gz.
   Accept the offers to install and to start at login.
2. **Read aloud:** on Home, choose **Speak**. Then select text in another app
   and press Ctrl+Alt+R; press again to stop.
3. **Dictate:** press Ctrl+Alt+Space in a text editor, say a sentence, and
   check the words, capitals and punctuation. Try a quiet room and a noisy one.
4. **Windows app:** register your Wine prefix on Apps, restart the app and
   use its read-aloud feature.
5. **Log out and in:** the tray icon appears and shortcuts work. Exactly one
   Akousousin controller is running:
   ```sh
   ps -eo pid,etime,args | grep '[a]kousousin.*--controller'
   ```
6. **Light and dark:** switch your desktop's colours with the window open.

## Reporting a problem

Open an [issue](https://github.com/jg00dman/akousousin/issues) with:

- what you did, what you expected and what happened;
- your desktop and distribution (for example SteamOS 3.7, Plasma, Wayland);
- **Advanced → Copy diagnostic report**, which leaves out anything you read
  or dictated.

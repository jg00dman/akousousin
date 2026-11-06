<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Voice Input — beta testing guide

Use the direct `Akousousin-x86_64.AppImage` link in the beta or trial release, make it
executable and launch it. The AppImage is the only download needed for testing;
matching sources and checksums are separate release assets, and diagnostic
artifacts remain on the GitHub Actions run. Open
**Voice Input**. This trial includes the current main-branch panel and Updates page.
It retains the existing TTS features; Whisper recognition is still experimental.

Whisper speech models are NOT bundled. They are retained in
`~/.local/share/Akousousin/models/whisper/` (respecting `XDG_DATA_HOME`).

To reuse your first test download, choose **Import existing model…**, then select
its `models/small` folder (the folder containing `model.bin`). Alternatively,
**Enable voice input** downloads Small once, about 485 MB. Wait for **Ready**.
Turbo currently supports importing converted local models.

Install microphone/audio utilities if needed:

```sh
sudo apt install pulseaudio-utils
```

Click **Start recording (10 seconds)**. Wait for the two short 300 Hz tones and
**Listening — speak now**, then speak. The transcript and detected language appear
in the panel. The model stays loaded for subsequent recordings. Try silence and
another language too. The sound can be disabled. **Test ready sound** plays the
two tones without loading a model or recording; it uses the system default
playback device. If playback completes silently, check AKS output routing and
volume in KDE audio settings. **System default** follows the Linux default microphone; choose a named input
from the dropdown or use Refresh after connecting a device. **Automatic detection**
keeps language detection enabled. Choose… opens a searchable, scrollable language
list, and the panel shows the last automatically detected language separately.

Closing the panel leaves the shared controller and recognition worker available.
Disable voice input, idle model unloading or Quit releases model memory. Imported/downloaded
models survive closing, updates and replacement of the AppImage. Do not delete the
earlier bundle until model import finishes successfully.

Desktop dictation is experimental in this trial. Quit the older AKS controller
first, then choose Enable desktop shortcuts in Voice Input and approve KDE's
shortcut and keyboard-control dialogs. Default mode is toggle; push-to-talk is
also available. Test in a plain text editor. Switching windows retains the result;
a switch during insertion may leave a partial result. Cancel is available in the
panel and tray. Closing the panel leaves the shared worker/controller running.
See recognition/DICTATION.md in the corresponding source for implementation,
limitations and acceptance checks. SAPI recognition remains unimplemented.
Microphone capture and dictation into Kate were confirmed on Kubuntu 26.04 Wayland
on 5 November 2026. The ready cue was enabled but inaudible; use Test ready sound
to check playback in the newer trial. Other desktop acceptance cases remain open.
Existing SAPI support is text-to-speech only. Full dependency licences and matching
sources accompany the build as separate downloads. No Whisper model weights occur in the AppImage;
the small bundled VAD asset and existing approved Piper starter voice remain.

No configuration reset is required when updating from the trial that reported
“An app id is required.” The updated controller registers its portal connection
with a stable application identity before requesting shortcuts. The entry is now
prepared at controller startup and unchanged entries are retained; registration
retries briefly while the desktop cache catches up. Quit the old AKS
from its tray and launch the new build; keep your models and preferences.

If “App info not found” persists despite a valid launcher, quit active portal
sessions and run `systemctl --user restart xdg-desktop-portal.service`, then enable
shortcuts again. This resolved the failure in the confirmed Kubuntu/Kate test;
no AKS configuration or model reset was needed.

The model control is a single Enable voice input / Disable voice input button.
Disable stops recognition and frees model memory without deleting downloads;
the dictation shortcut or Start recording can enable it again. The first activation
can download Small in a cancellable worker. Desktop shortcuts still require KDE's
permission setup once per AKS run. Start Dictation in the tray can open that setup.

The tray menu is Start/Stop Speech, Start/Stop Dictation, Default Voice, Configure,
Quit. A single left-click opens it; a double-click opens Configure. Closing a panel
leaves the controller available. Quit closes all panels launched by that controller,
microphone capture, recognition and speech workers and portal sessions.

Voice Input and Settings have a vertical scrollbar and wheel scrolling; the voice
library also exposes scrollbars. The initial window fits the available screen and
Settings remains accessible at smaller sizes. The two ready tones now use 300 Hz
and a peak of 32700/32767 (about +10.3 dB from the previous trial); a full +12 dB
at the previous amplitude would clip.

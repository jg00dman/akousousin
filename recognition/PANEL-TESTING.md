# Whisper Voice Input panel trial

Download `Akousousin-x86_64.AppImage`, make it executable and launch it. Open
**Voice Input**. This trial includes the current main-branch panel and Updates page.
It retains the existing TTS features; Whisper recognition is still experimental.

Whisper speech models are NOT bundled. They are retained in
`~/.local/share/Akousousin/models/whisper/` (respecting `XDG_DATA_HOME`).

To reuse your first test download, choose **Import existing model…**, then select
its `models/small` folder (the folder containing `model.bin`). Alternatively,
**Enable / prepare model** downloads Small once, about 485 MB. Wait for **Ready**.
Turbo is import-only in this trial.

Install microphone/audio utilities if needed:

```sh
sudo apt install pulseaudio-utils
```

Click **Record 10 seconds**. Wait for the two short 250 Hz tones and
**Listening — speak now**, then speak. The transcript and detected language appear
in the panel. The model stays loaded for subsequent recordings. Try silence and
another language too. The sound can be disabled. Blank microphone means the system
default; blank language means automatic detection.

Closing the panel unloads its diagnostic recognition worker. Imported/downloaded
models survive closing, updates and replacement of the AppImage. Do not delete the
earlier bundle until model import finishes successfully.

This trial does not yet implement global hotkeys, text insertion, or SAPI recognition.
The ready cue and live microphone behavior need testing on your KDE Wayland desktop.
Existing SAPI support is text-to-speech only. Full dependency licences and matching
sources accompany the build. No Whisper model weights occur in the AppImage;
the small bundled VAD asset and existing approved Piper starter voice remain.

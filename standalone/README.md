<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin — Neural Voice Engine

**akousousin:** *The unified neural speech engine for Linux, implementing Microsoft SAPI and Speech Dispatcher, based on Piper and Whisper.*

The 0.7.0b11 beta implements SAPI text-to-speech using Piper, native Linux Speech
Dispatcher output and experimental local Whisper voice input on Linux. SAPI
recognition and native Windows microphone capture are not implemented. See the
[compatibility table](../COMPATIBILITY.md) for the implemented capabilities.


[Beta downloads](https://github.com/jg00dman/akousousin/releases) · [Builds and validation](https://github.com/jg00dman/akousousin/actions).

One speech service and configuration per operating-system user. This beta contains
the standalone 64-bit SAPI engine, control panel, tray and Piper/Waitress backend.
The default package contains no Piper voice or Whisper model weights and no Wine
runtime. On first use, Overview offers the reviewed en_US-ljspeech-medium voice
(about 64 MB), or a choice from Voice library. Downloads retain upstream model
cards, checksum provenance and licence declarations. Voices stay installed in the
user data folder across upgrades. Existing selected voices are preserved. An
optional build includes LJSpeech for offline first use.

## Linux installation and storage

OuDedetai installs the AppImage to `~/.local/share/Akousousin/Akousousin-x86_64.AppImage`.
When launched from elsewhere, the control panel offers to move the AppImage to
that location and add an application-menu shortcut with a persistent AKS icon.
Choose No to keep running portably; Settings → AppImage installation lets you
retry later. An existing destination requires confirmation before replacement.
The copy is verified before registrations are refreshed and AKS restarts; the
unchanged original is removed only after the restart command succeeds. Existing
voices, models and preferences are kept. Launching an AppImage already at the
recommended path creates/refreshes its menu shortcut without a move prompt.
Custom desktop entries are preserved. The header displays the actual AKS icon.
The Ubuntu 22.04 / x86-64 / glibc 2.35+ build target is unchanged.

- Preferences: `~/.config/Akousousin/settings.json`.
- Downloaded voices: `~/.local/share/Akousousin/voices/`.
- Whisper models: `~/.local/share/Akousousin/models/whisper/`, retained between upgrades.
- Imported Piper models remain in the location you explicitly select. Whisper
  imports are copied into the persistent Whisper cache.
- Logs: `~/.local/state/Akousousin/akousousin.log`.
- Private session/socket/control files: `$XDG_RUNTIME_DIR/Akousousin/`, with a
  private `/tmp/akousousin-<uid>/Akousousin/` fallback when no runtime directory exists.

XDG directory overrides are respected. Piper and Python stay inside the AppImage.
Its temporary extraction remains alive while Akousousin runs; no additional runtime
copy is stored in the data directory. Existing `runtimes/` copies from older betas
are no longer used. Old OuDedetai-specific settings are not copied implicitly.

Close Logos before registering an existing initialized 64-bit Wine prefix:

```bash
export APPIMAGE_EXTRACT_AND_RUN=1
IMAGE="$HOME/.local/share/Akousousin/Akousousin-x86_64.AppImage"
chmod +x "$IMAGE"
"$IMAGE" --download-starter-voice  # one-time download; omit if a voice is already installed
"$IMAGE" --wine-prefix "$HOME/wine-bisect-prefix/data/wine64_bottle" \
  --wine "$HOME/akousousin/wine-akousousin-piper-11.21-logos-x86_64.AppImage" --install-only
"$IMAGE"
```

Startup itself never downloads weights. On a fresh installation choose Download
starter voice in Overview, import an `.onnx` file (matching `.onnx.json` alongside),
or review and download one in Voice library. The first installed voice becomes
the default; subsequent downloads preserve your selection. Optional offline
builds copy the bundled starter into the same persistent voice library. Select Make default, then Settings → Install /
apply voice registration. Overview → Start server → Play sample tests real Piper and
playback. Next test Logos Read Aloud using the same Wine package.

## Removing voices and playback speed

Select an installed entry in Voice library and choose **Delete voice…**. Confirm
before deletion. AKS stops its speech service, removes the library entry and
cleans its language preferences. Downloaded voice files in the managed cache are
deleted; imported original files and their configuration files are retained.
Deleting the default selects another installed voice. Deleting the last voice
leaves speech unavailable until another is installed; the starter is not silently
reinstalled. Use **Settings → Install / apply voice registration** afterwards to
remove stale SAPI voice tokens, and restart applications that cache their lists.

Default speed ranges from **0.5 to 4.0**, in **0.25** steps, with a stepped slider
and a value control that avoids excessive decimal places. Application rate
requests still combine with the shared default speed.

## Tray and lifecycle

The original Akousousin waveform artwork is shared by the AppImage, window and tray.
A tray badge reports stopped, starting, running or error. Downloads add a blue
arrow/progress ring and their byte counts/percentages to the tooltip and menu;
failed downloads briefly show a red indicator. The control panel shows a separate
progress bar for each download across all pages. Known-size transfers use actual
bytes received; connection, verification and unknown-size stages show activity
without a guessed percentage. Its menu provides
Start/Stop Speech, Start/Stop Dictation, Default Voice (grouped by readable
language names), Configure, Quit. Left-click toggles desktop dictation; right-click
opens the menu. Configure opens the control panel.
Default changes apply to subsequent speech; applications caching a SAPI voice may
need restarting. Newly downloaded voices need registration through Settings.

If Speech Dispatcher registration is saved but restarting fails, the panel offers
a selectable command with Copy command and separate technical details. Run the
command in your normal terminal without sudo. Registration/restart uses the host
system libraries rather than inheriting AppImage library overrides.

Closing the configuration panel leaves Akousousin/Piper running. Tray Quit stops
Piper, microphone capture, recognition/download workers and portal sessions, closes
control panels launched by that controller and exits Akousousin. It warns when
application speech sessions are active. An
application releasing the last session also stops Piper and exits Akousousin when
Akousousin was started automatically. An independent/manual start is left running.
On desktops without a tray, the panel and command interface remain usable.

## Launcher interface, version 2

```bash
"$IMAGE" --protocol-version                         # prints 2
"$IMAGE" --configure                                # configuration, no independent ownership
"$IMAGE" --acquire-session unique-id --owner-pid PID  # start/reuse and wait until ready
"$IMAGE" --release-session unique-id                 # release only that session
"$IMAGE" --status                                    # JSON status, does not start anything
"$IMAGE" --start-server                              # independent/manual start
"$IMAGE" --stop-server                               # explicit backend stop, tray remains
"$IMAGE" --quit                                      # stop speech/input, close panels and exit
"$IMAGE" --dictation-toggle                          # KDE dictation; starts permission setup if needed
"$IMAGE" --dictation-cancel                          # discard pending dictation
"$IMAGE" --dictation-status                          # shared voice-input status/transcripts
"$IMAGE" --read-selection                            # read selected text, repeat to stop
"$IMAGE" --read-clipboard                            # explicitly read copied text, repeat to stop
"$IMAGE" --stop-reading                              # stop only the AKS reader
"$IMAGE" --selection-status                          # reader and global-shortcut status
"$IMAGE" --install-selection-action                  # optional manually bound desktop action
```

Use a distinct random ID per application session; repeat acquisition is idempotent.
The owner must be a running process. Akousousin checks its creation time and reaps
sessions whose owners exit, including launcher crashes. One session ending never
stops another's speech. The public commands return nonzero on errors; launchers
can still run their application without speech. Only Akousousin manipulates its own
private controller files. `--settings` remains a diagnostic/test override.

## Compatibility and rollback

This beta supports 64-bit callers only. Wine 11.21 prefixes missing the generic
SAPI enumeration fix use `C:\Program Files\Akousousin\compat\x64\sapi.dll`.
The installer redirects Wine SAPI COM default values to that private DLL and sets
`native,builtin`; Wine system DLL files and PATH remain unchanged. Original COM
default values and the override are saved for rollback/uninstall. Other Wine
versions needing that fix are refused rather than guessed.
Remove launcher-forced `sapi=b` when the compatibility DLL is required.

Settings → Uninstall & restore (or `--uninstall --wine-prefix ... --wine ...`)
restores original registry settings/defaults and removes or restores AKS-owned
private DLLs. It keeps voices
and preferences. Native Windows system SAPI is never replaced: extract the
Windows ZIP, use the same control panel/tray, and register with `--install` from
an administrator terminal. Windows data/config are under LocalAppData/Akousousin.

Language routing uses SAPI hints or a manually selected book language; automatic
foreign-word detection and full localisation are not implemented. Standard Piper
has no general pitch slider. Arabic/Hebrew auxiliary Piper output models are not distributed. This is separate
from multilingual Whisper input, which includes those language tokens but has
variable recognition accuracy. Model licences
vary; upstream cards and provenance are retained when downloading.

Original project code is GPL-3.0-or-later, copyright 2026 John Goodman, with
LGPL-2.1-or-later for the SAPI engine C code/API headers. Wine, Piper, Qt/PySide
and other dependencies retain their upstream terms and notices. Both application
packages include the GPL and LGPL texts and the component-licensing explanation. The source archive
includes matching Wine, Piper, eSpeak, Qt and PySide sources. Automated deterministic
WAV checks, real Piper output and session tests do not establish audible playback
or every Logos desktop behavior; test in a backed-up prefix.

## Checking for application updates

If a saved Wine executable/AppImage has been removed, registration refresh skips
that entry with a warning and continues updating other integrations. The warning
appears in the panel status and Updates page; its saved registration is retained
for repair in Settings. Other registration errors still fail the update. During
relocation the original AKS download is retained if skipped registrations might
still reference it. Correct the Wine path and apply registration for that prefix
before removing the old download. This behaviour is in source after beta 10.

Update checks and notifications are available in every format. Only an AppImage
launch offers installation of application updates. Standalone tar, Flatpak,
distro packages, Windows ZIP and source installations link to the release download
page and use their installer or software manager instead. Voice/model downloads remain
available independently in every format. Packaging records its distribution type
in `resources/build.json`; AppImage controls also require a valid executable
`APPIMAGE` path. A renamed executable alone does not enable self-updating.

## Standalone Linux tar installation (no AppImage runtime or FUSE)

AppImage remains the recommended/default Linux download. Alternatively download
`Akousousin-Linux-x86_64.tar.gz` (not the corresponding-sources archive). The tar
bundle includes the same application, Python runtime, private dependencies,
clipboard helpers and GPL/LGPL/dependency licence notices. It does not include
Wine or voice/model weights by default. It requires x86-64 Linux with glibc 2.35+
and the same host audio/desktop capabilities as the AppImage.

Quit AKS from its tray, then extract and install without sudo:

```sh
tar -xzf Akousousin-Linux-x86_64.tar.gz
cd Akousousin
./install.sh
~/.local/bin/akousousin --configure
```

After installation, `install.sh` offers to launch the installed control panel
when run in a terminal. The default answer is No. Use `./install.sh --quiet` to
skip this question during automated installation; errors are still reported.
Non-interactive installations do not prompt or launch the application.

The installer creates the application-menu entry and icon by default. It also
invokes the installed AKS executable's `--install-speech-dispatcher` command:
this is the same setup implementation used by the panel, not a second installer
configuration path. With an installed voice, AKS becomes the default output
module; existing eSpeak, Spiel and other engines stay available. With no voice,
the module is registered and default selection is deferred until the first voice
download/import completes. No model is downloaded by the installer.

Use `./install.sh --without-speech-dispatcher` to skip this setup. `--quiet` only
suppresses the launch question. If the daemon is missing or cannot restart, the
application installation remains valid and the installer prints recovery details;
the panel also retains setup warnings. Speech Dispatcher itself is a host package
and is not installed using sudo by AKS.

The per-user installer places executables/private libraries in
`~/.local/lib/akousousin`, a launcher in `~/.local/bin`, and a menu entry and icon
under `${XDG_DATA_HOME:-$HOME/.local/share}`. If `~/.local/bin` is not on PATH,
use the full launcher path or application-menu entry. `./install.sh
--bundle-prefix /absolute/path` changes the executable prefix; XDG_DATA_HOME still
controls desktop integration. This is a per-user installer, not a system package
installer; root execution is rejected. It uses its own bundled runtime and does
not require system Python.

For upgrades, quit AKS, extract the new archive separately and rerun its installer
with the same prefix and XDG environment. Installation stages a complete copy,
preserves the previous installation for rollback during replacement, and rejects
unowned/conflicting launcher files. Voice/model caches and configuration retain
their existing XDG locations. Wine registration remains explicit in Settings;
Speech Dispatcher setup uses the shared AKS command described above.

Run `~/.local/lib/akousousin/uninstall.sh` to remove this application installation.
It removes unchanged installer-owned launchers/icons and restores any previous
managed AKS desktop entries. Modified external files, configuration, downloaded
models/voices and Wine registrations are preserved. Bundle removal invokes AKS's
own removal command for Speech Dispatcher only if its managed launcher points to
that installed executable; other engines and their original default are retained.
If removing AKS entirely, first remove its Wine registrations using Settings.
Quit AKS before uninstall.
The tar update notification opens the release page; rerun the new installer to
upgrade. It cannot perform AppImage replacement.

On the Updates page:

- **Check for updates weekly** is enabled by default. Checks run quietly while AKS
  is running and remember their timing across restarts. Failed checks retry after
  an hour. Turning this off leaves manual Check for updates available.
- **Show beta testing updates** defaults on for beta installations and off for
  stable installations; saved choices survive upgrades. Turning it off offers
  only newer stable releases. An installed `0.7.0b1` stays installed until stable
  `0.7.0` or a later stable release is available; it never downgrades to `0.6.x`.
- Automatic notifications offer **Update now…** (opens Updates for review and
  installation) and **Remind me later** (one week). They wait while AKS is speaking,
  reading or processing dictation. The tray also shows an available-update action.
  Neither checking nor notification installs an update automatically.

Accepting an update downloads and verifies its SHA-256 and size before stopping
speech. The shared panel/tray progress shows Downloading update with byte counts,
then indeterminate Verifying update, Applying update and an explicit restarting
warning for three seconds. After relaunch the panel briefly confirms the installed
version. Close Wine applications first; voices, models and preferences are retained.

The AppImage is replaced at its registered path and saved SAPI registrations are
refreshed. The previous image is kept alongside it as `.AppImage.previous`; a
failed registration restores the previous image and attempts to restore its
registrations. A second simultaneous update is refused. Speech starts on demand
as usual. Release tags include a package version; older run-number-only tags are
not offered as updates. Each new release must increase the package version.

## HTTPS certificates on SteamOS and other Linux distributions

Downloads verify both the certificate chain and hostname. The application loads
standard host CA bundles, including SteamOS/Arch's `/etc/ssl/cert.pem` and
`/etc/ca-certificates/extracted/tls-ca-bundle.pem`, rather than depending only on
Ubuntu's compiled OpenSSL paths. Explicit `SSL_CERT_FILE` / `SSL_CERT_DIR` settings
are honoured. A missing or invalid custom trust store is not bypassed.

For an older AppImage reporting `CERTIFICATE_VERIFY_FAILED: unable to get local
issuer certificate` on SteamOS, quit AKS fully and launch it with the host bundle:

```sh
SSL_CERT_FILE=/etc/ssl/cert.pem "$HOME/.local/share/Akousousin/Akousousin-x86_64.AppImage"
```

Use the actual AppImage path if running it from Downloads. This keeps certificate
verification enabled and requires no root access or system changes. If a network
uses a custom certificate authority, use its administrator-provided trust bundle
instead of disabling verification.

## Experimental Voice Input on Linux

![Voice Input model and dictation setup](../docs/images/voice-input.png)

This setup screenshot uses an isolated profile with the model unloaded. The
[recording controls screenshot](../docs/images/voice-input-recording.png) shows
the lower part of this scrollable page.

Recognition uses **faster-whisper with CTranslate2**, CPU int8 and one killable
worker. It does not ship the original OpenAI Whisper Python package or PyTorch.
Base.en is the compact English default, and multilingual Base is the default for
other supported locales. Small/Small.en are quality options. Turbo requires a
converted local import and is not presented as a CPU speed option; a failed
Turbo load falls back to installed Small.

Install `pulseaudio-utils` for `parec`/`paplay`; PipeWire remains your audio server
through its PulseAudio-compatible service. Enable voice input downloads the
selected pinned weights once if necessary and loads them. Disable stops
recognition and frees model memory, retaining downloads. Wait for the ready state
and two optional 300 Hz tones before speaking. Test ready sound checks playback
separately. Tones use cached, seekable WAV audio with a short device-wake lead-in.

Choose a named microphone or System default, and a language from the searchable,
scrollable picker. The initial language follows the supported system locale.
Multilingual (auto) explicitly detects the first nonempty phrase, then locks its
language for the rest of that recording session. Starting a new session detects
again. Start recording tests ten seconds and displays text.

Capture uses an adaptive energy endpointer with approximately 500 ms silence and
an 8-second cap. Endpointed input skips Whisper's redundant VAD pass; standalone
WAV transcription retains neural VAD. The read-only transcript display retains up to 200 phrases within its size limit.
Ctrl+A selects its contents; Copy transcript includes measurements.
Per-phrase timing shows voiced duration,
endpoint wait, audio length, recognition queue wait, recognition time, insertion
queue wait and insertion time. Timings also include estimated speech end to
recognition and first/last acknowledged key.
The speech end estimate uses the last above-threshold microphone frame; key
acknowledgements cannot measure when another application renders its text.
Recent transcripts stay in memory; numeric timings
and outcomes are logged without dictated text. Spoken punctuation commands are
not interpreted.

On KDE Wayland, enable desktop shortcuts and approve KDE's shortcut and keyboard
input dialogs. The proposed shortcut is Ctrl+Alt+Space, subject to KDE approval.
After successful approval, AKS remembers that desktop dictation is enabled and
restores its shortcut session when AKS next starts. This does not turn on the
microphone or load the model. RemoteDesktop portal version 2 supports requesting
persistent keyboard permission; AKS saves and rotates the returned restore token.
The desktop may still ask again if it does not support restoration or permission
has been revoked. Explicitly disabling desktop shortcuts clears that choice and
the token; quitting AKS preserves them. State is kept in a private
`settings.desktop.json` file beside `settings.json`.
Toggle listening is the default; push-to-talk is also available. A registered
shortcut can enable/load voice input again after it was disabled. Tray Start
Dictation can initiate permission setup when necessary. Stop/Cancel controls remain
in the panel, and cancellation is available from the command interface.

Voice Input and Settings support wheel scrolling and visible vertical scrollbars;
the voice library exposes vertical/horizontal scrollbars. The initial window fits
the available screen, and Settings remains accessible at smaller sizes.

[Voice Input testing and cache/portal troubleshooting](https://github.com/jg00dman/akousousin/blob/main/recognition/PANEL-TESTING.md)
explains the experimental limits. SAPI recognition, other Wayland compositors and
a general native input framework remain future work. No automatic word-processor
proofing-language tagging is implemented.

## Build with or without the starter voice

`python standalone/package.py` builds a model-free package by default. Add
`--bundle-starter-voice` for offline first use with the reviewed LJSpeech voice.
The Standalone Akousousin workflow exposes the same `bundle_starter_voice`
checkbox (off by default). Both variants retain their runtime dependencies and
licence notices; only the optional voice weights differ. Packaging clears staged
resources so an earlier offline build cannot leak weights into a lean build.

## Global read selected text / Stop

![Read selection setup and global shortcut controls](../docs/images/read-selection.png)

The screenshot shows the setup page before enabling the shortcuts.

On KDE Wayland, download/import a voice, open Read selection and choose Enable
global reading shortcuts. This installs Speech Dispatcher support and selects
AKS as its default engine first, then verifies the selected voice. Only after
success does it request KDE shortcut permission; setup errors leave shortcuts
disabled. Already-working support is verified without restarting the daemon.
Approve or change the suggested Ctrl+Alt+R (selected text) and Ctrl+Alt+Shift+R
(copied text) bindings in KDE. The panel shows the bindings KDE actually assigned.
These shortcuts work while another application has focus and while the panel is
closed, as long as AKS remains running in the tray. After successful approval AKS
remembers enablement and restores the session on its next launch; KDE retains the
chosen key assignments. Explicit Disable prevents automatic restoration. Builds
that did not save enablement require enabling once after upgrading.

Speech Dispatcher support can also be installed separately in Settings. eSpeak
remains available, and removing AKS support restores the earlier default.
The Linux AppImage bundles `wl-paste` (wl-clipboard) for Wayland and `xclip`
for X11 with their private libraries; no system installation is needed on SteamOS.
Source and distro packages need the corresponding system tools. Highlight text and press the shortcut once to read, again to stop
only that reader. Some Wine applications do not publish a primary selection;
copy their text and use the separate copied-text shortcut. There is no silent
fallback to stale clipboard contents. Native and Wine/Logos selection availability
still needs confirmation on the target desktop.

An optional desktop action can be installed from this page, or using
`--install-selection-action`, for manual binding in Plasma or other desktop
shortcut settings. It can start AKS when needed. `--read-selection`,
`--read-clipboard`, `--stop-reading` and `--selection-status` control the same
resident reader. Quit closes its shortcut session and stops its owned reading.
Configure reuses the existing control panel and requests activation of that window.

The control-panel status bar is selectable: use Ctrl+A/Ctrl+C or its Copy button
to include the full status in a support report.

While dictation is recording, AKS suppresses new speech output instead of pausing
microphone capture. This is temporary and profile-specific: saved volume and
Piper service availability are unchanged. Ready tones bypass suppression.
Speech requests received during recording are discarded without synthesis;
requests spanning a recording session cannot resume afterwards. The Speech
Dispatcher module cancels current AKS output, and previews stop their own player.
Suppression is released after recording/transcription ends, cancellation, or an
error; a terminated controller cannot leave a permanent mute behind.

Dictation language now defaults to the supported system locale. Base.en is the
compact English default; Base is the compact multilingual default with the chosen
language passed explicitly. Small/Small.en trade memory and CPU for quality.
Multilingual (auto) is explicit: the first nonempty phrase determines the language
for that recording session. Stop and start another session to detect again.
English-only models switch to their multilingual counterpart when another language
or auto is chosen. Turbo remains importable, with no CPU speed claim.

Voice Input offers CPU threads, Keep model loaded while voice input is enabled,
and an idle timeout (one hour by default when keep-loaded is off). More threads
are not always faster on CPU-limited systems; see the reproducible benchmark in
`backend/tools/benchmark_recognition.py`. Timing logs contain numeric measurements
and outcomes, never dictated text. Model cards accompany on-demand downloads;
model files and their upstream licences are not bundled into the AppImage.

Toggle-mode Stop cancels pending insertion immediately. Speech that finishes
recognising afterwards is retained for copying, never automatically typed. A new
session does not replay it. Push-to-talk submits on release. Keyboard events use
acknowledgements and pacing; a failed key release closes the keyboard session.
Recognition startup includes a real warm-up before Ready, so the initial prepare
may take longer while subsequent phrases avoid that lazy initialization.

<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin 0.9.0b2 beta

Fixes from testing 0.9.0b1:

- The panel now follows a light/dark switch straight away; no restart needed.
- Scroll bars are slim and rounded, closer to Plasma's own look.
- Dictation's cards stack in one column unless the window is wide, so its
  controls have room.
- Advanced › Open service log now opens the log in your desktop's viewer from
  the AppImage too; if that fails, the log's location is copied instead.

# Akousousin 0.9.0b1 beta — new control panel

A redesigned control panel, test build for the v1 interface. Speech, Wine SAPI
and Speech Dispatcher behaviour are unchanged.

- **Eight clear pages:** Home, Voices, Dictation, Shortcuts, Apps, Advanced,
  Privacy and About, with one main action per section and settings shown in
  place instead of in dialogs. Light and dark colour schemes follow the desktop.
- **Voices:** a Default voice chooser at the top, then one list of every voice
  grouped by language (in each language's own name). Select a voice to hear it,
  make it the default, use it for its language, download it after reviewing its
  licence, or remove it. Speed, volume and reading language are on the same page.
- **Dictation:** choose hold-to-talk or press-to-start, language, microphone and
  Fastest / Balanced / Most accurate, and try it without typing into other apps.
- **Privacy:** what always stays on this computer, the few uses of the internet
  (update checks, downloads you ask for, online voice samples) and a
  **Block all internet access** setting that turns those off. Starting
  dictation no longer downloads a missing model by itself; choose Download on
  the Dictation page.
- **Tray:** click or tap to start or stop dictation (or open Akousousin, set in
  Shortcuts); right-click or press and hold for the menu, which now includes
  Read selected text, Read copied text and Stop reading. The icon shows Ready,
  Listening (green microphone with a breathing glow) and Reading (the logo lines
  rising and falling); movement follows the desktop's animation setting.
- **Advanced:** service status and restart, memory, voice character, updates,
  a diagnostic report that leaves out anything read or dictated, and Remove
  everything.
- The interface is ready for translation and follows the system language; a
  Spanish translation is included for review.
- Earlier unreleased changes on this branch: GNOME Wayland dictation with the
  Akousousin Focus extension, late tray registration on X11, direct AppImage
  and tar downloads.

# Unreleased

- Add `--version` to print the application version and exit without starting the
  controller, opening the panel or creating preferences.
- When microphone capture cannot find `parec`, report the Ubuntu/Debian install
  command (`sudo apt install pulseaudio-utils`) instead of a raw file-not-found
  error. Capture still uses the existing PipeWire/PulseAudio-compatible path.

# Akousousin 0.8.3

Stable release of the `--purge` feature introduced in 0.8.3b1 (PR #14).
Previous stable installations can receive this version through the normal
update check without enabling beta updates. This release has the same purge
implementation as the beta.

`--purge` asks for confirmation before removing managed voices, Whisper models,
settings, application files and integrations. `--yes` (or `-y`) supports
unattended use. The bundled starter voice and Wine-version restriction removal
are retained.

**Complete native Windows app support is forthcoming and not yet working end
to end.** Its ZIP remains experimental; this release does not add Windows
capture or global shortcuts.

# Akousousin 0.8.3b1 beta

Publish the merged `--purge` feature (PR #14). Unlike the existing uninstall
commands, purge also removes managed downloaded voices, Whisper models and
settings. It asks for confirmation; `--yes` (or `-y`) supports unattended use.

- Quit AKS, restore the selected Wine prefix's speech registration when the
  prefix exists, remove Speech Dispatcher integration and AKS desktop launchers,
  and remove the managed tar installation and application data.
- Continue remaining cleanup steps after a failure, report the problems, and
  return a nonzero exit status if anything failed.
- Keep the bundled LJSpeech starter voice and the removal of the Wine 11.21-only
  installation restriction from the previous releases.

This is a prerelease; enable **Show beta testing updates** to receive it through
the AppImage updater. Stable-only users remain on 0.8.2.

**Complete native Windows app support is forthcoming and not yet working end
to end.** Its ZIP remains experimental; this beta does not add Windows capture
or global shortcuts.

# Akousousin 0.8.2

Stable release. Remove the installer restriction that allowed the private SAPI
compatibility DLL only on Wine 11.21. Other Wine versions, including 11.22, are
no longer blocked by their version string. This enables testing those versions;
it does not claim runtime validation on every Wine release.

- Keep the existing compatibility probe and `--wine-compat` force-install option.
  The bundled compatibility DLL is still built from Wine 11.21. Its private
  location, registry override, rollback and uninstall behaviour are unchanged.
- Continue bundling the reviewed LJSpeech starter voice for fresh installations.
- No OuDedetai changes are required or included.

**Complete native Windows app support is forthcoming and not yet working end
to end.** Its ZIP remains experimental; Windows capture and global shortcuts
are not added by this release.

# Akousousin 0.8.1

Stable release. Official AppImage, Linux tar.gz and Windows ZIP packages now
include the reviewed English LJSpeech starter voice (`en_US-ljspeech-medium`,
about 64 MB). A fresh installation can register SAPI and speak without a separate
voice download. The voice is copied into the persistent per-user library.

- Keep existing working voice selections. Recover stale starter paths from the
  verified local cache, and choose a usable installed voice if the selected
  voice's files have disappeared. Deliberately deleted voices stay deleted.
- Additional voices and Whisper models remain on demand. Lean builds remain
  available with `--no-bundle-starter-voice` or by unticking the workflow option.
- No OuDedetai changes are required or included.

**Complete native Windows app support is forthcoming and not yet working end
to end.** Its ZIP remains experimental; this release does not add Windows
capture or global shortcuts.

# Akousousin 0.8.0

The first stable release: the same code as 0.7.0b11, which proved stable in testing.

The existing control panel is retained; the GUI workflow trial is parked.
**Complete native Windows app support is forthcoming and not yet working end
to end.** Windows capture/global shortcuts remain unimplemented; its ZIP is
experimental despite component CI coverage.

- Preview playback failures identify the selected audio player, exit status,
  captured error and saved WAV path. The existing selectable error dialog offers
  Copy command and Copy details. Prefer PulseAudio-compatible `paplay`, matching
  ready tones and capture, rather than selecting an installed `pw-play` without
  a usable PipeWire output node (the reported Manjaro failure). Retain `pw-play`
  and `aplay` when the preferred tools are unavailable.

- Keep the existing panel layout; the GUI workflow experiment is parked on its
  separate branch. Tar installation creates its menu entry by default and now
  invokes the installed AKS CLI for Speech Dispatcher setup. AppImage relocation
  uses the same command. AKS becomes the default while existing eSpeak/Spiel
  engines remain options. A model-free install defers default selection until a
  voice is downloaded/imported. Removal delegates to AKS's own unregistration
  command when the module belongs to this tar installation. `--quiet` and the
  upstream launch offer are retained; `--without-speech-dispatcher` skips setup.

- Fix standalone tar SAPI cold start when Wine supplies a foreign APPIMAGE or
  private-library environment. Registration stores the current package launcher
  explicitly and clears inherited Wine environment variables. Reapply existing
  voice registrations to update the launcher. CLI registration is documented in
  [CLI-REGISTRATION.md](CLI-REGISTRATION.md). This is not in beta 10 downloads.

- A saved Wine executable/AppImage that no longer exists no longer blocks
  registration refresh, application updates or AppImage relocation. Skip only
  that registration, keep its record for repair, and show a persistent warning
  in the panel status and Updates page. Other refresh failures still stop the
  operation. Relocation retains the original AKS download when a skipped
  registration may still use it. This fix is not in the beta 10 downloads.

# Akousousin 0.7.0b10 beta

- Add `Akousousin-Linux-x86_64.tar.gz` as a no-FUSE alternative. AppImage remains
  the default. The tar includes a per-user installer/uninstaller, private runtime,
  desktop/menu integration and matching bundled licence notices. Installation and
  upgrades preserve shared settings/models; failed replacement rolls back.
- Every format can check for updates and show notifications. Only an actual
  AppImage launch offers self-installation; tar and other installations open the
  release download page and use their installer or package manager.

**Complete native Windows application support is forthcoming and is not yet
working end to end.** The Windows ZIP is experimental: user testing found
voice-install settings failures and Whisper tokenizer decoding failures. Windows
global dictation/reading shortcuts, native microphone capture and desktop text
integration are not implemented. SAPI speech-output components have automated
coverage, but that is not evidence of a working complete Windows application.
See the [Windows work plan](WINDOWS-PLAN.md).

- Fix model JSON reads to use UTF-8 rather than the Windows default code page.
- Use unique settings staging files and bounded retries for Windows file locks.
  These fixes address failures reported in 0.7.0b9; Windows desktop retesting is
  still required before claiming complete Windows support.

# Akousousin 0.7.0b9 beta

**Windows support is forthcoming, not yet working end to end.** This beta's
Windows ZIP is experimental and lacks native dictation capture and global
reading/dictation shortcuts. User testing also identified voice-install and
Whisper-download failures; do not treat package CI success as desktop readiness.

- Use a single deterministic Whisper decoding attempt instead of retrying at
  multiple temperatures. Noisy fixtures reproduce substantial retry overhead;
  this does not guarantee accurate recognition of noise or a fixed response time.
- Add speech-end-to-recognition and speech-end-to-first/last-key diagnostics.
  Speech end is estimated from the last above-threshold captured frame. Key
  timestamps measure KDE acknowledgements, not application rendering. Copy
  transcript includes the new measurements. Reliable acknowledged delivery and
  Stop cancellation are preserved; shortcut defaults and Orca STOP are unchanged.

- Remember approved dictation and reading shortcut enablement across AKS restarts.
  Quit closes the live sessions while preserving that preference; explicit Disable
  prevents restoration. Startup restores shortcuts without starting recording.
- Request persistent RemoteDesktop keyboard permission on portal version 2 and
  save/rotate its restore token in a private settings sidecar. Desktop backends
  without restoration support may still prompt. Existing users must enable once
  after upgrading because earlier builds did not save this preference.

Trial checks: quit the old instance, enable each desired shortcut once, then
quit/relaunch and reboot. Verify shortcuts restore without opening the panel and
without recording automatically. Test first and subsequent dictation phrases in
Kate and the browser; copy all timings and compare with perceived delay. Stop
while recognition is pending and confirm no later typing occurs. Desktop prompt
restoration and visible text latency require testing on the target KDE system.

# Akousousin 0.7.0b8 beta

This trial addresses corrupted text, repeating keys and insertion continuing
long after toggle-mode Stop in beta 7. Real Kate/LibreOffice delivery still needs
confirmation on the target desktop; protocol tests alone cannot establish that.

- Toggle Stop now cancels the session's pending/in-flight insertion. Later
  recognition results remain in the transcript, and a new session cannot replay
  them. Push-to-talk retains its explicit submit-on-release behaviour.
- Keyboard events each wait for a portal acknowledgement and are paced. Key
  release is protected against cancellation; failed release disables and closes
  the keyboard session. The no-reply burst path has been removed.
- Transcript history grows to up to 200 phrases, with an IPC size bound. The
  larger display has a scrollbar, Ctrl+A, preserved selection and Copy transcript
  includes timings. The display is read-only so incoming keys cannot overwrite it.
- Whisper performs a real encoder/decoder warm-up before Ready. This moves lazy
  first-inference initialization before microphone capture; it does not remove
  startup cost. Cached workers remain available between sessions.
- Ready tones use seekable WAV playback with a 200 ms device-wake lead-in. Linux
  normally uses an anonymous RAM file. Tone amplitude is fixed; audible playback
  and device routing still need verification on SteamOS.
- Speech suppression ends when microphone capture closes, rather than waiting
  for delayed transcript-only recognition. No microphone gain/sensitivity control
  or system-wide microphone changes are introduced.

Quit the old AKS from its tray before launching this build, to close its old
keyboard session. Existing voices/models/preferences are retained; no reset or
model redownload is required.

Test Base.en + English with two CPU threads first. Check exact text in Kate and
LibreOffice, then stop with Ctrl+Alt+Space while work is pending. After Stop, no
further text should be automatically typed. Delayed results should be retained
only in Voice Input. Copy the diagnostics, check Ctrl+A, and test the ready tones.
Then start a new session and check that no old text reappears.

Small or unsuitable thread settings can still exceed real-time processing speed.
This remains phrase-based recognition: a three-second bound during uninterrupted
speech is not claimed. Church Cap's MIT-licensed rolling-caption design has been
reviewed, but no Church Cap code is included in this repair.

See the [beta checklist](https://github.com/jg00dman/akousousin/blob/main/standalone/BETA-TESTING.md)
and [recognition measurements](https://github.com/jg00dman/akousousin/blob/main/backend/WHISPER-VALIDATION.md).

# Desktop dictation development

This increment moves recognition into the per-user controller and implements KDE
Wayland shortcut dictation. It is experimental: state, protocol, capture-pipe and
real-model tests do not establish live KDE/portal compatibility.

## Use in a recognition-enabled build

Quit the previous AKS build from its tray before starting this build; the older
resident controller does not implement the new input commands. Import/download
Small as before. Assets stay in the approved XDG-aware
`~/.local/share/Akousousin/models/whisper/` directory.

Open Voice Input and select toggle (default) or push-to-talk. Choose Enable desktop
shortcuts, then approve the shortcut and keyboard-control dialogs provided by KDE.
Only keyboard control is requested; no screen capture, pointer control, clipboard
access, root helper or virtual input daemon is requested. The proposed shortcut is
Ctrl+Alt+Space, but KDE decides the actual binding shown in the panel.

Focus a text editor, use the approved shortcut, and wait for the ready tones before
speaking. Toggle mode keeps listening, endpointing phrases at approximately 0.8
seconds of silence. Push-to-talk recognizes while held, stops capture on release, then inserts its collected transcript (up to 4000 characters). Release all shortcut keys before expecting text; an unmodified key is convenient for initial testing. Long phrases are split
at 15 seconds. Stop recording flushes the last speech fragment; Cancel discards
pending recognition/insertion. A missed/early release while loading does not start
a microphone recording later. Recognition runs in one worker, reused between
recordings and panels, and unloads after 300 seconds idle by default.

Closing the panel leaves dictation available in the tray. Disable desktop dictation
closes its permission sessions and unloads the focus observer. Quit AKS closes all
input workers and sessions. The Recording test still displays text only. The most
recent five transcripts are kept in memory and shown with their language and output
status; Copy transcript is an explicit clipboard action. No transcript file is
written. Program updates do not bundle or remove speech model weights.

## Input and output implementation

Capture connects to the host PulseAudio-compatible server using `parec`, including
`pipewire-pulse`. It uses 20 ms mono 16 kHz PCM frames, bounded preroll and energy
endpointing (default RMS threshold 250). Each submitted phrase still uses Whisper's
neural VAD. There are at most two pending phrases. If inference cannot keep up,
capture stops with a visible error; it never grows an unbounded audio queue.
Microphone disconnect/timeout stops the session and reports an error; start a new
session after reconnecting. Silence, low levels, changing microphone defaults and
background noise need testing with physical devices.

The desktop adapter uses GlobalShortcuts and RemoteDesktop portal sessions. It
requests press/release signals and sends Unicode keysyms. Control characters are
rejected or normalized to spaces; it does not send Enter/Tab or paste via clipboard.
Portal denial, revocation, restart or enable failure does not fall back to unguarded
keyboard injection.

KDE Wayland does not expose a general active-window query. A session-only KWin
script reports window identities/activation epochs and answers focus queries to a
private D-Bus endpoint. It is loaded from a mode-0600 runtime file and removed on
disable/quit. It does not persist a KWin configuration change. Other compositors
are unsupported by this adapter. If KWin scripting is unavailable, insertion is
unavailable rather than proceeding without focus checks.

The original window and activation epoch are checked before insertion, between
characters, and with a fresh KWin query every eight characters. Switching away and
back still invalidates the target. Uncertain focus retains the transcript. There
is a compositor scheduling race between a focus check and delivering a key event;
this is not an atomic text-editor transaction. A focus change/cancellation during
insertion can leave a partial transcript, which AKS does not try to undo. The guard
tracks windows, not individual fields or cursor positions within one window.
Use a plain text editor for first desktop validation.

The shared TTS service publishes synthesis activity and a conservative expected
playback lease from generated audio duration. Capture pauses and discards partial
audio during that interval, then resumes. External applications can delay/cancel
playback independently; exact SAPI playback timing is not observable here. This
suppression needs audible desktop testing and does not cover unrelated sound.

## Tests and outstanding acceptance

- Backend endpoint tests: silence, preroll, noise bursts, bounded chunks, reset,
  backpressure, real subprocess/pipe shutdown and cancellation.
- Recognition worker: cancellation during model load and inference, then recovery.
- Controller state: worker reuse, idle unload, retained text on focus refusal,
  diagnostic capture, input ownership surviving a TTS client exit.
- Desktop: toggle and PTT transitions, Unicode, focus-away-and-back, stale focus,
  cancellation, key release after errors.
- Private D-Bus: actual request/response messages (including an early response),
  permission denial, keyboard notification signatures. Run with:

  `AKS_TEST_PORTALS=1 PYTHONPATH=standalone:backend dbus-run-session -- python -m unittest discover -s standalone/tests -p test_portal_bus.py -v`

- Real multilingual Small: two fixture recordings through the new manager reused
  the same worker PID and produced the expected English transcript offline. Cloud
  observations: 7.295 s cold, 4.889 s warm for 11 s audio, child peak 653604 KiB.
  This does not measure physical capture or the fifth-generation i5.

On 5 November 2026, a user confirmed microphone discovery, the ten-second recording
test, KDE permission setup and dictation into Kate on Kubuntu 26.04 Wayland. The
installed desktop entry launched successfully through `gtk-launch`, while the
already-running portal initially reported “App info not found”. Restarting
`xdg-desktop-portal.service` resolved registration and enabled working dictation.
This validates that desktop path on that system; it does not establish all acceptance cases.
The ready tones were enabled but inaudible and remain under investigation.

Non-Latin insertion, focus changes, push-to-talk, lock/unlock, TTS feedback,
physical-device failures and target-hardware performance remain acceptance tests. The project has no SAPI recognition engine yet; native Windows
recognition/audio adapters and application-specific proofing-language tagging are
later work.

## Application identity and selectors

The host portal connection registers `org.akousousin.Akousousin` through
`org.freedesktop.host.portal.Registry.Register` before other portal methods. A
matching desktop entry is provided at the normal XDG applications location. A
small hidden launcher descriptor is created automatically when needed; existing
custom launchers are preserved. Qt's desktop name alone does not identify the
separate dbus-next connection. This fixes the “An app id is required” setup error
without resetting settings, model caches or portal permissions. If a valid desktop
entry opens through `gtk-launch org.akousousin.Akousousin` but the portal reports
“App info not found”, refresh the running portal with
`systemctl --user restart xdg-desktop-portal.service`, then enable shortcuts again.
A portal restart closes existing portal sessions. The controller now prepares its
entry at startup, preserves an unchanged entry and retries transient lookup errors.

The microphone selector lists readable source names and an explicit System default
choice, hides speaker monitors, and preserves an unavailable explicit selection.
Refresh reruns bounded `pactl` discovery off the UI thread. The language picker is
searchable by name/code and scrollable. Automatic detection remains a choice,
while the last detected language is displayed separately; detection never silently
locks the user's language preference. Selections apply to the next recording.

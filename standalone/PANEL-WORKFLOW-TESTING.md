<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Panel workflow trial

Branch: `codex/panel-workflow`. This is a trial, not a beta release or a merge to
main. Download its AppImage directly; the normal in-app updater does not offer
trial tags. Quit the existing AKS tray before launching it. Existing models and
voices are reused. No streaming transcription or repetition filter is included.

## Page order

1. **Status & setup:** independent speech and recognition readiness, live microphone
   state, reading/stop controls and optional setup steps. No speech voice is
   required to set up dictation. A loaded recognition model is not a listening mic.
2. **Voices & languages:** language groups, searchable/filterable catalogue,
   download/licence review, import/delete, global default versus explicit language
   preference, language override, preview, speed and volume. Tabs keep browsing,
   language preferences and playback/advanced controls within this one section.
3. **Dictation:** microphone/language, live level while recording, model activation
   and import, advanced threads/idle options, ready sound, recording test and
   selectable transcripts with complete copyable timings.
4. **Connect applications:** Wine/SAPI and Speech Dispatcher install/repair/remove,
   including saved registration status and missing Wine paths.
5. **Shortcuts:** dictation and reading enablement, actual assigned bindings,
   desktop shortcut editor, toggle/push-to-talk and optional desktop action.
6. **Application:** package location/install integration, updates/channel choices,
   advanced service port, idle lifetime and explicit speech-model load/unload.
7. **About:** version/build/format, documentation, issue tracker, copyright and
   component licences, storage/log locations and copyable diagnostics.

The Next button follows the setup order without requiring optional features.
Speech/microphone state stays visible when changing pages. All forms should be
keyboard reachable and scroll at 760×480 and on the Steam Deck display.

## Model lifetime

Both idle defaults are now **0 — Never**. The former shipped defaults (speech
300 seconds; recognition 300/3600 seconds) migrate once to Never. Other custom
timeouts remain unchanged. After the new preference version is saved, any chosen
finite timeout is explicit, including those former defaults.

Load the desired speech model once using Play sample or Load speech model, and
recognition once using Load recognition model. AKS remembers those choices and
warms installed models at the next launch. Startup never downloads missing models,
opens the microphone or speaks automatically. Explicit model unload prevents
startup restoration. Quit closes owned workers while preserving the choices.
An application requesting speech can load the voice again after manual unload.

Stop speaking cancels AKS reading/preview and pending synthesis without explicitly
unloading the model. Stop dictation closes capture/cancels pending insertion while
keeping recognition ready. Playback already owned by an external application may
need that application's own Stop control. Orca's normal interruption behaviour
is unchanged.

## Touch and desktop checks

- Tray: Read selected text, Read copied text, Stop speaking, Start/Stop dictation,
  Voice, Open control panel and Quit. The active reading action becomes Stop reading.
- Start dictation from the tray while an editor is focused; do not start into the
  panel. The popup closes before capture/selection queries, and an available KDE
  observer guards against starting in a different window. Test this on real KDE:
  mocked focus tests cannot establish compositor behaviour.
- Enable and change shortcuts from the Shortcuts page. GlobalShortcuts portal v2
  can open the desktop editor. Older backends show instructions for System Settings.
  Assigned bindings should update after edits and survive quit/relaunch/reboot.
- Check ready versus listening on the status page, dictation page and tray.
  Warming recognition must not show active dictation or open a microphone stream.
- Verify voice default changes do not silently replace per-language preferences.
- Record, stop, copy timings, switch pages, test Delete/import and preview at a
  small window size. About → Copy diagnostics must omit transcripts and permission
  tokens. Nothing here claims full Orca accessibility conformance.
- Apply an AppImage update/move with a stale Wine path: it should finish with a
  visible registration warning, not fail. The original download may be retained
  when a skipped registration could still depend on it.

## CLI registration and standalone tar SAPI cold start

See [CLI-REGISTRATION.md](CLI-REGISTRATION.md). Both installed tar and AppImage
support `--wine-prefix ... --wine ... --install-only`; `--refresh-registrations`
reapplies saved active registrations. The DLL reads a per-voice Launcher registry
value pointing at that package, rather than searching default installation paths.
Re-register using the new build to clear Wine's inherited AppImage/library
environment during cold start. Test with AKS completely quit before asking Logos
to speak. The beta 10 tar does not include this cold-start fix.

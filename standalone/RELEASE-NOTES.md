# Akousousin 0.6.0b3 beta candidate

Linux selection reading adds a desktop action for a configurable global shortcut.
Highlight text to read it; repeat to stop only that reading. An explicit clipboard
action supports applications without a primary selection. Wayland uses wl-clipboard
and X11 uses xclip. Shortcut binding and application selection support need desktop
validation.

Native Linux speech through Speech Dispatcher now shares Piper and the voice
library with SAPI. Orca SSML text and progress marks, punctuation/spelling fallback,
request-specific cancellation and bounded shared synthesis are included. Installing
or removing Speech Dispatcher support restarts the user service as its final step.

SAPI starts Akousousin on demand. Idle inference unloads automatically without
requiring launcher lifecycle management. Voice, language, speed and volume defaults
are shared across interfaces.

The control panel's Updates page checks GitHub for newer versioned releases and
offers installation. Linux AppImage updates verify SHA-256 and size, preserve a
previous image, refresh saved SAPI registrations and restart the panel. Windows ZIP
and source installations link to the matching download. Updates are user initiated.

Linux targets x86-64/glibc 2.35+ and existing 64-bit Wine prefixes. Native Windows
64-bit SAPI remains supported. The reviewed LJSpeech starter voice, model card,
licence notices, checksums and corresponding sources accompany the packages.

Exact word highlighting, localized symbol names, pitch control, sound icons and
general SSML prosody remain incomplete. Whisper recognition remains separately
scoped. See COMPATIBILITY.md and TESTING.md for evidence and desktop test limits.

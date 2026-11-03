OpenSAPI 0.4 shared speech beta: one per-user configuration, system tray and public launcher interface.

Download OpenSAPI-x86_64.AppImage for Linux, or OpenSAPI-Windows-x86_64.zip for Windows. Read TESTING.md for installation, storage paths, commands and rollback. The reviewed en_US-ljspeech-medium starter voice is bundled with its model card,
licence declarations and checksum provenance. No Wine runtime or other voice
models are bundled. Existing selected voices are preserved.

The tray reports stopped/starting/running/error and offers Start/Stop, installed voices grouped by readable language names, Configure and Quit. The original waveform artwork is now also used by the configuration window.

Closing the panel leaves speech running. Quit stops Piper and exits OpenSAPI. A launcher's last released session automatically stops/exits an automatically started OpenSAPI; independent/manual instances remain. Concurrent application sessions and crashed owner processes are handled by OpenSAPI, using the version-2 command interface. Piper stays in the AppImage; persistent runtime copies are no longer made.

Linux stays x86-64/glibc 2.35+ (Ubuntu 22.04). Existing 64-bit prefixes only; native Windows system SAPI is unchanged. Model licence review/import remains explicit. Qt/PySide matching sources, existing engine/Wine/Piper/eSpeak sources, notices, checksums and testing instructions accompany the release. Language-hint investigation and full localisation remain future work.

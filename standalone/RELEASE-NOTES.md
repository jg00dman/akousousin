OpenSAPI standalone beta for existing 64-bit Wine prefixes and native 64-bit Windows.

This branch includes the earlier prototype and deployable Piper work, plus a separate SAPI engine, a transactional prefix installer, and a voice control panel. The AppImage contains the panel and Piper service; it does not include a Wine runtime or voice model weights.

Download OpenSAPI-x86_64.AppImage for Linux or OpenSAPI-Windows-x86_64.zip for Windows. Read TESTING.md before installing. Existing Wine applications must be closed first. Import your existing ONNX voice and matching JSON, or review a voice's licence in the catalogue before downloading it. Apply the voice registration to your prefix, then start the service.

Linux remains x86-64/glibc 2.35+ (Ubuntu 22.04 target). Wine 11.21 prefixes needing the generic SAPI enumeration fix receive a backed-up, prefix-local compatibility DLL; its matching Wine source is in the corresponding-sources archive. Native Windows system SAPI is not replaced. This beta supports 64-bit callers only.

The control panel provides server start/stop, speech preview, voice search and import/download, a default voice, speed/volume/noise controls, language preferences, and a manual book language. Language hints depend on what the application supplies; this does not automatically detect foreign words. Arabic/Hebrew auxiliary models are not bundled and those languages are unavailable in this beta.

CI runs the 13 deterministic integration tests, 7 failure/recovery tests, actual Piper-to-SAPI WAV generation, GUI launch, server stop/restart, and uninstall restoration separately on Wine and Windows. WAV validation establishes generated audio, not audible playback or desktop Logos compatibility. Please test Logos in a backed-up prefix.

SHA256SUMS, the original Wine patch, testing instructions and corresponding OpenSAPI/Wine/Piper/eSpeak sources accompany the downloads. This is an experimental prerelease; existing releases and main are unchanged.

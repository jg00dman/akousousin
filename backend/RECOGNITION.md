# Whisper recognition development

Status: experimental backend foundation on the `whisper` branch. This is not yet
an installable SAPI recognition engine or desktop dictation feature. Existing
release packages and the Piper service remain unchanged.

Install the development extra from the repository root:

```sh
python -m pip install './backend[recognition]'
```

Provision converted faster-whisper model assets explicitly before use. Inference
never downloads files. Put the full CTranslate2 model directory at
`$XDG_DATA_HOME/Akousousin/models/whisper/small` (default XDG data home is
`~/.local/share`). Optional Turbo assets go in sibling directory `turbo`. On
Windows the root is `%LOCALAPPDATA%/Akousousin/models/whisper`. These are complete
multilingual models, not independently installable language modules.

For example, an explicit development-time download with `huggingface_hub`:

```python
from huggingface_hub import snapshot_download
from akousousin_backend.recognition import model_root
snapshot_download('Systran/faster-whisper-small', local_dir=model_root() / 'small')
# Optional: snapshot_download('mobiuslabsgmbh/faster-whisper-large-v3-turbo',
#                            local_dir=model_root() / 'turbo')
```

Model download management, immutable revisions, integrity checks, notices, and
release packaging still need implementation before distribution.

```sh
akousousin-whisper --wav speech.wav
akousousin-whisper --wav speech.wav --language de-DE
akousousin-whisper --capture-seconds 5
```

WAV input is mono 16 kHz signed 16-bit PCM, at most 30 seconds. The Linux developer
capture adapter requires `parec` (usually `pulseaudio-utils`); it connects to the
host PulseAudio-compatible server, including PipeWire's `pipewire-pulse`. Omit
`--source` to use the default source, or pass an explicit source name. This is a
fixed-duration diagnostic capture, not the eventual toggle-listening interface.
Windows currently supports WAV input only.

Inference runs in a separate spawn process with CPU int8, two CPU threads,
one worker, VAD enabled and greedy decoding. An explicit application/user language
is normalized and locked; omitted language requests Whisper detection. Host locale
is not silently passed as a lock. Results preserve text, language, language
probability, explicit/detected source, active model and any fallback warning.
Language probability under a forced language is not independent detection evidence.
Turbo loading failure falls back to Small; if Small also fails the request fails
cleanly. Missing/corrupt assets are diagnosed by model loading, not merely folder
presence. One inference is accepted at a time; a timeout or worker death closes the
worker and the next request can restart it.

## Remaining integration

1. Recognition-side COM/SAPI engine and registration for Wine and Windows. Accept
   SAPI-provided audio streams; do not assume microphone input. Validate actual
   recognition events/results with a SAPI test client before claiming compliance.
2. Explicit model management and recognition settings in the existing panel;
   integrate worker ownership with the shared service without loading Whisper for
   TTS-only users.
3. Continuous bounded capture/endpointing, device changes, cancellation, default
   toggle and optional push-to-talk. Suspend standalone capture during AKS speech.
4. KDE Wayland global shortcuts through supported desktop interfaces, with a
   separately designed text insertion adapter and clear permission/error feedback.
5. Application-aware language tagging. Changing keyboard layout does not reliably
   set document proofing language. Broader native Linux speech framework is later.
6. Windows/AppImage dependency and licence packaging; real small/Turbo inference,
   silence/noise, multilingual, low-end CPU/RAM, microphone and SAPI validation.

Tests run without downloading models:

```sh
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
```

# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Talk to the desktop's audio server: PipeWire natively, or PulseAudio.

Every microphone recording, sound Akousousin plays itself, and microphone
list goes through here. PipeWire is used with its own tools (pw-record,
pw-play, pw-dump) when it is the running audio server; otherwise the
PulseAudio tools (parec, paplay, pactl) are used. Speech Dispatcher plays
its own audio with the output method configured for it.

Set AKOUSOUSIN_AUDIO=pipewire or AKOUSOUSIN_AUDIO=pulseaudio to override.
"""
from functools import lru_cache
import json
import os
import time
from pathlib import Path
import shutil
import subprocess

from .host import host_environment

PIPEWIRE, PULSEAUDIO = 'pipewire', 'pulseaudio'
RATE = 16000


class AudioUnavailable(RuntimeError):
    title = 'No audio system found'

    def __init__(self, purpose):
        super().__init__(f'{purpose} needs PipeWire (pw-record and pw-play, usually in pipewire-bin or '
                         'pipewire-tools) or PulseAudio (parec and paplay, in pulseaudio-utils).')


def _run(arguments, timeout=3):
    return subprocess.run(arguments, capture_output=True, text=True, timeout=timeout,
                          env=host_environment(), check=True).stdout


def _runtime_dir():
    return Path(os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}')


def _pipewire_has_audio():
    """PipeWire may run only for screen sharing next to PulseAudio; require audio nodes."""
    try:
        objects = json.loads(_run(['pw-dump'], timeout=4))
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return any(((item.get('info') or {}).get('props') or {}).get('media.class', '').startswith('Audio/')
               for item in objects if isinstance(item, dict))


@lru_cache(maxsize=1)
def server():
    """'pipewire', 'pulseaudio', or '' when neither can be used."""
    if os.name == 'nt':
        return ''
    chosen = os.environ.get('AKOUSOUSIN_AUDIO', '').lower()
    if chosen in (PIPEWIRE, PULSEAUDIO):
        return chosen
    socket = os.environ.get('PIPEWIRE_REMOTE') or str(_runtime_dir() / 'pipewire-0')
    if shutil.which('pw-record') and shutil.which('pw-dump') and Path(socket).exists() and _pipewire_has_audio():
        return PIPEWIRE
    if shutil.which('parec') or shutil.which('paplay') or shutil.which('pactl'):
        return PULSEAUDIO
    return ''


def describe():
    return {PIPEWIRE: 'PipeWire (native)', PULSEAUDIO: 'PulseAudio'}.get(server(), 'Not found')


@lru_cache(maxsize=1)
def _raw_flag():
    """pw-record writes .au to stdout since PipeWire 1.0 unless --raw is given."""
    try:
        help_text = subprocess.run(['pw-record', '--help'], capture_output=True, text=True, timeout=3,
                                   env=host_environment()).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return ['--raw'] if '--raw' in help_text else []


def _properties(stream, role=None):
    properties = {'application.name': 'Akousousin', 'application.id': 'io.github.jg00dman.Akousousin',
                  'media.name': stream}
    if role:
        properties['media.role'] = role
    return '--properties=' + json.dumps(properties)


def record_command(source=None, stream='Dictation'):
    """A command writing mono 16 kHz signed 16-bit PCM to stdout."""
    kind = server()
    if kind == PIPEWIRE:
        arguments = ['pw-record', *_raw_flag(), f'--rate={RATE}', '--channels=1', '--format=s16',
                     '--latency=20ms', _properties(stream)]
        if source:
            arguments.append('--target=' + source)
        return arguments + ['-']
    if kind == PULSEAUDIO and shutil.which('parec'):
        arguments = ['parec', '--raw', '--format=s16le', f'--rate={RATE}', '--channels=1',
                     '--latency-msec=20', '--client-name=Akousousin', '--stream-name=' + stream]
        if source:
            arguments.append('--device=' + source)
        return arguments
    raise AudioUnavailable('Recording from the microphone')


PULSE_ROLES = {'Notification': 'event', 'Accessibility': 'a11y'}


# PipeWire (WirePlumber) and PulseAudio suspend an output after 5 s without
# sound, and many outputs (HDMI and DisplayPort monitors, USB, Bluetooth) need
# a few hundred milliseconds to wake: whatever plays then is lost, such as the
# first word of a sentence or a short cue. A sound after a quiet spell starts
# with enough silence to cover the wake-up; one soon after another does not.
WAKE_AFTER = 4.0
WAKE_LEAD_IN = .5


def _last_sound():
    base = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/tmp/akousousin-{os.getuid()}')
    return base / 'Akousousin' / 'last-sound'


def lead_in():
    """Seconds of silence to put before a sound so a sleeping output is awake for its start."""
    if os.name == 'nt':
        return 0.0
    try:
        quiet = time.time() - _last_sound().stat().st_mtime
    except OSError:
        return WAKE_LEAD_IN
    return WAKE_LEAD_IN if quiet >= WAKE_AFTER else 0.0


def played(seconds):
    """Record that a sound of this length starts now; shared by every Akousousin process."""
    if os.name == 'nt':
        return
    marker = _last_sound()
    try:
        marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker.touch()
        end = time.time() + max(0.0, seconds)
        os.utime(marker, (end, end))
    except OSError:
        pass


def with_lead_in(data, seconds):
    """A 16-bit WAV with this much silence added at the start."""
    if seconds <= 0:
        return data
    import io
    import wave
    with wave.open(io.BytesIO(data), 'rb') as source:
        params = source.getparams()
        frames = source.readframes(source.getnframes())
    output = io.BytesIO()
    with wave.open(output, 'wb') as target:
        target.setparams(params)
        target.writeframes(b'\0' * (int(params.framerate * seconds) * params.nchannels * params.sampwidth) + frames)
    return output.getvalue()


def wav_seconds(data):
    import io
    import wave
    with wave.open(io.BytesIO(data), 'rb') as audio:
        return audio.getnframes() / float(audio.getframerate() or 1)


def play_command(path, stream='Akousousin', role='Accessibility'):
    """Play a WAV file. ``role`` is a PipeWire media role: Notification or Accessibility."""
    kind = server()
    if kind == PIPEWIRE and shutil.which('pw-play'):
        return ['pw-play', _properties(stream, role), str(path)]
    if shutil.which('paplay') and kind != PIPEWIRE:
        return ['paplay', '--client-name=Akousousin', '--stream-name=' + stream,
                '--property=media.role=' + PULSE_ROLES.get(role, 'a11y'), str(path)]
    player = shutil.which('pw-play') or shutil.which('paplay') or shutil.which('aplay')
    if player:
        return [player, str(path)]
    raise AudioUnavailable('Playing sound')


def _pipewire_sources():
    objects = json.loads(_run(['pw-dump'], timeout=4))
    sources, default = [], ''
    for item in objects:
        if not isinstance(item, dict):
            continue
        props = (item.get('info') or {}).get('props') or {}
        if item.get('type') == 'PipeWire:Interface:Node' and props.get('media.class') in ('Audio/Source', 'Audio/Source/Virtual'):
            name = props.get('node.name')
            if name:
                sources.append({'name': name, 'monitor': False,
                                'description': props.get('node.description') or props.get('node.nick') or name})
        elif item.get('type') == 'PipeWire:Interface:Metadata' and (item.get('props') or props).get('metadata.name') == 'default':
            for entry in item.get('metadata') or []:
                if entry.get('key') == 'default.audio.source':
                    value = entry.get('value')
                    if isinstance(value, str):
                        try:
                            value = json.loads(value)
                        except ValueError:
                            value = {'name': value}
                    default = (value or {}).get('name', '')
    return sources, default


def _pulse_sources():
    sources = json.loads(_run(['pactl', '--format=json', 'list', 'sources']))
    if not isinstance(sources, list):
        raise ValueError('Invalid source list')
    try:
        default = _run(['pactl', 'get-default-source']).strip()
    except (OSError, subprocess.SubprocessError):
        default = ''
    return sources, default


def list_sources():
    """(sources, default name). Each source has name, description and, for PulseAudio, its monitor fields."""
    kind = server()
    if kind == PIPEWIRE:
        return _pipewire_sources()
    if kind == PULSEAUDIO and shutil.which('pactl'):
        return _pulse_sources()
    raise AudioUnavailable('Listing microphones')


class PcmStream:
    """Turns recorder output into little-endian PCM.

    Some PipeWire versions write a Sun .au stream (big-endian, with a header)
    to stdout when they have no --raw option; this undoes that transparently.
    """
    def __init__(self):
        self.pending = b''
        self.checked = False
        self.swap = False
        self.odd = b''

    def feed(self, data):
        if not self.checked:
            self.pending += data
            if len(self.pending) < 24:
                return b''
            data, self.pending, self.checked = self.pending, b'', True
            if data[:4] == b'.snd':
                offset = int.from_bytes(data[4:8], 'big')
                if len(data) < offset:
                    self.pending, self.checked = data, False
                    return b''
                self.swap = True
                data = data[offset:]
        if not self.swap:
            return data
        from array import array
        data = self.odd + data
        cut = len(data) - len(data) % 2
        self.odd = data[cut:]
        samples = array('h', data[:cut])
        samples.byteswap()
        return samples.tobytes()

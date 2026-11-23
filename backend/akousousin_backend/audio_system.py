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
from pathlib import Path
import shutil
import subprocess
import sys

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
    if os.name == 'nt':
        return 'Windows audio'
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
    if os.name == 'nt':
        # Windows has no recorder tool: Akousousin records with miniaudio
        # in a child process of its own (see record_main below).
        base = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, '-m', __name__]
        return [*base, '--record-microphone', *(['--source', source] if source else [])]
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
    if os.name == 'nt':
        import miniaudio
        names = [device['name'] for device in miniaudio.Devices().get_captures()]
        return [{'name': name, 'description': name, 'monitor': False} for name in names], ''
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


def record_main(arguments=None):
    """Windows recorder: mono 16 kHz signed 16-bit PCM to stdout until stopped."""
    import argparse
    import threading
    import miniaudio
    parser = argparse.ArgumentParser()
    parser.add_argument('--record-microphone', action='store_true')
    parser.add_argument('--source', default='')
    options = parser.parse_args(arguments)
    device_id = None
    if options.source:
        for device in miniaudio.Devices().get_captures():
            if device['name'] == options.source:
                device_id = device['id']
                break
    output = sys.stdout.buffer
    stopped = threading.Event()

    def consume():
        while True:
            data = yield
            try:
                output.write(data)
                output.flush()
            except (OSError, ValueError):  # the reader went away
                stopped.set()

    device = miniaudio.CaptureDevice(input_format=miniaudio.SampleFormat.SIGNED16, nchannels=1,
                                     sample_rate=RATE, buffersize_msec=20, device_id=device_id,
                                     app_name='Akousousin')
    generator = consume()
    next(generator)
    device.start(generator)
    try:
        stopped.wait()
    finally:
        device.close()


if __name__ == '__main__':
    record_main()

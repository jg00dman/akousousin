# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Choosing PipeWire or PulseAudio, and the commands built for each."""
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

from akousousin_backend import audio_system

PW_DUMP = [
    {'id': 30, 'type': 'PipeWire:Interface:Metadata', 'props': {'metadata.name': 'default'},
     'metadata': [{'subject': 0, 'key': 'default.audio.source', 'type': 'Spa:String:JSON',
                   'value': {'name': 'alsa_input.usb-mic'}}]},
    {'id': 41, 'type': 'PipeWire:Interface:Node',
     'info': {'props': {'media.class': 'Audio/Source', 'node.name': 'alsa_input.usb-mic', 'node.description': 'USB Microphone'}}},
    {'id': 42, 'type': 'PipeWire:Interface:Node',
     'info': {'props': {'media.class': 'Audio/Sink', 'node.name': 'alsa_output.speakers', 'node.description': 'Speakers'}}},
    {'id': 43, 'type': 'PipeWire:Interface:Node',
     'info': {'props': {'media.class': 'Video/Source', 'node.name': 'v4l2_camera'}}},
]


@unittest.skipIf(os.name == 'nt', 'Linux audio servers')
class ServerTests(unittest.TestCase):
    def setUp(self):
        audio_system.server.cache_clear()
        self.addCleanup(audio_system.server.cache_clear)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.runtime = Path(folder.name)
        environment = patch.dict(os.environ, {'XDG_RUNTIME_DIR': folder.name}, clear=False)
        environment.start()
        self.addCleanup(environment.stop)
        for name in ('AKOUSOUSIN_AUDIO', 'PIPEWIRE_REMOTE'):
            os.environ.pop(name, None)

    def detect(self, tools, dump=PW_DUMP):
        with patch.object(audio_system.shutil, 'which', side_effect=lambda name: '/usr/bin/' + name if name in tools else None), \
                patch.object(audio_system, '_run', return_value=json.dumps(dump)):
            audio_system.server.cache_clear()
            return audio_system.server()

    def test_pipewire_with_audio_nodes_is_used_natively(self):
        (self.runtime / 'pipewire-0').touch()
        self.assertEqual(self.detect({'pw-record', 'pw-dump', 'parec'}), 'pipewire')

    def test_pipewire_only_for_screen_sharing_falls_back_to_pulseaudio(self):
        (self.runtime / 'pipewire-0').touch()
        video_only = [item for item in PW_DUMP if 'Audio' not in json.dumps(item)]
        self.assertEqual(self.detect({'pw-record', 'pw-dump', 'parec'}, video_only), 'pulseaudio')

    def test_no_pipewire_socket_means_pulseaudio(self):
        self.assertEqual(self.detect({'pw-record', 'pw-dump', 'parec'}), 'pulseaudio')

    def test_neither_server_reports_both_install_options(self):
        self.assertEqual(self.detect(set()), '')
        with patch.object(audio_system, 'server', return_value=''):
            with self.assertRaisesRegex(audio_system.AudioUnavailable, 'pw-record.*pulseaudio-utils'):
                audio_system.record_command()

    def test_environment_override_wins(self):
        with patch.dict(os.environ, {'AKOUSOUSIN_AUDIO': 'pulseaudio'}):
            (self.runtime / 'pipewire-0').touch()
            self.assertEqual(self.detect({'pw-record', 'pw-dump', 'parec'}), 'pulseaudio')


class CommandTests(unittest.TestCase):
    def test_pipewire_recording_is_raw_16k_mono_with_target_and_names(self):
        with patch.object(audio_system, 'server', return_value='pipewire'), \
                patch.object(audio_system, '_raw_flag', return_value=['--raw']):
            command = audio_system.record_command('alsa_input.usb-mic', 'Microphone level')
        self.assertEqual(command[:2], ['pw-record', '--raw'])
        for option in ('--rate=16000', '--channels=1', '--format=s16', '--target=alsa_input.usb-mic'):
            self.assertIn(option, command)
        properties = json.loads(next(arg for arg in command if arg.startswith('--properties='))[13:])
        self.assertEqual((properties['application.name'], properties['media.name']), ('Akousousin', 'Microphone level'))
        self.assertEqual(command[-1], '-')

    def test_pulseaudio_recording_uses_parec_device(self):
        with patch.object(audio_system, 'server', return_value='pulseaudio'), \
                patch.object(audio_system.shutil, 'which', return_value='/usr/bin/parec'):
            command = audio_system.record_command('mic')
        self.assertEqual(command[0], 'parec')
        self.assertIn('--device=mic', command)
        self.assertIn('--format=s16le', command)

    def test_playback_roles_match_each_server(self):
        which = Mock(side_effect=lambda name: '/usr/bin/' + name)
        with patch.object(audio_system.shutil, 'which', which):
            with patch.object(audio_system, 'server', return_value='pipewire'):
                command = audio_system.play_command('/tmp/a.wav', 'Dictation ready', 'Notification')
                self.assertEqual(command[0], 'pw-play')
                self.assertEqual(json.loads(command[1][13:])['media.role'], 'Notification')
            with patch.object(audio_system, 'server', return_value='pulseaudio'):
                command = audio_system.play_command('/tmp/a.wav', 'Dictation ready', 'Notification')
                self.assertEqual(command[0], 'paplay')
                self.assertIn('--property=media.role=event', command)

    def test_pipewire_sources_and_default_come_from_pw_dump(self):
        dump = json.loads(json.dumps(PW_DUMP))
        dump[0]['metadata'][0]['value'] = json.dumps({'name': 'alsa_input.usb-mic'})  # older PipeWire: a JSON string
        with patch.object(audio_system, 'server', return_value='pipewire'), \
                patch.object(audio_system, '_run', return_value=json.dumps(dump)):
            sources, default = audio_system.list_sources()
        self.assertEqual(default, 'alsa_input.usb-mic')
        self.assertEqual([(s['name'], s['description']) for s in sources], [('alsa_input.usb-mic', 'USB Microphone')])


class PcmStreamTests(unittest.TestCase):
    def test_raw_audio_passes_through(self):
        stream = audio_system.PcmStream()
        data = struct.pack('<40h', *range(40))
        self.assertEqual(stream.feed(data[:10]) + stream.feed(data[10:]), data)

    def test_au_stream_from_older_pipewire_is_converted(self):
        stream = audio_system.PcmStream()
        header = b'.snd' + struct.pack('>5I', 28, 0xFFFFFFFF, 3, 16000, 1) + b'\0' * 4
        body = struct.pack('>5h', 1, -2, 300, 32767, -32768)
        output = stream.feed(header[:6]) + stream.feed(header[6:] + body[:3]) + stream.feed(body[3:])
        self.assertEqual(struct.unpack('<5h', output), (1, -2, 300, 32767, -32768))


if __name__ == '__main__':
    unittest.main()


class WakeLeadInTests(unittest.TestCase):
    """A sleeping output must be awake before the first word or cue plays."""
    def setUp(self):
        import tempfile
        from unittest.mock import patch
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        environment = patch.dict(os.environ, {'XDG_RUNTIME_DIR': temporary.name})
        environment.start()
        self.addCleanup(environment.stop)

    @unittest.skipIf(os.name == 'nt', 'Linux audio servers')
    def test_silence_only_after_a_quiet_spell(self):
        from akousousin_backend import audio_system
        self.assertEqual(audio_system.lead_in(), audio_system.WAKE_LEAD_IN, 'nothing played yet')
        audio_system.played(2.0)
        self.assertEqual(audio_system.lead_in(), 0.0, 'output is awake while and just after we play')
        marker = audio_system._last_sound()
        old = marker.stat().st_mtime - 10
        os.utime(marker, (old, old))
        self.assertEqual(audio_system.lead_in(), audio_system.WAKE_LEAD_IN)

    def test_lead_in_prepends_silence_and_keeps_the_sound(self):
        import io
        import wave
        from akousousin_backend import audio_system
        output = io.BytesIO()
        with wave.open(output, 'wb') as audio:
            audio.setparams((1, 2, 16000, 0, 'NONE', ''))
            audio.writeframes(b'\x01\x02' * 1600)
        original = output.getvalue()
        padded = audio_system.with_lead_in(original, .5)
        self.assertAlmostEqual(audio_system.wav_seconds(padded), .6, places=3)
        with wave.open(io.BytesIO(padded), 'rb') as audio:
            frames = audio.readframes(audio.getnframes())
        self.assertEqual(frames[:16000], b'\0' * 16000)
        self.assertTrue(frames.endswith(b'\x01\x02' * 1600))
        self.assertIs(audio_system.with_lead_in(original, 0), original)

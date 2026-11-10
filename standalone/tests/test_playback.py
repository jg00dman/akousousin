# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from akousousin_app import playback


class PlaybackTests(unittest.TestCase):
    def test_failure_reports_player_exit_error_and_copyable_command(self):
        process = Mock(returncode=1)
        process.poll.return_value = 1
        def start(command, **options):
            options['stdout'].write(b'PipeWire connection refused\n')
            return process
        path = Path('/tmp/voice preview.wav')
        with patch.object(playback.shutil, 'which', return_value='/usr/bin/pw-play'), \
                patch.object(playback.subprocess, 'Popen', side_effect=start):
            with self.assertRaises(playback.PlaybackError) as raised:
                playback.play_wav(path)
        error = raised.exception
        self.assertIn('status 1', error.message)
        self.assertIn('PipeWire connection refused', error.message)
        self.assertEqual(error.command, "/usr/bin/pw-play '/tmp/voice preview.wav'")
        self.assertIn(str(path), error.details)

    def test_cancel_stops_player_without_changing_the_speech_service(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(playback.shutil, 'which', return_value='/usr/bin/pw-play'), \
                patch.object(playback.subprocess, 'Popen', return_value=process), \
                patch.object(playback.runtime, 'call') as controller:
            self.assertFalse(playback.play_wav(Path('/tmp/preview.wav'), cancelled=Mock(side_effect=[False, True])))
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=2)
        controller.assert_not_called()

    def test_missing_player_reports_the_saved_audio_location(self):
        with patch.object(playback.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, '/tmp/preview.wav'):
                playback.play_wav(Path('/tmp/preview.wav'))

    def test_player_start_failure_includes_os_error(self):
        with patch.object(playback.shutil, 'which', return_value='/usr/bin/pw-play'), \
                patch.object(playback.subprocess, 'Popen', side_effect=PermissionError('Permission denied')):
            with self.assertRaisesRegex(playback.PlaybackError, 'Permission denied'):
                playback.play_wav(Path('/tmp/preview.wav'))

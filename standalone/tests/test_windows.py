# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import threading
import unittest
from unittest import mock

from akousousin_app import playback, windows


class NativePlaybackTests(unittest.TestCase):
    def test_stream_plays_all_audio_then_drains_before_finishing(self):
        finished = threading.Event()
        pcm = bytes(range(200)) * 10  # 1000 frames of 16-bit mono
        stream = playback._stream(pcm, 2, 1000, finished)
        next(stream)
        played = bytearray()
        while not finished.is_set():
            played.extend(stream.send(128))
        self.assertEqual(bytes(played[:len(pcm)]), pcm)
        drained = len(played) - len(pcm)
        self.assertGreaterEqual(drained, int(1000 * playback.DRAIN_SECONDS) * 2)
        self.assertFalse(any(played[len(pcm):]))
        self.assertEqual(stream.send(64), bytes(128))  # silence until the device is closed


class PlatformNeutralTests(unittest.TestCase):
    @mock.patch.object(windows, 'WINDOWS', False)
    def test_helpers_do_nothing_off_windows(self):
        self.assertEqual(windows.hidden(), {})
        self.assertEqual(windows.detached(), {'start_new_session': True})
        self.assertFalse(windows.is_admin())
        self.assertIsNone(windows.taskbar_is_light())
        windows.console(['--status'])


if __name__ == '__main__':
    unittest.main()

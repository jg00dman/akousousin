# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import struct
import unittest

from akousousin_app import speech_stream as stream


def sample():
    return (stream.HEADER + stream.info({'rate': 22050, 'events': ['word']}) + stream.event(stream.SENTENCE, 0, 9)
            + stream.event(stream.WORD, 0, 5) + stream.audio(b'\x01\x00' * 3) + stream.event(stream.MARK, 6, 6, 'mɑrk')
            + stream.audio(b'\x02\x00') + stream.end(stream.COMPLETE))


class StreamTests(unittest.TestCase):
    def test_frames_round_trip_whatever_the_read_sizes(self):
        data = sample()
        for size in (1, 2, 7, len(data)):
            with self.subTest(size=size):
                reader, frames = stream.Reader(), []
                for i in range(0, len(data), size):
                    frames.extend(reader.feed(data[i:i + size]))
                self.assertEqual(frames, [('info', {'rate': 22050, 'events': ['word']}), ('event', 2, 0, 9, ''),
                                          ('event', 1, 0, 5, ''), ('audio', b'\x01\x00' * 3),
                                          ('event', 4, 6, 6, 'mɑrk'), ('audio', b'\x02\x00'), ('end', {'status': 'complete'})])
                self.assertEqual(reader.close(), {'status': 'complete'})

    def test_event_and_audio_frames_have_spiels_layout(self):
        self.assertEqual(stream.audio(b'ab'), b'\x01' + struct.pack('<I', 2) + b'ab')
        self.assertEqual(stream.event(stream.MARK, 3, 3, 'x'), b'\x02\x04' + struct.pack('<III', 3, 3, 1) + b'x')

    def test_a_stream_cut_short_is_reported(self):
        reader = stream.Reader()
        reader.feed(sample()[:-3])
        with self.assertRaises(stream.Truncated):
            reader.close()

    def test_garbage_is_refused(self):
        for data in (b'RIFF....', stream.HEADER + b'\x09', stream.HEADER + b'\x01' + struct.pack('<I', 1 << 30),
                     stream.HEADER + stream.end('complete') + stream.audio(b'')):
            with self.subTest(data=data[:12]), self.assertRaises(ValueError):
                stream.Reader().feed(data)


if __name__ == '__main__':
    unittest.main()

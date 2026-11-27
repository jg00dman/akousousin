# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The voice service's speech stream: audio with word, sentence and mark events where they are heard.

Layout (all integers little-endian):

    header   4 bytes  b'AK01'
    audio    u8 1, u32 length, PCM S16LE mono at the stream's rate
    event    u8 2, u8 kind, u32 start, u32 end, u32 name length, UTF-8 name
    info     u8 3, u32 length, JSON           (first: rate, voices, events available)
    end      u8 5, u32 length, JSON           (last: {"status": "complete"|"interrupted"|"failed"})

Audio and event frames match Spiel's ``audio/x-spiel`` framing, so they pass to
Spiel unchanged. An event comes just before the audio it describes: its place
in the stream is its timing. ``start``/``end`` are character offsets into the
input as sent. A stream that ends without an end frame was cut short.
"""
import json
import struct

HEADER = b'AK01'
AUDIO, EVENT, INFO, END = 1, 2, 3, 5
WORD, SENTENCE, RANGE, MARK = 1, 2, 3, 4
KINDS = {'word': WORD, 'sentence': SENTENCE, 'mark': MARK}
COMPLETE, INTERRUPTED, FAILED = 'complete', 'interrupted', 'failed'

LONGEST_AUDIO = 8 * 1024 * 1024
LONGEST_JSON = 64 * 1024
LONGEST_NAME = 1024

_LENGTH = struct.Struct('<I')
_EVENT = struct.Struct('<BIII')


def audio(pcm):
    return bytes([AUDIO]) + _LENGTH.pack(len(pcm)) + bytes(pcm)


def event(kind, start, end, name=''):
    encoded = name.encode('utf-8')
    return bytes([EVENT]) + _EVENT.pack(kind, start, end, len(encoded)) + encoded


def _json(frame, value):
    encoded = json.dumps(value, separators=(',', ':')).encode('utf-8')
    return bytes([frame]) + _LENGTH.pack(len(encoded)) + encoded


def info(value):
    return _json(INFO, value)


def end(status, message=''):
    return _json(END, {'status': status, 'message': message} if message else {'status': status})


class Truncated(ConnectionError):
    """The stream stopped before its end frame."""


class Reader:
    """Parses a speech stream from bytes as they arrive.

    ``feed(data)`` returns the frames completed so far, as tuples:
    ('audio', pcm), ('event', kind, start, end, name), ('info', dict), ('end', dict).
    Call ``close()`` when the connection ends: it raises Truncated unless the
    end frame arrived.
    """
    def __init__(self):
        self.buffer = bytearray()
        self.header = False
        self.ended = None

    def feed(self, data):
        self.buffer += data
        frames = []
        if not self.header:
            if len(self.buffer) < len(HEADER):
                return frames
            if bytes(self.buffer[:len(HEADER)]) != HEADER:
                raise ValueError('Not a speech stream')
            del self.buffer[:len(HEADER)]
            self.header = True
        while self.buffer:
            if self.ended is not None:
                raise ValueError('Data after the end of the stream')
            frame = self._frame()
            if frame is None:
                break
            frames.append(frame)
            if frame[0] == 'end':
                self.ended = frame[1]
        return frames

    def _frame(self):
        kind, buffer = self.buffer[0], self.buffer
        if kind == EVENT:
            if len(buffer) < 1 + _EVENT.size:
                return None
            event_kind, start, finish, length = _EVENT.unpack_from(buffer, 1)
            if length > LONGEST_NAME:
                raise ValueError('Mark name too long')
            total = 1 + _EVENT.size + length
            if len(buffer) < total:
                return None
            name = bytes(buffer[1 + _EVENT.size:total]).decode('utf-8')
            del buffer[:total]
            return ('event', event_kind, start, finish, name)
        if kind not in (AUDIO, INFO, END):
            raise ValueError(f'Unknown frame {kind}')
        if len(buffer) < 1 + _LENGTH.size:
            return None
        (length,) = _LENGTH.unpack_from(buffer, 1)
        if length > (LONGEST_AUDIO if kind == AUDIO else LONGEST_JSON):
            raise ValueError('Frame too long')
        total = 1 + _LENGTH.size + length
        if len(buffer) < total:
            return None
        payload = bytes(buffer[1 + _LENGTH.size:total])
        del buffer[:total]
        if kind == AUDIO:
            return ('audio', payload)
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError('Invalid frame')
        return ('info' if kind == INFO else 'end', value)

    def close(self):
        if self.ended is None:
            raise Truncated('The speech stream ended early')
        return self.ended

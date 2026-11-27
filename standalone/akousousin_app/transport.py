# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Bounded, cancellable HTTP for the local speech service; never uses a proxy."""
import errno
import select
import socket
import time
import urllib.error

MAX_AUDIO = 64 * 1024 * 1024


class _Exchange:
    """One HTTP/1.0 request to the loopback speech service, cancellable at every wait."""
    def __init__(self, port, path, payload, cancelled, identifier, timeout):
        self.cancelled, self.timeout = cancelled, timeout
        self.deadline = time.monotonic() + timeout
        self.connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.connection.setblocking(False)
            # A cancellation that can be waited on (see waiting.Interrupt) wakes this
            # at once; a plain event is checked every 50 ms instead.
            self.wakers = cancelled.descriptors() if hasattr(cancelled, 'descriptors') else None
            code = self.connection.connect_ex(('127.0.0.1', port))
            if code not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):
                raise OSError(code, 'Speech connection failed')
            self.ready(True, time.monotonic() + 3)
            request = (f'POST {path} HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n'
                       f'Content-Type: application/json\r\nContent-Length: {len(payload)}\r\n'
                       f'X-Akousousin-Request: {identifier}\r\nConnection: close\r\n\r\n').encode() + payload
            view = memoryview(request)
            sending = time.monotonic() + 5
            while view:
                self.ready(True, sending)
                try:
                    count = self.connection.send(view)
                except BlockingIOError:
                    continue
                if not count:
                    raise ConnectionError('Speech connection closed')
                view = view[count:]
        except BaseException:
            self.connection.close()
            raise

    def close(self):
        self.connection.close()

    def ready(self, write=False, end=None):
        connection = self.connection
        end = self.deadline if end is None else min(self.deadline, end)
        while True:
            if self.cancelled.is_set():
                raise InterruptedError('Speech cancelled')
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Speech response timed out')
            if self.wakers is None:
                reads, writes, errors = select.select([] if write else [connection],
                    [connection] if write else [], [connection], .05)
                if errors:
                    raise ConnectionError('Speech connection failed')
                happened = bool(reads or writes)
            else:
                poller = select.poll()
                poller.register(connection, select.POLLOUT if write else select.POLLIN)
                for descriptor, mask in self.wakers:
                    poller.register(descriptor, mask)
                flags = dict(poller.poll(remaining * 1000)).get(connection.fileno(), 0)
                if flags & select.POLLNVAL:
                    raise ConnectionError('Speech connection failed')
                happened = bool(flags)
            if happened:
                error = connection.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if error:
                    raise OSError(error, 'Speech connection failed')
                return

    def receive(self, size):
        """Up to ``size`` bytes, or b'' when the service closes the connection."""
        while True:
            self.ready()
            try:
                return self.connection.recv(size)
            except BlockingIOError:
                continue

    def headers(self):
        """The response's header lines, raising HTTPError unless it is 200; and the body bytes already read."""
        data = bytearray()
        while b'\r\n\r\n' not in data:
            chunk = self.receive(4096)
            if not chunk:
                raise ConnectionError('Speech response ended before headers')
            data.extend(chunk)
            if len(data) > 16384 and b'\r\n\r\n' not in data[:16384]:
                raise ValueError('Speech response headers too large')
        header, body = data.split(b'\r\n\r\n', 1)
        lines = header.decode('ascii').split('\r\n')
        status = lines.pop(0).split(' ', 2)
        if len(status) < 2 or status[0] not in ('HTTP/1.0', 'HTTP/1.1'):
            raise ValueError('Invalid HTTP response')
        if status[1] != '200':
            raise urllib.error.HTTPError('loopback speech', int(status[1]), 'Speech request failed', {}, None)
        for line in lines:
            if line.split(':', 1)[0].lower() == 'transfer-encoding':
                raise ValueError('Unexpected transfer encoding')
        return lines, body


def fetch(port, payload, cancelled, identifier, timeout=65):
    """A whole WAV from /synthesize."""
    exchange = _Exchange(port, '/synthesize', payload, cancelled, identifier, timeout)
    try:
        lines, body = exchange.headers()
        lengths = []
        for line in lines:
            name, value = line.split(':', 1)
            if name.lower() == 'content-length':
                if not value.strip().isdigit():
                    raise ValueError('Invalid audio size')
                lengths.append(int(value))
        if len(lengths) != 1 or not 0 < lengths[0] <= MAX_AUDIO:
            raise ValueError('Missing or excessive audio size')
        length = lengths[0]
        if len(body) > length:
            raise ValueError('Unexpected response data')
        while len(body) < length:
            chunk = exchange.receive(min(65536, length - len(body)))
            if not chunk:
                raise ConnectionError('Truncated audio response')
            body.extend(chunk)
        return bytes(body)
    finally:
        exchange.close()


def speak(port, request, cancelled, identifier, silence=65):
    """Speech from /speak as frames, as they arrive (see speech_stream).

    Yields ('info', dict), ('audio', pcm) and ('event', kind, start, end, name),
    and returns the end frame's dict. A stream can run for minutes; it only
    times out if nothing arrives for ``silence`` seconds. Raises
    speech_stream.Truncated if the service stops without an end frame.
    """
    import json
    from . import speech_stream
    exchange = _Exchange(port, '/speak', json.dumps(request).encode(), cancelled, identifier, silence)
    try:
        _, body = exchange.headers()
        reader = speech_stream.Reader()
        data = bytes(body)
        while True:
            for frame in reader.feed(data):
                if frame[0] == 'end':
                    return frame[1]
                yield frame
            exchange.deadline = time.monotonic() + silence
            data = exchange.receive(65536)
            if not data:
                return reader.close()
    finally:
        exchange.close()

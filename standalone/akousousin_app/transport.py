# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Bounded, cancellable HTTP for the local speech service; never uses a proxy."""
import errno
import select
import socket
import time
import urllib.error

MAX_AUDIO = 64 * 1024 * 1024


def fetch(port, payload, cancelled, identifier, timeout=65):
    deadline = time.monotonic() + timeout
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.setblocking(False)
        def ready(write=False, end=deadline):
            while True:
                if cancelled.is_set():
                    raise InterruptedError('Speech cancelled')
                if time.monotonic() >= min(deadline, end):
                    raise TimeoutError('Speech response timed out')
                reads, writes, errors = select.select([] if write else [connection],
                    [connection] if write else [], [connection], .05)
                if errors:
                    raise ConnectionError('Speech connection failed')
                if reads or writes:
                    error = connection.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                    if error:
                        raise OSError(error, 'Speech connection failed')
                    return
        code = connection.connect_ex(('127.0.0.1', port))
        if code not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):
            raise OSError(code, 'Speech connection failed')
        ready(True, time.monotonic() + 3)
        request = (f'POST /synthesize HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n'
                   f'Content-Type: application/json\r\nContent-Length: {len(payload)}\r\n'
                   f'X-Akousousin-Request: {identifier}\r\nConnection: close\r\n\r\n').encode() + payload
        view = memoryview(request)
        sending = time.monotonic() + 5
        while view:
            ready(True, sending)
            try:
                count = connection.send(view)
            except BlockingIOError:
                continue
            if not count:
                raise ConnectionError('Speech connection closed')
            view = view[count:]
        data = bytearray()
        while b'\r\n\r\n' not in data:
            ready()
            try:
                chunk = connection.recv(4096)
            except BlockingIOError:
                continue
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
        lengths = []
        for line in lines:
            name, value = line.split(':', 1)
            if name.lower() == 'transfer-encoding':
                raise ValueError('Unexpected transfer encoding')
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
            ready()
            try:
                chunk = connection.recv(min(65536, length - len(body)))
            except BlockingIOError:
                continue
            if not chunk:
                raise ConnectionError('Truncated audio response')
            body.extend(chunk)
        return bytes(body)

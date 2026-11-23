# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Waiting to be told: file changes (Linux inotify) and interruptions a thread can wait on.

Akousousin's helpers sleep until something happens rather than waking
repeatedly to check, so an idle desktop stays idle.
"""
import ctypes
import os
import struct
import select
import sys
import threading

_IN_MODIFY, _IN_ATTRIB, _IN_CLOSE_WRITE = 0x2, 0x4, 0x8
_IN_MOVED_FROM, _IN_MOVED_TO, _IN_CREATE, _IN_DELETE = 0x40, 0x80, 0x100, 0x200
_IN_DELETE_SELF, _IN_MOVE_SELF, _IN_Q_OVERFLOW = 0x400, 0x800, 0x4000
_EVENT = struct.Struct('iIII')
CHANGES = (_IN_MODIFY | _IN_ATTRIB | _IN_CLOSE_WRITE | _IN_MOVED_FROM | _IN_MOVED_TO | _IN_CREATE
           | _IN_DELETE | _IN_DELETE_SELF | _IN_MOVE_SELF)


class Watch:
    """A descriptor that becomes readable when anything in the given folders changes.

    With ``names``, drain() reports only changes to files of those names (and
    the folders themselves going away). Raises OSError where the system cannot
    watch files (outside Linux) or none of the folders exist.
    """
    def __init__(self, *folders, names=None):
        self.names = {os.fsencode(name) for name in names} if names else None
        if not sys.platform.startswith('linux'):
            raise OSError('File watching needs Linux')
        libc = ctypes.CDLL(None, use_errno=True)
        self.fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), 'Could not watch files')
        watched = 0
        for folder in folders:
            if folder and libc.inotify_add_watch(self.fd, os.fsencode(str(folder)), CHANGES) >= 0:
                watched += 1
        if not watched:
            self.close()
            raise OSError('Nothing to watch')

    def fileno(self):
        return self.fd

    def drain(self):
        """Whether anything that matters changed since the last call; never blocks."""
        changed = False
        while self.fd is not None:
            try:
                data = os.read(self.fd, 65536)
            except BlockingIOError:
                break
            if not data:
                break
            if self.names is None:
                changed = True
                continue
            offset = 0
            while offset + _EVENT.size <= len(data):
                _watch, mask, _cookie, length = _EVENT.unpack_from(data, offset)
                name = data[offset + _EVENT.size:offset + _EVENT.size + length].rstrip(b'\0')
                offset += _EVENT.size + length
                if name in self.names or mask & (_IN_DELETE_SELF | _IN_MOVE_SELF | _IN_Q_OVERFLOW):
                    changed = True
        return changed

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __del__(self):
        self.close()


class Interrupt(threading.Event):
    """A threading.Event whose setting also makes a descriptor readable.

    A thread can wait for it together with sockets, pipes and file watches.
    """
    def __init__(self):
        super().__init__()
        self._read, self._write = os.pipe()
        os.set_blocking(self._read, False)
        os.set_blocking(self._write, False)

    def set(self):
        super().set()
        try:
            os.write(self._write, b'\0')
        except (BlockingIOError, OSError, TypeError):
            pass  # already readable, or closed

    def fileno(self):
        return self._read

    def descriptors(self):
        """What a waiter should watch, as (descriptor, poll events) pairs."""
        return [(self._read, select.POLLIN)]

    def close(self):
        for name in ('_read', '_write'):
            descriptor = getattr(self, name, None)
            if descriptor is not None:
                setattr(self, name, None)
                os.close(descriptor)

    def __del__(self):
        self.close()

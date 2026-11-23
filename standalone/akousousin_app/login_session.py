# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Which desktop login session Akousousin belongs to, and whether it has ended.

The controller must not outlive the desktop it serves. Under Plasma, Qt is
told to survive a compositor restart, so at logout the controller would carry
on with no screen, and the next login would hand over to it: no tray icon,
shortcuts bound to the ended session. Watching the login session itself is
reliable on X11 and Wayland alike.

This uses systemd's public sd-login C API (libsystemd, or elogind's
libelogind) through ctypes. Without either, sessions are unknown and nothing
is watched.
"""
import ctypes
import ctypes.util
import os

_library = None


def _sd():
    global _library
    if _library is None:
        _library = False
        if os.name == 'posix':
            for name in ('systemd', 'elogind'):
                path = ctypes.util.find_library(name) or 'lib%s.so.0' % name
                try:
                    library = ctypes.CDLL(path)
                    for function in ('sd_session_get_state', 'sd_uid_get_display', 'sd_pid_get_session'):
                        getattr(library, function).restype = ctypes.c_int
                    _library = library
                    break
                except (OSError, AttributeError):
                    continue
    return _library or None


def _string(call, *arguments):
    """Call an sd-login function that returns a malloc'd string; None on failure."""
    library = _sd()
    if library is None:
        return None
    value = ctypes.c_char_p()
    if getattr(library, call)(*arguments, ctypes.byref(value)) < 0 or not value.value:
        return None
    try:
        return value.value.decode()
    finally:
        libc = ctypes.CDLL(None)
        libc.free(ctypes.cast(value, ctypes.c_void_p))


def state(session):
    """'online', 'active' or 'closing'; None once the session is gone."""
    return _string('sd_session_get_state', session.encode()) if session else None


def running(session):
    return state(session) in ('online', 'active')


def current():
    """The session of this desktop: ours if we are in one, else the user's graphical one."""
    candidates = (os.environ.get('XDG_SESSION_ID'),
                  _string('sd_pid_get_session', ctypes.c_int(0)),
                  _string('sd_uid_get_display', ctypes.c_uint(os.getuid())) if os.name == 'posix' else None)
    for session in candidates:
        if session and running(session):
            return session
    return None


class Monitor:
    """A descriptor that becomes readable when any login session starts, changes or ends.

    Lets the controller wait to be told about logout instead of asking
    repeatedly. Raises OSError where sd-login cannot provide one.
    """
    def __init__(self):
        library = _sd()
        if library is None:
            raise OSError('sd-login is unavailable')
        for function, result in (('sd_login_monitor_new', ctypes.c_int), ('sd_login_monitor_get_fd', ctypes.c_int),
                                 ('sd_login_monitor_flush', ctypes.c_int), ('sd_login_monitor_unref', ctypes.c_void_p)):
            getattr(library, function).restype = result
        for function in ('sd_login_monitor_get_fd', 'sd_login_monitor_flush', 'sd_login_monitor_unref'):
            getattr(library, function).argtypes = [ctypes.c_void_p]
        self._library = library
        self._handle = ctypes.c_void_p()
        if library.sd_login_monitor_new(b'session', ctypes.byref(self._handle)) < 0:
            raise OSError('Could not watch login sessions')
        self.fd = library.sd_login_monitor_get_fd(self._handle)
        if self.fd < 0:
            self.close()
            raise OSError('Could not watch login sessions')

    def flush(self):
        """Acknowledge the pending changes, so the descriptor waits for the next ones."""
        if self._handle:
            self._library.sd_login_monitor_flush(self._handle)

    def close(self):
        if self._handle:
            self._library.sd_login_monitor_unref(self._handle)
            self._handle = None

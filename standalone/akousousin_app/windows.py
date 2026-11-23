# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Native Windows helpers: no console windows, administrator steps, taskbar theme.

Every function is safe to call on Linux, where it does nothing or returns the
neutral answer, so callers need no platform checks of their own.
"""
import os
import subprocess
import sys

WINDOWS = os.name == 'nt'
# Launches that belong to another program (a SAPI client, login, the
# controller) must never print into whatever console started them.
QUIET_FLAGS = ('--api-start', '--acquire-session', '--release-session', '--background',
               '--controller', '--serve', '--panel', '--configure', '--speech-dispatcher')


def hidden():
    """subprocess options that keep a console program from opening a window.

    The Windows build is a GUI program, so console helpers it starts
    (reg.exe, regedit.exe, taskkill.exe, the SAPI probes) would each flash a
    console window without this.
    """
    if not WINDOWS:
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 0  # SW_HIDE
    return {'creationflags': subprocess.CREATE_NO_WINDOW, 'startupinfo': info}


def detached():
    """Options for a long-running Akousousin child (controller, voice service)."""
    if not WINDOWS:
        return {'start_new_session': True}
    return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}


def console(arguments=None):
    """Give command-line use somewhere to write.

    The packaged akousousin.exe has no console of its own. When it is run from
    a terminal, write to that terminal; otherwise discard output rather than
    fail. Output redirected by the caller (pipes, files) is left alone.
    """
    if not WINDOWS:
        return
    arguments = sys.argv[1:] if arguments is None else arguments
    missing = [name for name in ('stdin', 'stdout', 'stderr') if getattr(sys, name) is None]
    if not missing:
        return
    attached = False
    if not any(flag in arguments for flag in QUIET_FLAGS):
        import ctypes
        attached = bool(ctypes.windll.kernel32.AttachConsole(-1))  # ATTACH_PARENT_PROCESS
    for name in missing:
        if attached:
            device = 'CONIN$' if name == 'stdin' else 'CONOUT$'
            stream = open(device, 'r' if name == 'stdin' else 'w', encoding='utf-8', errors='replace')
        else:
            stream = open(os.devnull, 'r' if name == 'stdin' else 'w', encoding='utf-8')
        setattr(sys, name, stream)


def is_admin():
    if not WINDOWS:
        return False
    import ctypes
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


class Cancelled(PermissionError):
    pass


def run_elevated(arguments, timeout=300):
    """Run Akousousin with administrator rights (one UAC prompt) and wait.

    Returns the exit code. Raises Cancelled when the person declines.
    """
    import ctypes
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('fMask', wintypes.ULONG), ('hwnd', wintypes.HWND),
                    ('lpVerb', wintypes.LPCWSTR), ('lpFile', wintypes.LPCWSTR),
                    ('lpParameters', wintypes.LPCWSTR), ('lpDirectory', wintypes.LPCWSTR),
                    ('nShow', ctypes.c_int), ('hInstApp', wintypes.HINSTANCE), ('lpIDList', ctypes.c_void_p),
                    ('lpClass', wintypes.LPCWSTR), ('hkeyClass', wintypes.HKEY), ('dwHotKey', wintypes.DWORD),
                    ('hIconOrMonitor', wintypes.HANDLE), ('hProcess', wintypes.HANDLE)]

    executable, *rest = arguments
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040 | 0x00008000  # SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE
    info.lpVerb = 'runas'
    info.lpFile = executable
    info.lpParameters = subprocess.list2cmdline(rest)
    info.nShow = 0  # SW_HIDE
    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == 1223:  # ERROR_CANCELLED
            raise Cancelled('Administrator permission was not given.')
        raise ctypes.WinError(error)
    try:
        if kernel32.WaitForSingleObject(info.hProcess, int(timeout * 1000)) != 0:
            raise TimeoutError('The administrator step did not finish in time.')
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
        return code.value
    finally:
        kernel32.CloseHandle(info.hProcess)


def taskbar_is_light():
    """Whether the Windows taskbar uses the light theme (it is dark by default)."""
    if not WINDOWS:
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
            return bool(winreg.QueryValueEx(key, 'SystemUsesLightTheme')[0])
    except OSError:
        return False

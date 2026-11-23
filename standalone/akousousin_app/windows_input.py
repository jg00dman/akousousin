# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Windows desktop dictation: the same interface as desktop_input.Desktop.

A global hotkey (RegisterHotKey) starts and stops dictation, and the text is
typed into the window that was active with SendInput Unicode key events.
Typing stops if that window loses focus. Loaded only on enable, Windows only.
"""
import ctypes
from ctypes import wintypes
import threading
import time

from .desktop_input import keysyms

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x1, 0x2, 0x4000
VK_SPACE, VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN = 0x20, 0x10, 0x11, 0x12, 0x5B, 0x5C
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
EVENT_SYSTEM_FOREGROUND, WINEVENT_OUTOFCONTEXT = 3, 0
INPUT_KEYBOARD, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 1, 0x2, 0x4
SHORTCUT = 'Ctrl+Alt+Space'
HOTKEY_ID = 0xA45


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):  # only to give INPUT its full size
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT)]
    _anonymous_ = ('u',)
    _fields_ = [('type', wintypes.DWORD), ('u', _U)]


WINEVENTPROC = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
                                  wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SetWinEventHook.restype = wintypes.HANDLE
user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, WINEVENTPROC,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

# The taskbar and tray overflow take focus when the tray icon is clicked.
SHELL_CLASSES = {'Shell_TrayWnd', 'Shell_SecondaryTrayWnd', 'NotifyIconOverflowWindow', 'TopLevelWindowForOverflowXamlIsland'}


def held(key):
    return bool(user32.GetAsyncKeyState(key) & 0x8000)


def foreground():
    return user32.GetForegroundWindow() or 0


def typeable(window):
    """A window the user could be typing in: not ours and not the taskbar."""
    if not window:
        return False
    process = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(process))
    if process.value == kernel32.GetCurrentProcessId():
        return False
    name = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(window, name, 64)
    return name.value not in SHELL_CLASSES


def units(text):
    """UTF-16 code units, the way SendInput types Unicode (surrogate pairs for emoji)."""
    for symbol in keysyms(text):  # same rules as Linux: no Enter/Tab/control characters
        code = symbol & 0xFFFFFF if symbol > 0xFFFFFF else symbol
        data = chr(code).encode('utf-16-le')
        yield from (int.from_bytes(data[i:i + 2], 'little') for i in range(0, len(data), 2))


class Desktop:
    def __init__(self, dictation, config, preferences=None):
        self.dictation, self.config, self.preferences = dictation, config, preferences
        self.status = 'Starting desktop integration…'
        self.enabled = False
        self.start_requested = False
        self.shortcut_down = False
        self.shortcut_description = ''
        self.last_window = 0
        self.thread = None
        self.thread_id = None
        self.ready = threading.Event()

    def start(self, listen=False):
        self.start_requested = listen
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.ready.wait(5)

    def _run(self):
        self.thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_SPACE):
            self.status = SHORTCUT + ' is already used by another program'
            self.ready.set()
            return

        def changed(_hook, _event, window, *_rest):
            if typeable(window):
                self.last_window = window
        self._callback = WINEVENTPROC(changed)  # keep a reference while hooked
        hook = user32.SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, self._callback,
                                      0, 0, WINEVENT_OUTOFCONTEXT)
        if typeable(foreground()):
            self.last_window = foreground()
        self.enabled = True
        self.shortcut_description = SHORTCUT
        self.status = 'Desktop dictation enabled — ' + SHORTCUT
        if self.preferences:
            self.preferences.update(dictation_enabled=True)
        self.ready.set()
        if self.start_requested:
            self.start_requested = False
            self.trigger()
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID and not self.shortcut_down:
                    self.shortcut_down = True
                    threading.Thread(target=self._shortcut, daemon=True).start()
        finally:
            self.enabled = False
            if hook:
                user32.UnhookWinEvent(hook)
            user32.UnregisterHotKey(None, HOTKEY_ID)

    def _shortcut(self):
        """Pressed: start (or, in toggle mode, stop). Released: stop when holding to talk."""
        try:
            mode = self.config().get('stt_mode', 'toggle')
            if self.dictation.status()['busy']:
                if mode == 'toggle':
                    self.dictation.finish(cancel_insertion=True)
            else:
                window = foreground()
                if not typeable(window):
                    raise RuntimeError('Click into the app you want to type in first')
                self.dictation.start(target=window)
            while held(VK_SPACE):
                time.sleep(.02)
            if mode == 'push-to-talk':
                self.dictation.finish()
        except Exception as error:
            self.status = str(error)
        finally:
            self.shortcut_down = False

    def trigger(self):
        """From the tray or the panel: dictate into the window used last."""
        try:
            if self.dictation.status()['busy']:
                self.dictation.finish(cancel_insertion=True)
                return
            window = self.last_window
            if not window or not user32.IsWindow(window):
                raise RuntimeError('Click into the app you want to type in first')
            user32.SetForegroundWindow(window)  # the tray click moved focus to the taskbar
            self.dictation.start(target=window)
        except Exception as error:
            self.status = str(error)

    def insert(self, text, target, cancelled):
        if not self.enabled:
            raise RuntimeError('Desktop dictation is disabled')
        deadline = time.monotonic() + 3
        # Typing while Ctrl/Alt are still down would press shortcuts in the app.
        while self.shortcut_down or any(held(key) for key in (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN)):
            if cancelled.is_set() or time.monotonic() >= deadline:
                raise InterruptedError('Shortcut is still held or dictation was cancelled')
            time.sleep(.03)
        delivery = {}
        for unit in units(text):
            if cancelled.is_set():
                raise InterruptedError('Text insertion cancelled')
            if foreground() != target:
                raise RuntimeError('Active window changed')
            events = (INPUT * 2)()
            for event, flags in zip(events, (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)):
                event.type = INPUT_KEYBOARD
                event.ki = KEYBDINPUT(0, unit, flags, 0, 0)
            if user32.SendInput(2, events, ctypes.sizeof(INPUT)) != 2:
                raise RuntimeError('Windows blocked typing into this app (it may be running as administrator)')
            now = time.monotonic()
            delivery.setdefault('first_key_at', now)
            delivery['last_key_at'] = now
        return delivery

    def close(self):
        self.start_requested = False
        self.enabled = False
        self.dictation.cancel()
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        if self.thread:
            self.thread.join(5)

# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from akousousin_app import selection


class SelectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / 'settings.json'

    def test_wayland_primary_and_explicit_clipboard_do_not_fall_back(self):
        def read(command, **kwargs):
            kwargs['stdout'].write('Selected café'.encode())
            return subprocess.CompletedProcess(command, 0)
        with patch.dict(os.environ, {'WAYLAND_DISPLAY': 'wayland-0'}), \
                patch.object(selection.shutil, 'which', return_value='/usr/bin/wl-paste'), \
                patch.object(selection.subprocess, 'run', side_effect=read) as run:
            self.assertEqual(selection.selected_text(), 'Selected café')
            self.assertIn('--primary', run.call_args.args[0])
            selection.selected_text(clipboard=True)
            self.assertNotIn('--primary', run.call_args.args[0])
            run.side_effect = lambda *args, **kwargs: subprocess.CompletedProcess(args, 1)
            with self.assertRaisesRegex(RuntimeError, 'No text'):
                selection.selected_text()
            self.assertEqual(run.call_count, 3)

    def test_chunks_preserve_unicode_and_protocol_data_cannot_escape_message(self):
        text = 'Unicode café 😀. ' * 300
        self.assertEqual(''.join(selection.text_parts(text)), text)
        self.assertTrue(all(len(part) <= 800 for part in selection.text_parts(text)))
        self.assertEqual(selection.encode_text('.\nCANCEL ALL\n..end'), '..\r\nCANCEL ALL\r\n...end\r\n.')

    def test_repeat_toggle_stops_only_its_worker_and_can_start_again(self):
        started = threading.Event()
        stopped = threading.Event()
        def speak(text, cancelled, path):
            started.set()
            if not cancelled.wait(3):
                raise AssertionError('Stop did not reach reader')
            stopped.set()
        errors = []
        def first():
            try:
                selection.toggle(self.path, reader=lambda copied: 'hello', speaker=speak)
            except Exception as error:
                errors.append(error)
        with patch.dict(os.environ, {'XDG_RUNTIME_DIR': str(self.root)}):
            worker = threading.Thread(target=first)
            worker.start()
            self.assertTrue(started.wait(1))
            self.assertEqual(selection.toggle(self.path), 'Stopped reading.')
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertTrue(stopped.is_set())
            self.assertEqual(errors, [])
            self.assertEqual(selection.toggle(self.path, reader=lambda copied: 'next', speaker=lambda *args: None),
                             'Reading finished.')

    def test_ssip_wait_interrupted_sends_cancel_self_and_never_all(self):
        first, second = socket.socketpair()
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        cancelled = threading.Event()
        commands = []
        def server():
            stream = second.makefile('rb')
            try:
                while line := stream.readline():
                    commands.append(line)
                    if line == b'SPEAK\r\n':
                        second.sendall(b'230 OK RECEIVING DATA\r\n')
                        data = []
                        while (line := stream.readline()) != b'.\r\n':
                            data.append(line)
                        self.assertEqual(data, [b'hello\r\n'])
                        second.sendall(b'225-1\r\n225 OK QUEUED\r\n')
                        cancelled.set()
                    else:
                        second.sendall(b'200 OK\r\n')
                    if commands[-1] == b'CANCEL SELF\r\n':
                        break
            finally:
                stream.close()
        worker = threading.Thread(target=server)
        worker.start()
        with self.assertRaises(InterruptedError):
            selection.SpeechClient(first).read('hello', cancelled)
        worker.join(2)
        self.assertIn(b'CANCEL SELF\r\n', commands)
        self.assertFalse(any(b'ALL' in command for command in commands))

    def test_action_keeps_paths_quoted_and_contains_clipboard_variant(self):
        with patch.dict(os.environ, {'XDG_DATA_HOME': str(self.root)}), \
                patch.object(selection.runtime, 'command', side_effect=lambda *args: ['/an image.AppImage', *args]):
            target = selection.install_action(self.path)
        text = target.read_text()
        self.assertIn('"/an image.AppImage" "--read-selection"', text)
        self.assertIn('Exec="/usr/bin/env" "APPIMAGE_EXTRACT_AND_RUN=1"', text)
        self.assertIn('"--read-clipboard"', text)
        self.assertIn('StartupNotify=false', text)
        self.assertNotIn('Ctrl+C', text)


    def test_host_tools_use_host_libraries_and_qt_plugins(self):
        with patch.dict(os.environ, {'LD_LIBRARY_PATH': '/bundled/lib', 'LD_LIBRARY_PATH_ORIG': '/host/lib',
                                     'LD_PRELOAD': '/bundled/libcrypto.so.3',
                                     'QT_PLUGIN_PATH': '/bundled/qt', 'QT_QPA_PLATFORM_PLUGIN_PATH': '/bundled/platforms'}):
            env = selection.host_environment()
        for name in ('LD_LIBRARY_PATH', 'LD_LIBRARY_PATH_ORIG', 'LD_PRELOAD'):
            self.assertNotIn(name, env)
        self.assertNotIn('QT_PLUGIN_PATH', env)
        self.assertNotIn('QT_QPA_PLATFORM_PLUGIN_PATH', env)

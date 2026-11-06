# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from akousousin_app.desktop_identity import APP_ID, MARKER, desktop_exec, ensure_desktop_entry


class IdentityTests(unittest.TestCase):
    def test_identity_is_installed_without_touching_settings_or_models(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            models = root / 'Akousousin/models/whisper/small'; models.mkdir(parents=True)
            (models / 'model.bin').write_bytes(b'keep')
            entry = ensure_desktop_entry(['/opt/AKS trial.AppImage', '--configure'], root)
            self.assertEqual(entry, root / 'applications' / (APP_ID + '.desktop'))
            self.assertIn('Name=Akousousin', entry.read_text())
            self.assertIn('Exec="/opt/AKS trial.AppImage" "--configure"', entry.read_text())
            self.assertIn(MARKER, entry.read_text())
            self.assertEqual((models / 'model.bin').read_bytes(), b'keep')

    def test_upgrade_refreshes_only_an_owned_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            entry = ensure_desktop_entry(['/old.AppImage'], folder)
            ensure_desktop_entry(['/new.AppImage'], folder)
            self.assertIn('/new.AppImage', entry.read_text())
            custom = '[Desktop Entry]\nName=Custom AKS\nExec=/custom\nType=Application\n'
            entry.write_text(custom)
            ensure_desktop_entry(['/another.AppImage'], folder)
            self.assertEqual(entry.read_text(), custom)

    def test_control_characters_in_command_are_rejected(self):
        with self.assertRaises(ValueError):
            desktop_exec(['/tmp/bad\ncommand'])

    @unittest.skipUnless(os.name != 'nt' and shutil.which('gio'), 'Requires gio desktop-entry launcher')
    def test_gio_exec_roundtrip_with_spaces_quotes_and_percent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = root / 'argv.json'
            script = root / 'launcher "quoted" $literal% file.py'
            script.write_text('import json,sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))\n')
            arguments = ['text with spaces', 'quote"slash\\percent%and$dollar`']
            entry = ensure_desktop_entry([sys.executable, str(script), str(result), *arguments], root)
            run = subprocess.run(['gio', 'launch', str(entry)], capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)
            deadline = time.monotonic() + 3
            while not result.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            import json
            self.assertEqual(json.loads(result.read_text()), arguments)


    def test_unchanged_entry_keeps_inode_and_mtime(self):
        with tempfile.TemporaryDirectory() as folder:
            entry = ensure_desktop_entry([sys.executable, '--version'], folder)
            before = entry.stat()
            ensure_desktop_entry([sys.executable, '--version'], folder)
            after = entry.stat()
            self.assertEqual((after.st_ino, after.st_mtime_ns), (before.st_ino, before.st_mtime_ns))

    def test_removed_or_nonexecutable_running_image_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / 'trial.AppImage'
            with patch.dict(os.environ, {'APPIMAGE': str(image)}):
                with self.assertRaisesRegex(RuntimeError, 'moved or been removed'):
                    ensure_desktop_entry(data_home=folder)
                image.write_text('download'); image.chmod(0o644)
                with self.assertRaisesRegex(RuntimeError, 'not executable'):
                    ensure_desktop_entry(data_home=folder)

    @unittest.skipUnless(os.name != 'nt', 'Requires Linux GIO')
    def test_host_gio_finds_installed_identity_by_id(self):
        with tempfile.TemporaryDirectory() as folder:
            ensure_desktop_entry([sys.executable, '--version'], folder)
            code = """import ctypes
lib=ctypes.CDLL('libgio-2.0.so.0')
lookup=lib.g_desktop_app_info_new
lookup.argtypes=[ctypes.c_char_p]; lookup.restype=ctypes.c_void_p
assert lookup(b'org.akousousin.Akousousin.desktop'), 'Host GIO cannot resolve AKS identity'
"""
            environment = dict(os.environ, XDG_DATA_HOME=folder)
            environment.pop('LD_LIBRARY_PATH', None)
            result = subprocess.run([sys.executable, '-c', code], env=environment,
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)

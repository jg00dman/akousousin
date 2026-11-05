import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

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

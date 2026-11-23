# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import os
from pathlib import Path
import select
import sys
import tempfile
import threading
import unittest

from akousousin_app.waiting import Interrupt, Watch


@unittest.skipUnless(sys.platform.startswith('linux'), 'inotify is Linux only')
class WatchTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def readable(self, watch, seconds=1):
        return bool(select.select([watch], [], [], seconds)[0])

    def test_a_replaced_file_is_reported(self):
        watch = Watch(self.folder)
        self.addCleanup(watch.close)
        self.assertFalse(self.readable(watch, .05))
        (self.folder / 'settings.json.tmp').write_text('{}')
        os.replace(self.folder / 'settings.json.tmp', self.folder / 'settings.json')
        self.assertTrue(self.readable(watch))
        self.assertTrue(watch.drain())
        self.assertFalse(watch.drain())

    def test_named_watch_ignores_other_files_and_the_folder_itself(self):
        watch = Watch(self.folder, names=['gate.json'])
        self.addCleanup(watch.close)
        (self.folder / 'other.json').write_text('{}')
        os.chmod(self.folder, 0o700)  # attribute change on the folder itself
        self.assertTrue(self.readable(watch))
        self.assertFalse(watch.drain())
        (self.folder / 'gate.json').write_text('{}')
        self.assertTrue(self.readable(watch))
        self.assertTrue(watch.drain())

    def test_missing_folders_are_an_error(self):
        with self.assertRaises(OSError):
            Watch(self.folder / 'missing')


@unittest.skipIf(os.name == 'nt', 'waits on pipes')
class InterruptTests(unittest.TestCase):
    def test_setting_wakes_a_waiting_thread(self):
        interrupt = Interrupt()
        self.addCleanup(interrupt.close)
        self.assertFalse(select.select([interrupt], [], [], 0)[0])
        threading.Timer(.05, interrupt.set).start()
        self.assertTrue(select.select([interrupt], [], [], 2)[0])
        self.assertTrue(interrupt.is_set())
        self.assertTrue(interrupt.wait(0))


if __name__ == '__main__':
    unittest.main()

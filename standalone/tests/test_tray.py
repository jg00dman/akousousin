# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The tray icon stays visible on any panel: monochrome states are named theme icons."""
import os
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from akousousin_app.ui import tray_icons

HICOLOR = """[Icon Theme]
Name=Hicolor
Directories=scalable/status

[scalable/status]
Size=22
MinSize=8
MaxSize=512
Type=Scalable
Context=Status
"""


class IconFileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        environment = patch.dict(os.environ, {'XDG_DATA_HOME': temporary.name})
        environment.start()
        self.addCleanup(environment.stop)

    def test_icons_are_symbolic_svgs_the_desktop_can_recolour(self):
        for name, text in tray_icons.contents().items():
            self.assertTrue(name.endswith('-symbolic'))
            root = ElementTree.fromstring(text)
            self.assertIn('ColorScheme-Text', text)
            self.assertIn('stroke="currentColor"', text)
            self.assertEqual(root.get('viewBox'), '0 0 24 24')
        self.assertEqual(len(tray_icons.names()), 1 + tray_icons.FRAMES)
        self.assertNotEqual(tray_icons.svg(0), tray_icons.svg(.5), 'reading frames must move')

    def test_install_is_idempotent_and_remove_cleans_up(self):
        folder = tray_icons.install()
        self.assertEqual(folder, Path(os.environ['XDG_DATA_HOME']) / 'icons/hicolor/scalable/status')
        ready = folder / (tray_icons.READY + '.svg')
        before = ready.stat().st_mtime_ns
        tray_icons.install()
        self.assertEqual(ready.stat().st_mtime_ns, before)
        ready.write_text('stale')
        tray_icons.install()
        self.assertEqual(ready.read_text(), tray_icons.svg())
        tray_icons.remove()
        self.assertEqual(list(folder.iterdir()), [])


@unittest.skipIf(os.name == 'nt', 'theme icons are for Linux trays')
class TrayIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        environment = patch.dict(os.environ, {'XDG_DATA_HOME': temporary.name, 'XDG_CONFIG_HOME': temporary.name})
        environment.start()
        self.addCleanup(environment.stop)
        index = Path(temporary.name) / 'icons/hicolor/index.theme'
        index.parent.mkdir(parents=True)
        index.write_text(HICOLOR)
        paths, name = QIcon.themeSearchPaths(), QIcon.themeName()
        self.addCleanup(lambda: (QIcon.setThemeSearchPaths(paths), QIcon.setThemeName(name)))
        QIcon.setThemeSearchPaths([])
        QIcon.setThemeName('')
        from akousousin_app.ui.tray import Tray
        self.tray = Tray(Path(temporary.name) / 'settings.json', lambda request: None, lambda: False)
        self.addCleanup(self.tray.icon.hide)

    def update(self, dictation=None, reading=None, downloads=(), problem=False):
        self.tray.update(running=True, dictation=dictation or {}, reading=reading or {}, pending=False,
                         downloads=list(downloads), available=None, problem=problem)

    def test_ready_icon_is_sent_by_name_so_the_panel_colours_it(self):
        self.assertTrue(self.tray.themed)
        self.assertEqual(self.tray.icon.icon().name(), tray_icons.READY)

    def test_reading_animates_through_named_frames(self):
        self.update(reading={'reading': True})
        seen = set()
        for _ in range(40):
            self.tray._frame()
            seen.add(self.tray.icon.icon().name())
        self.assertGreater(len(seen), 5)
        self.assertTrue(all(name.startswith(tray_icons.PREFIX + 'reading-') for name in seen))

    def test_coloured_states_are_drawn(self):
        self.update(dictation={'busy': True, 'phase': 'listening'})
        self.assertEqual(self.tray.icon.icon().name(), '')
        self.update()
        self.assertEqual(self.tray.icon.icon().name(), tray_icons.READY)
        self.update(problem=True)  # the caution badge is drawn on top
        self.assertEqual(self.tray.icon.icon().name(), '')

    def test_falls_back_to_drawing_when_the_theme_cannot_find_the_icons(self):
        with patch('akousousin_app.ui.tray.QIcon.fromTheme', return_value=QIcon()):
            from akousousin_app.ui.tray import Tray
            self.assertFalse(Tray._install_themed_icons())


if __name__ == '__main__':
    unittest.main()

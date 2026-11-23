# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The tray icon stays visible on light and dark panels, and shows all speech."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from akousousin_app.ui.tray import panel_tint


class PanelTintTests(unittest.TestCase):
    """Follow the panel, not the bundled Qt's palette (always light)."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.config, self.system, self.data = root / 'config', root / 'etc-xdg', root / 'usr-share'
        for folder in (self.config, self.system, self.data):
            folder.mkdir()
        environment = patch.dict(os.environ, {
            'XDG_CONFIG_HOME': str(self.config), 'XDG_CONFIG_DIRS': str(self.system),
            'XDG_DATA_HOME': str(root / 'local-share'), 'XDG_DATA_DIRS': str(self.data), 'XDG_CURRENT_DESKTOP': 'KDE'})
        environment.start()
        self.addCleanup(environment.stop)

    def write(self, name, text, folder=None):
        path = (folder or self.config) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_kubuntu_default_dark_panel_with_light_apps(self):
        # The global theme's defaults choose a dark Plasma style; the user's files say nothing about it.
        self.write('kdeglobals', '[KDE]\nLookAndFeelPackage=org.kubuntu.desktop\n[Colors:Window]\nForegroundNormal=35,38,41\n')
        self.write('plasma/look-and-feel/org.kubuntu.desktop/contents/defaults',
                   '[kdeglobals][General]\nColorScheme=BreezeLight\n\n[plasmarc][Theme]\nname=kubuntu\n', self.data)
        self.write('plasma/desktoptheme/kubuntu/colors', '[Colors:Window]\nForegroundNormal=239,240,241\n', self.data)
        self.assertEqual(panel_tint().name(), '#eff0f1')

    def test_a_system_wide_plasma_style_counts(self):
        self.write('kdeglobals', '[Colors:Window]\nForegroundNormal=35,38,41\n')
        self.write('plasmarc', '[Theme]\nname=breeze-dark\n', self.system)
        self.assertEqual(panel_tint().name(), '#fcfcfc')

    def test_the_users_own_choice_beats_the_system_default(self):
        self.write('plasmarc', '[Theme]\nname=breeze-dark\n', self.system)
        self.write('plasmarc', '[Theme]\nname=default\n')
        self.write('kdeglobals', '[Colors:Window]\nForegroundNormal=35,38,41\n')
        self.assertEqual(panel_tint().name(), '#232629')

    def test_a_style_that_follows_the_scheme_uses_the_scheme(self):
        self.write('plasmarc', '[Theme]\nname=default\n')
        self.write('plasma/desktoptheme/default/metadata.json', '{}', self.data)  # Breeze: no colors file
        self.write('kdeglobals', '[General]\nColorScheme=BreezeDark\n')
        self.write('color-schemes/BreezeDark.colors', '[Colors:Window]\nForegroundNormal=252,252,252\n', self.data)
        self.assertEqual(panel_tint().name(), '#fcfcfc')

    def test_breeze_dark_colour_scheme_gives_light_lines(self):
        self.write('kdeglobals', '[Colors:Window]\nBackgroundNormal=32,35,38\nForegroundNormal=252,252,252\n')
        self.assertEqual(panel_tint().name(), '#fcfcfc')

    def test_breeze_light_colour_scheme_gives_dark_lines(self):
        self.write('kdeglobals', '[Colors:Window]\nForegroundNormal=35,38,41\n')
        self.assertEqual(panel_tint().name(), '#232629')

    def test_dark_plasma_style_wins_over_a_light_colour_scheme(self):
        # Breeze Twilight: light apps, dark panel.
        self.write('kdeglobals', '[Colors:Window]\nForegroundNormal=35,38,41\n')
        self.write('plasmarc', '[Theme]\nname=breeze-dark\n')
        self.assertEqual(panel_tint().name(), '#fcfcfc')

    def test_light_plasma_style_wins_over_a_dark_colour_scheme(self):
        self.write('kdeglobals', '[Colors:Window]\nForegroundNormal=252,252,252\n')
        self.write('plasmarc', '[Theme]\nname=breeze-light\n')
        self.assertEqual(panel_tint().name(), '#232629')

    def test_gnome_top_bar_is_dark(self):
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'ubuntu:GNOME'}):
            self.assertEqual(panel_tint().name(), '#ffffff')

    def test_unknown_desktop_uses_the_app_palette(self):
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'XFCE'}):
            self.assertIsNone(panel_tint())

    def test_unreadable_settings_are_ignored(self):
        self.write('kdeglobals', '[Colors:Window]\nForegroundNormal=not,a,colour\n[broken')
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'XFCE'}):
            self.assertIsNone(panel_tint())


@unittest.skipIf(os.name == 'nt', 'Linux panels')
class TrayStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.config = Path(temporary.name)
        environment = patch.dict(os.environ, {'XDG_CONFIG_HOME': temporary.name, 'XDG_CURRENT_DESKTOP': 'KDE'})
        environment.start()
        self.addCleanup(environment.stop)
        from akousousin_app.ui.tray import Tray
        self.tray = Tray(self.config / 'settings.json', lambda request: None, lambda: False)
        self.addCleanup(self.tray.icon.hide)

    def update(self, **status):
        values = dict(running=True, dictation={}, reading={}, pending=False, downloads=[], available=None, problem=False)
        values.update(status)
        self.tray.update(**values)

    def middle_bar_colour(self):
        image = self.tray.icon.icon().pixmap(64, 64).toImage()
        return image.pixelColor(32, 32)  # the tallest, centre line

    def test_lines_are_light_on_breeze_dark(self):
        (self.config / 'kdeglobals').write_text('[Colors:Window]\nForegroundNormal=252,252,252\n')
        self.update()
        self.assertGreater(self.middle_bar_colour().lightness(), 200)

    def test_switching_scheme_recolours_without_restarting(self):
        (self.config / 'kdeglobals').write_text('[Colors:Window]\nForegroundNormal=35,38,41\n')
        self.update()
        self.assertLess(self.middle_bar_colour().lightness(), 80)
        (self.config / 'kdeglobals').write_text('[Colors:Window]\nForegroundNormal=252,252,252\n')
        self.update()
        self.assertGreater(self.middle_bar_colour().lightness(), 200)

    def test_speech_from_windows_apps_animates_like_read_aloud(self):
        self.update(speaking=True)
        self.assertEqual(self.tray.mode, 'reading')
        self.assertTrue(self.tray.timer.isActive() or os.environ.get('AKOUSOUSIN_NO_ANIMATION'))
        self.update(speaking=False)
        self.assertEqual(self.tray.mode, 'ready')


if __name__ == '__main__':
    unittest.main()

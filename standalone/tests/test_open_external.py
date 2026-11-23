# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import os
import unittest
from unittest.mock import patch

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from akousousin_app import qt_locale, runtime


@unittest.skipIf(os.name == 'nt', 'xdg-open is Linux only')
class OpenExternalTests(unittest.TestCase):
    def test_pages_open_without_the_bundled_libraries(self):
        bundled = {'LD_LIBRARY_PATH': '/tmp/.mount_x/usr/lib', 'QT_PLUGIN_PATH': '/tmp/.mount_x/plugins', 'HOME': '/home/me'}
        with patch.object(runtime, 'environment', return_value=bundled), \
                patch('subprocess.Popen') as popen:
            self.assertTrue(runtime.open_external('https://github.com/jg00dman/akousousin/releases'))
        arguments, options = popen.call_args
        self.assertEqual(arguments[0], ['xdg-open', 'https://github.com/jg00dman/akousousin/releases'])
        self.assertNotIn('LD_LIBRARY_PATH', options['env'])
        self.assertNotIn('QT_PLUGIN_PATH', options['env'])
        self.assertEqual(options['env']['HOME'], '/home/me')

    def test_a_missing_opener_is_reported(self):
        with patch('subprocess.Popen', side_effect=FileNotFoundError):
            self.assertFalse(runtime.open_external('https://example.org'))

    def test_links_in_the_window_use_the_same_opener(self):
        app = qt_locale.application()
        with patch.object(runtime, 'open_external') as opened:
            QDesktopServices.openUrl(QUrl('https://example.org/page'))
        opened.assert_called_once_with('https://example.org/page')


if __name__ == '__main__':
    unittest.main()

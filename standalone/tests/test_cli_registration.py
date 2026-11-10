# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import contextlib
import copy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from akousousin_app import main, settings


class CliRegistrationTests(unittest.TestCase):
    def test_explicit_wine_registration_can_run_without_opening_the_panel(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            prefix = Path(folder) / 'wine prefix'
            wine = '/path with spaces/Wine.AppImage'
            resource = Path(folder) / 'resources'
            installer = Mock()
            with patch.object(main.resources, 'bootstrap', return_value=copy.deepcopy(settings.DEFAULTS)), \
                    patch.object(main.resources, 'root', return_value=resource), \
                    patch.object(main, 'Installer', return_value=installer) as factory, \
                    patch.object(main.settings, 'register') as register, \
                    patch.object(main.runtime, 'call') as controller, \
                    patch.object(main.sys, 'argv', ['akousousin', '--settings', str(path),
                        '--wine-prefix', str(prefix), '--wine', wine, '--install-only']), \
                    contextlib.redirect_stdout(io.StringIO()):
                main.main()
            factory.assert_called_once_with(resource, prefix, wine, False)
            installer.install.assert_called_once()
            register.assert_called_once_with(path, prefix, wine)
            controller.assert_not_called()

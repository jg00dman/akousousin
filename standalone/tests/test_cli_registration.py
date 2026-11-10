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


class BundleLaunchTests(unittest.TestCase):
    def test_launch_prompt_quiet_and_noninteractive_installation(self):
        target = Path('/custom prefix/lib/akousousin')
        for quiet, tty, answer, skip in ((True, True, 'yes', False), (False, False, 'yes', False),
                                         (False, True, '', False), (False, True, ' YES ', False),
                                         (True, False, '', True)):
            with self.subTest(quiet=quiet, tty=tty, answer=answer), \
                    patch.object(main.sys, 'argv', ['akousousin', '--install-bundle', '/bundle'] +
                                 (['--quiet'] if quiet else []) + (['--without-speech-dispatcher'] if skip else [])), \
                    patch.object(main.os, 'geteuid', return_value=1000), \
                    patch.object(main.runtime, 'call', return_value=None), \
                    patch('akousousin_app.linux_bundle.install', return_value=target), \
                    patch('akousousin_app.linux_bundle.speech_setup') as setup, \
                    patch.object(main.sys, 'stdin', Mock(isatty=Mock(return_value=tty))), \
                    patch('builtins.input', return_value=answer) as prompt, \
                    patch.object(main.os, 'execve') as launch, contextlib.redirect_stdout(io.StringIO()):
                main.main()
                if skip:
                    setup.assert_not_called()
                else:
                    setup.assert_called_once_with(target, settings.config_path())
                self.assertEqual(prompt.called, not quiet and tty)
                if not quiet and tty and answer.strip().lower() == 'yes':
                    executable = str(target / 'akousousin')
                    self.assertEqual(launch.call_args.args[:2], (executable, [executable, '--configure']))
                    self.assertEqual(launch.call_args.args[2]['PYINSTALLER_RESET_ENVIRONMENT'], '1')
                else:
                    launch.assert_not_called()

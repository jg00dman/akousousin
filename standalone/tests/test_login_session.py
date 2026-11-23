# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The controller belongs to one desktop login and must not outlive it."""
import json
import os
import tempfile
import threading
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from akousousin_app import login_session, runtime, settings
from akousousin_app.controller import Sessions


def sessions(states, display=None, own=None):
    """Fake sd-login: session states by id, the user's display session and our own."""
    def string(call, *arguments):
        if call == 'sd_session_get_state':
            return states.get(arguments[0].decode())
        if call == 'sd_uid_get_display':
            return display
        if call == 'sd_pid_get_session':
            return own
    return patch('akousousin_app.login_session._string', side_effect=string)


class CurrentSessionTests(unittest.TestCase):
    def test_prefers_the_environment_session_while_it_runs(self):
        with sessions({'3': 'active', '7': 'active'}, display='7'), patch.dict(os.environ, {'XDG_SESSION_ID': '3'}):
            self.assertEqual(login_session.current(), '3')

    def test_a_stale_environment_session_falls_back_to_the_display_session(self):
        # systemd's user manager outlives logins, so its environment can name an old one.
        with sessions({'3': 'closing', '7': 'active'}, display='7'), patch.dict(os.environ, {'XDG_SESSION_ID': '3'}):
            self.assertEqual(login_session.current(), '7')

    def test_unknown_without_logind(self):
        with sessions({}), patch.dict(os.environ, {'XDG_SESSION_ID': ''}):
            self.assertIsNone(login_session.current())

    def test_closing_and_gone_sessions_are_not_running(self):
        with sessions({'5': 'closing', '6': 'online'}):
            self.assertFalse(login_session.running('5'))
            self.assertFalse(login_session.running('9'))
            self.assertTrue(login_session.running('6'))

    def test_real_library_lookup_does_not_fail_without_a_session(self):
        login_session.state('no-such-session')
        login_session.current()


class ReplaceStaleTests(unittest.TestCase):
    def call(self, theirs, states, mine='7'):
        calls = []
        replies = iter([{'login_session': theirs}, {'stopping': True}, None])

        def call(path, request, launch=True, timeout=85):
            calls.append(request['command'])
            return next(replies)
        with sessions(states, display=mine), patch.dict(os.environ, {'XDG_SESSION_ID': ''}), \
                patch('akousousin_app.runtime.call', side_effect=call):
            replaced = runtime.replace_stale('settings.json')
        return replaced, calls

    @unittest.skipIf(os.name == 'nt', 'logind is Linux')
    def test_controller_from_an_ended_login_is_quit_before_a_new_one_starts(self):
        replaced, calls = self.call('3', {'7': 'active'})
        self.assertTrue(replaced)
        self.assertEqual(calls, ['status', 'quit', 'status'])

    def test_controller_of_this_login_is_kept(self):
        self.assertEqual(self.call('7', {'7': 'active'}), (False, ['status']))

    def test_controller_of_another_live_login_is_left_alone(self):
        self.assertEqual(self.call('4', {'4': 'active', '7': 'active'}), (False, ['status']))

    def test_older_controllers_without_a_session_are_left_alone(self):
        self.assertEqual(self.call(None, {'7': 'active'}), (False, ['status']))


class ControllerLockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'settings.json'
        settings.save(path, json.loads(json.dumps(settings.DEFAULTS)))
        with patch('akousousin_app.controller.Service', return_value=Mock()):
            self.state = Sessions(path)
        self.state.selection = Mock()
        self.state.selection.status.return_value = {'reading': False}

    @unittest.skipIf(os.name == 'nt', 'reading shortcuts are Linux-only')
    def test_enabling_reading_shortcuts_does_not_need_the_controller_lock(self):
        # Checking Speech Dispatcher can take many seconds; the tray and other
        # requests must not queue behind it.
        held, release = threading.Event(), threading.Event()

        def hold():
            with self.state.lock:
                held.set()
                release.wait(5)
        holder = threading.Thread(target=hold)
        holder.start()
        held.wait(5)
        done = []
        worker = threading.Thread(target=lambda: done.append(self.state.request({'command': 'selection-shortcuts-enable'})))
        worker.start()
        worker.join(2)
        release.set()
        holder.join()
        self.assertEqual(done, [{'reading': False}])
        self.state.selection.enable.assert_called_once_with()

    def test_restoring_shortcuts_takes_the_lock_per_command_only(self):
        self.state.desktop_preferences = Mock()
        self.state.desktop_preferences.load.return_value = {'dictation_enabled': False, 'reading_enabled': True}
        seen = []
        self.state.selection.enable.side_effect = lambda: seen.append(self.state.lock._is_owned())
        self.state.restore_desktop_shortcuts()
        self.assertEqual(seen, [False])

    def test_status_reports_the_login_session(self):
        self.state.login_session = '7'
        self.state.service.health.return_value = None
        self.assertEqual(self.state.request({'command': 'status'})['login_session'], '7')


class OwnerTests(unittest.TestCase):
    def test_a_helper_notices_its_owner_has_gone(self):
        with patch.dict(os.environ, {'AKOUSOUSIN_OWNER_PID': str(os.getppid())}):
            self.assertFalse(runtime.owner_gone())
        with patch.dict(os.environ, {'AKOUSOUSIN_OWNER_PID': '1'}):
            self.assertEqual(runtime.owner_gone(), os.getppid() != 1)
        with patch.dict(os.environ, {'AKOUSOUSIN_OWNER_PID': ''}):
            self.assertFalse(runtime.owner_gone())


if __name__ == '__main__':
    unittest.main()

import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from akousousin_app import settings
from akousousin_app.controller import Sessions


class SessionsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'settings.json'
        settings.save(self.path, settings.DEFAULTS)
        with patch('akousousin_app.controller.Service', return_value=Mock()):
            self.state = Sessions(self.path)

    def acquire(self, name):
        self.state.request({'command': 'acquire', 'session': name, 'pid': __import__('os').getpid()})

    def test_last_session_stops_backend_and_controller(self):
        self.acquire('logos')
        self.state.request({'command': 'release', 'session': 'logos'})
        self.state.service.stop.assert_called_once_with(5000)
        self.assertTrue(self.state.closed)

    def test_one_application_cannot_stop_another(self):
        self.acquire('logos')
        self.acquire('other')
        self.state.request({'command': 'release', 'session': 'logos'})
        self.state.service.stop.assert_not_called()
        self.assertFalse(self.state.closed)

    def test_independent_start_remains_after_logos(self):
        self.state.request({'command': 'start'})
        self.acquire('logos')
        self.state.request({'command': 'release', 'session': 'logos'})
        self.state.service.stop.assert_not_called()
        self.assertFalse(self.state.closed)

    def test_configuration_panel_does_not_acquire_a_session(self):
        with patch('akousousin_app.controller.subprocess.Popen'):
            self.state.request({'command': 'configure'})
        self.assertFalse(self.state.independent)
        self.assertEqual(self.state.owners, {})
        self.state.service.stop.assert_not_called()

    def test_explicit_quit_stops_even_while_in_use(self):
        self.acquire('logos')
        self.state.request({'command': 'quit'})
        self.assertTrue(self.state.closed)
        self.state.service.stop.assert_called_once()

    def test_unknown_release_does_not_close_running_app(self):
        self.state.request({'command': 'release', 'session': 'unknown'})
        self.assertFalse(self.state.closed)

    def test_dead_owner_or_reused_pid_is_reaped(self):
        self.acquire('logos')
        with patch('akousousin_app.controller.psutil.Process') as process:
            process.return_value.create_time.return_value = -1
            self.state.reap()
        self.assertTrue(self.state.closed)

    def test_failed_start_does_not_create_a_session(self):
        self.state.service.start.side_effect = RuntimeError('Missing model')
        with self.assertRaisesRegex(RuntimeError, 'Missing model'):
            self.acquire('logos')
        self.assertEqual(self.state.owners, {})

    def test_dispatcher_wake_survives_another_app_releasing_its_session(self):
        self.acquire('logos')
        self.state.request({'command': 'wake'})
        self.state.request({'command': 'release', 'session': 'logos'})
        self.state.service.stop.assert_not_called()
        self.assertFalse(self.state.closed)
        self.assertFalse(self.state.independent)
        self.state.request({'command': 'quit'})
        self.state.service.stop.assert_called_once()

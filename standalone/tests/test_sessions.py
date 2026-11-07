# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
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

    def test_configure_reuses_live_panel_and_requests_activation(self):
        panel = Mock(pid=1234)
        panel.poll.return_value = None
        with patch('akousousin_app.controller.subprocess.Popen', return_value=panel) as launch:
            first = self.state.request({'command': 'configure'})
            activation = self.state.panel_activation
            second = self.state.request({'command': 'configure'})
        launch.assert_called_once()
        self.assertEqual(first['panels'], second['panels'])
        self.assertGreater(self.state.panel_activation, activation)

    def test_configure_replaces_a_closed_panel(self):
        old = Mock(); old.poll.return_value = 0
        self.state.panels = [old]
        with patch('akousousin_app.controller.subprocess.Popen') as launch:
            self.state.request({'command': 'configure'})
        launch.assert_called_once()

    def test_quit_closes_owned_selection_reader(self):
        with patch.object(self.state.selection, 'close') as close:
            self.state.request({'command': 'quit'})
        close.assert_called_once()

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

    def test_dictation_ownership_survives_last_tts_session(self):
        self.acquire('logos')
        with patch.object(self.state.input, 'prepare') as prepare:
            result = self.state.request({'command': 'stt-prepare'})
        prepare.assert_called_once()
        self.assertIn('desktop', result)
        self.state.request({'command': 'release', 'session': 'logos'})
        self.state.service.stop.assert_not_called()
        self.assertFalse(self.state.closed)

    def test_bad_recording_duration_never_starts_capture(self):
        with patch.object(self.state.input, 'start') as start:
            for seconds in (0, 31, True, '10'):
                with self.assertRaises(ValueError):
                    self.state.request({'command': 'stt-start', 'seconds': seconds})
        start.assert_not_called()


    def test_quit_closes_owned_panel_even_if_input_cleanup_fails(self):
        import subprocess, sys
        panel = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        self.addCleanup(lambda: panel.kill() if panel.poll() is None else None)
        self.state.panels.append(panel)
        self.state.desktop = Mock()
        desktop = self.state.desktop
        with patch.object(self.state.input, 'close', side_effect=RuntimeError('Input cleanup failed')), self.assertLogs(level='ERROR'):
            self.state.request({'command': 'quit'})
        self.assertIsNotNone(panel.poll())
        self.assertEqual(self.state.panels, [])
        desktop.close.assert_called_once()
        self.state.service.stop.assert_called_once()
        self.assertTrue(self.state.closed)

    def test_start_dictation_enables_desktop_on_first_use(self):
        with patch('akousousin_app.desktop_input.Desktop') as factory:
            self.state.request({'command': 'stt-toggle'})
        factory.return_value.start.assert_called_once_with(listen=True)

    def test_shutdown_does_not_accept_new_work(self):
        self.state.quit()
        with self.assertRaisesRegex(RuntimeError, 'shutting down'):
            self.state.request({'command': 'configure'})


    def test_update_handoff_keeps_only_the_updater_panel_alive(self):
        import subprocess, sys
        panels = [subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']) for _ in range(2)]
        def cleanup():
            for panel in panels:
                if panel.poll() is None: panel.kill()
                panel.wait(timeout=3)
        self.addCleanup(cleanup)
        self.state.panels = panels.copy()
        self.state.request({'command': 'quit', 'update_pid': panels[0].pid})
        self.assertIsNone(panels[0].poll(), 'Updater was killed during replacement')
        self.assertIsNotNone(panels[1].poll(), 'Unrelated panel survived update shutdown')
        self.assertTrue(self.state.closed)
        self.assertEqual(self.state.panels, [])

# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from akousousin_app.selection_shortcuts import ReadingShortcuts
from akousousin_app.selection_controller import Selection


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        try:
            from dbus_next import MessageType
        except ImportError:
            self.skipTest('Install the desktop dependency')
        self.type = MessageType.SIGNAL
        self.activate, self.cancel = Mock(), Mock()
        self.shortcuts = ReadingShortcuts(self.activate, self.cancel)
        self.shortcuts.enabled = True
        self.shortcuts.shortcuts = '/session/reading'
        self.shortcuts.portal_owner = ':1.5'

    def signal(self, member, key='read-selection', session='/session/reading', sender=':1.5'):
        return SimpleNamespace(message_type=self.type, interface='org.freedesktop.portal.GlobalShortcuts',
                               member=member, body=[session, key, 0, {}], sender=sender)

    def test_activation_release_and_repeat_do_not_fire_twice_for_one_press(self):
        for member in ('Activated', 'Activated', 'Deactivated', 'Activated'):
            self.shortcuts.message(self.signal(member))
        self.assertEqual(self.activate.call_count, 2)
        self.activate.assert_called_with(clipboard=False)

    def test_copied_text_is_explicit_and_other_sessions_and_senders_are_ignored(self):
        self.shortcuts.message(self.signal('Activated', session='/session/dictation'))
        self.shortcuts.message(self.signal('Activated', sender=':1.9'))
        self.shortcuts.message(self.signal('Activated', key='dictate'))
        self.activate.assert_not_called()
        self.shortcuts.message(self.signal('Activated', key='read-clipboard'))
        self.activate.assert_called_once_with(clipboard=True)

    def test_closed_permission_stops_only_its_reader(self):
        self.shortcuts.sessions = ['/session/reading']
        message = self.signal('Closed')
        message.interface = 'org.freedesktop.portal.Session'
        message.path = '/session/reading'
        self.shortcuts.message(message)
        self.cancel.assert_called_once()
        self.assertFalse(self.shortcuts.enabled)


class ReaderOwnershipTests(unittest.TestCase):
    def test_repeat_stops_owned_reader_and_quit_releases_it(self):
        started = threading.Event()
        def read(path, clipboard, cancelled):
            started.set()
            if not cancelled.wait(2):
                raise AssertionError('Reader was not stopped')
        owner = Selection('/profile')
        with patch('akousousin_app.selection.toggle', side_effect=read):
            owner.toggle()
            self.assertTrue(started.wait(1))
            owner.toggle()
            owner.thread.join(2)
        self.assertFalse(owner.status()['reading'])
        self.assertEqual(owner.state, 'Reading stopped')
        owner.close()

    def test_reader_failure_is_visible_and_reported_without_starting_another_reader(self):
        owner = Selection('/profile')
        with patch('akousousin_app.selection.toggle', side_effect=RuntimeError('No text available')), \
                patch('akousousin_app.selection.notify') as notify:
            owner.toggle(); owner.thread.join(2)
        self.assertIn('No text available', owner.status()['state'])
        notify.assert_called_once_with('No text available')

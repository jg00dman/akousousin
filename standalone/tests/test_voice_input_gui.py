# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Native Qt controls, accessible names, keyboard navigation and voice assignments."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

from akousousin_app import resources, settings
from akousousin_app.panel import Panel
from akousousin_app.qt_locale import application


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != 'nt' and not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
            os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.app = application()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / 'settings.json'
        for context in (patch.dict(os.environ, {f'XDG_{key}_HOME': str(self.root / key) for key in ('CONFIG','STATE','DATA')}),
                        patch('akousousin_app.panel.Panel.poll'), patch('akousousin_app.qt_dictation.Dictation.refresh_mics')):
            context.start()
            self.addCleanup(context.stop)
        self.panel = Panel(self.path, False)
        self.panel.resize(760,480)
        self.panel.show()
        self.app.processEvents()
        self.addCleanup(self.panel.close)

    def test_keyboard_reaches_six_pages_and_accessible_fields(self):
        nav = self.panel.nav
        nav.setFocus()
        self.assertEqual(QAccessible.queryAccessibleInterface(nav).text(QAccessible.Name), 'Navigation')
        for idx, name in enumerate(self.panel.destinations):
            if idx:
                QTest.keyClick(nav, Qt.Key_Down)
            self.assertEqual(nav.currentItem().text(), name)
            self.assertEqual(self.panel.stack.currentWidget().accessibleName(), name)
        self.panel.go('Overview')
        for widget in (self.panel.sample, self.panel.test_result, self.panel.status):
            self.assertTrue(QAccessible.queryAccessibleInterface(widget).text(QAccessible.Name))
        self.assertFalse(self.panel.speak.isEnabled())
        self.assertTrue(self.panel.starter.isVisible())
        self.assertTrue(self.panel.test_result.isVisible())

    def test_default_and_per_language_assignments_survive_reopen(self):
        page = self.panel.voices
        model = self.root / 'v.onnx'
        model.touch()
        Path(str(model) + '.json').write_text('{}')
        for key in ('Alpha', 'Beta'):
            resources.register_voice(self.path, key, dict(path=str(model), language='fr_FR', name=key, quality='local'))
        self.panel.reload()
        self.panel.go('Voices')
        page.search.setText('Alpha')
        self.assertEqual(page.tree.topLevelItemCount(), 1)
        self.assertTrue(page.default.isVisible())
        def request(path, payload):
            self.assertIn(payload['command'], ('voice', 'language-voice'))
            return {'pending_registration': settings.select_voice(path, payload['voice'],
                    language_only=payload['command'] == 'language-voice')}
        with patch('akousousin_app.runtime.call', side_effect=request), patch.object(self.panel, 'run', lambda f, done: done(f())):
            page.default.click()
            page.search.setText('Beta')
            page.prefer.click()
        config = settings.load(self.path)
        self.assertEqual(config['voice'], 'Alpha')
        self.assertEqual(config['language_voices']['fr_FR'], 'Beta')
        self.assertEqual(config['book_language'], '')

    def test_explicit_preview_and_filtered_catalogue(self):
        page = self.panel.voices
        self.panel.go('Voices')
        page.search.setText(resources.STARTER)
        self.assertTrue(page.preview.isEnabled())
        self.assertTrue(page.download.isVisible())
        self.assertFalse(page.default.isVisible())
        with patch.object(self.panel, 'play') as play:
            page.preview.click()
            self.assertEqual(play.call_args.args, (resources.STARTER, 'en/en_US/ljspeech/medium'))
        page.installed.setChecked(True)
        self.assertEqual(page.tree.topLevelItemCount(), 0)

    def test_import_removal_preserves_original_file(self):
        model = self.root / 'local.onnx'
        model.touch()
        Path(str(model) + '.json').write_text('{}')
        resources.register_voice(self.path, 'local', dict(path=str(model), language='de_DE', name='local', quality='local'))
        self.panel.reload()
        self.panel.voices.search.setText('local')
        with patch.object(self.panel, 'confirm', return_value=True), patch('akousousin_app.runtime.call'), \
                patch.object(self.panel, 'run', lambda f, done: done(f())):
            self.panel.voices.delete()
        self.assertTrue(model.exists())
        self.assertFalse(settings.load(self.path)['voices'])

    def test_about_has_keyboard_link_and_local_notices(self):
        self.panel.go('About')
        page = self.panel.stack.currentWidget()
        from PySide6.QtWidgets import QLabel
        link = next(w for w in page.findChildren(QLabel) if 'biblia.com' in w.text())
        self.assertTrue(link.focusPolicy() & Qt.TabFocus)
        content = ' '.join(w.text() for w in page.findChildren(QLabel))
        for word in ('ἀκούσουσιν', 'and those who hear will live.', 'Logos', 'Piper', 'Whisper', 'faster-whisper'):
            self.assertIn(word, content)
        self.assertTrue(any('licences and notices' in b.text() for b in page.findChildren(QPushButton)))

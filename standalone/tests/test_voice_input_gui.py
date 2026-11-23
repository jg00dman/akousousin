# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The control panel: keyboard navigation, accessible names and the main workflows."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

if os.name != 'nt' and not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPushButton

from akousousin_app import network, resources, settings
from akousousin_app.panel import Panel
from akousousin_app.qt_locale import application
from akousousin_app.ui.pages import PAGES


def synchronous(window):
    """Run panel tasks inline so tests can follow each workflow step by step."""
    def run(work, done=None, *, failed=None, key=None, background=False):
        try:
            value = work()
        except Exception as error:
            (failed or window.tasks.failed.emit)(error)
            return True
        if done:
            done(value)
        return True
    window.tasks.run = run


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / 'settings.json'
        for context in (patch.dict(os.environ, {f'XDG_{key}_HOME': str(self.root / key) for key in ('CONFIG', 'STATE', 'DATA')}),
                        patch('akousousin_app.ui.pages.dictation.discover_microphones', return_value=[('', 'System default')])):
            context.start()
            self.addCleanup(context.stop)
        self.window = Panel(self.path, offer_install=False, poll=False)
        synchronous(self.window)
        self.window.resize(1100, 760)
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self.window.close)

    def voices(self):
        self.window.go('voices')
        return self.window.pages['voices']

    def import_voice(self, key, language):
        model = self.root / (key + '.onnx')
        model.touch()
        Path(str(model) + '.json').write_text('{}')
        resources.register_voice(self.path, key, dict(path=str(model), language=language, name=key, quality='local'))
        self.window.state.reload()
        return model

    def test_keyboard_reaches_every_page_with_accessible_names(self):
        nav = self.window.nav
        nav.setFocus()
        self.assertEqual(QAccessible.queryAccessibleInterface(nav).text(QAccessible.Name), 'Pages')
        self.assertEqual(nav.count(), len(PAGES))
        for index in range(nav.count()):
            if index:
                QTest.keyClick(nav, Qt.Key_Down)
            page = self.window.current_page()
            self.assertEqual(nav.currentItem().text(), page.title())
            self.assertEqual(self.window.stack.currentWidget().accessibleName(), page.title())
        self.window.activateWindow()
        if QTest.qWaitForWindowActive(self.window, 1000):  # shortcuts need an active window
            QTest.keyClick(self.window.nav, Qt.Key_2, Qt.ControlModifier)
            self.assertEqual(self.window.current_page().key, 'voices')
        for page in self.window.pages.values():
            for button in page.findChildren(QPushButton):
                self.assertTrue(button.text() or button.accessibleName(), f'{page.key}: unnamed button')

    def test_old_page_names_still_open_the_right_page(self):
        self.window.go('Updates')
        self.assertEqual(self.window.current_page().key, 'advanced')
        self.window.go('Dictation')
        self.assertEqual(self.window.current_page().key, 'dictation')

    def test_default_and_per_language_voices_can_be_chosen(self):
        for key in ('Alpha', 'Beta'):
            self.import_voice(key, 'fr_FR')
        page = self.voices()
        page.search.setText('Beta')
        self.assertEqual(page.key_(), 'Beta')

        def request(path, payload, launch=True):
            return {'pending_registration': settings.select_voice(path, payload['voice'],
                    language_only=payload['command'] == 'language-voice')}
        with patch('akousousin_app.runtime.call', side_effect=request):
            self.assertTrue(page.make_default.isVisibleTo(page))
            page.make_default.click()
            page.search.setText('Alpha')
            page.use_for.click()
        config = settings.load(self.path)
        self.assertEqual(config['voice'], 'Beta')
        self.assertEqual(config['language_voices']['fr_FR'], 'Alpha')
        self.assertEqual(page.default.currentData(), 'Beta')
        self.assertIn('Default voice', page.library.role('Beta', config))

    def test_catalogue_filter_and_sample_preview(self):
        page = self.voices()
        page.search.setText(resources.STARTER)
        self.assertEqual(page.key_(), resources.STARTER)
        self.assertTrue(page.download.isVisibleTo(page))
        self.assertFalse(page.make_default.isVisibleTo(page))
        with patch.object(self.window.state.preview, 'toggle') as toggle:
            page.play.click()
        self.assertEqual(toggle.call_args.args[0], resources.STARTER)
        self.assertEqual(toggle.call_args.args[2], 'en/en_US/ljspeech/medium')
        page.show_group.buttons()[1].click()  # Installed only
        self.assertIsNone(page.key_())

    def test_removing_an_imported_voice_keeps_the_original_file(self):
        model = self.import_voice('local', 'de_DE')
        page = self.voices()
        page.search.setText('local')
        with patch.object(page, 'confirm', return_value=True), patch('akousousin_app.runtime.call'):
            page.delete()
        self.assertTrue(model.exists())
        self.assertFalse(settings.load(self.path)['voices'])

    def test_blocking_the_internet_is_saved_and_enforced(self):
        self.window.go('privacy')
        page = self.window.pages['privacy']
        page.blocked.click()
        self.assertTrue(settings.load(self.path)['network_blocked'])
        self.assertFalse(page.samples.isEnabled())
        with self.assertRaises(network.NetworkBlocked):
            network.require(self.path, 'testing')
        from akousousin_app import updates
        with self.assertRaises(network.NetworkBlocked):
            updates.perform_check(self.path)

    @unittest.skipIf(os.name == 'nt', 'XDG autostart is for Linux desktops')
    def test_start_at_login_is_offered_once_and_can_be_turned_off(self):
        from akousousin_app import startup
        page = self.window.pages['advanced']
        with patch.object(page, 'confirm', return_value=True) as asked, \
                patch('akousousin_app.ui.pages.advanced.updates.is_appimage', return_value=False):
            page.first_run()
            page.first_run()
        asked.assert_called_once()
        self.assertTrue(startup.enabled())
        self.assertTrue(settings.load(self.path)['login_offered'])
        self.window.go('advanced')
        self.assertTrue(page.login.isChecked())
        page.login.click()
        self.assertFalse(startup.enabled())
        page.preload.setCurrentIndex(page.preload.findData(False))
        page.preload.activated.emit(page.preload.currentIndex())
        self.assertFalse(settings.load(self.path)['preload'])

    def test_declining_start_at_login_is_remembered(self):
        from akousousin_app import startup
        page = self.window.pages['advanced']
        with patch.object(page, 'confirm', return_value=False) as asked, \
                patch('akousousin_app.ui.pages.advanced.updates.is_appimage', return_value=False):
            page.first_run()
            page.first_run()
        asked.assert_called_once()
        self.assertFalse(startup.enabled())

    def test_about_explains_the_name_with_a_keyboard_link(self):
        self.window.go('about')
        page = self.window.pages['about']
        labels = page.findChildren(QLabel)
        link = next(w for w in labels if 'bible.com/bible/3034/JHN.5.25.BSB' in w.text())
        self.assertTrue(link.focusPolicy() & Qt.TabFocus)
        content = ' '.join(w.text() for w in labels)
        for words in ('ἀκούσουσιν', 'Greek word for “they will hear”', 'those who hear will live.', 'Logos', 'Piper', 'Whisper', 'faster-whisper'):
            self.assertIn(words, content)
        self.assertTrue(any('licence texts' in b.text() for b in page.findChildren(QPushButton)))

    @unittest.skipIf(os.name == 'nt', 'Linux microphone level')
    def test_microphone_level_runs_only_while_dictation_is_visible(self):
        import sys
        import time
        from akousousin_app.ui.meter import loudness
        self.assertEqual(loudness(b''), 0.0)
        self.assertGreater(loudness(b'\x00\x40' * 800), loudness(b'\x10\x00' * 800))
        emitter = "import sys,time\nwhile True:\n sys.stdout.buffer.write(b'\\x00\\x40'*320); sys.stdout.buffer.flush(); time.sleep(.02)"
        levels = []
        with patch('akousousin_backend.audio_system.record_command', return_value=[sys.executable, '-c', emitter]) as command:
            self.window.go('dictation')
            page = self.window.pages['dictation']
            page.monitor.level.connect(levels.append)
            self.assertTrue(page.monitor.running)
            self.assertEqual(command.call_args.args[1], 'Microphone level')
            deadline = time.monotonic() + 5
            while not any(levels) and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.01)
            self.assertGreater(max(levels), .5)
            self.assertEqual(page.meter.accessibleDescription(), 'Hearing sound')
            self.window.go('voices')
            self.assertFalse(page.monitor.running, 'the microphone closes when the page is left')
            self.window.go('dictation')
            self.window.showMinimized()
            self.app.processEvents()
            self.assertFalse(page.monitor.running, 'the microphone closes when the window is minimised')

    def test_closing_with_work_running_hides_and_waits(self):
        self.window.tasks.active.add('download')
        self.window.close()
        self.assertFalse(self.window.isVisible())
        self.assertTrue(self.window.quit_when_idle)
        self.window.tasks.active.clear()


if __name__ == '__main__':
    unittest.main()

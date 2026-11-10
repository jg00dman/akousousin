# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Actual Tk hit-testing: the Start button must not be hidden behind its row."""
import copy
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from akousousin_app import settings
from akousousin_app.voice_input import VoiceInput


@unittest.skipUnless(os.environ.get('DISPLAY'), 'Run under xvfb-run for the GUI test')
class VoiceInputGuiTests(unittest.TestCase):
    def test_task_order_unified_shortcuts_and_live_microphone_state(self):
        from akousousin_app.panel import Panel
        from akousousin_app.panel_layout import PAGES
        with tempfile.TemporaryDirectory() as folder, patch('akousousin_app.resources.bootstrap', return_value=copy.deepcopy(settings.DEFAULTS)), \
                patch('akousousin_app.catalogue.catalogue', return_value={}), \
                patch('akousousin_app.voice_input.discover_microphones', return_value=[('', 'System default')]), \
                patch('akousousin_app.runtime.call', return_value=None):
            panel = Panel(Path(folder) / 'settings.json', offer_install=False)
            self.addCleanup(panel.root.destroy)
            panel.root.geometry('760x480'); panel.root.update()
            self.assertEqual(tuple(panel.nav_pages), PAGES)
            def buttons(parent):
                for child in parent.winfo_children():
                    if isinstance(child, ttk.Button): yield child
                    yield from buttons(child)
            shortcut_labels = [button.cget('text') for button in buttons(panel.pages['Shortcuts'])]
            self.assertIn('Change dictation shortcut…', shortcut_labels)
            self.assertIn('Change reading shortcuts…', shortcut_labels)
            self.assertFalse(any('shortcut' in str(button.cget('text')).lower()
                                 for button in buttons(panel.pages['Dictation'])))
            ready = {'state':'Recognition ready', 'loaded':True, 'phase':'ready', 'busy':False,
                     'dictation_active':False, 'microphone_open':False}
            panel.update_home({'reading':{}, 'dictation':ready})
            self.assertIn('Microphone off', panel.dictation_status.get())
            self.assertTrue(panel.home_stop_dictation.instate(['disabled']))
            ready.update(phase='listening', busy=True, dictation_active=True, microphone_open=True)
            panel.update_home({'reading':{}, 'dictation':ready})
            self.assertIn('Microphone listening', panel.dictation_status.get())
            self.assertFalse(panel.home_stop_dictation.instate(['disabled']))
            panel.show('About'); panel.root.update()
            copy_button = next(button for button in buttons(panel.pages['About']) if button.cget('text') == 'Copy diagnostics')
            copy_button.invoke(); panel.root.update()
            self.assertIn('Configuration:', panel.root.clipboard_get())
            self.assertNotIn('restore_token', panel.root.clipboard_get())
            for name in PAGES:
                panel.show(name); panel.root.update()
                self.assertTrue(panel.nav_pages[name].winfo_ismapped())
                if name in panel.scrolls:
                    self.assertTrue(panel.scrolls[name].scrollbar.winfo_ismapped())

    def setUp(self):
        self.callback_errors = []
        reporter = patch.object(tk.Tk, 'report_callback_exception', side_effect=lambda *args: self.callback_errors.append(args))
        reporter.start(); self.addCleanup(reporter.stop)
        self.addCleanup(lambda: self.assertEqual(self.callback_errors, [], 'Tk callback errors'))

    def test_speed_steps_and_confirmed_import_removal(self):
        from akousousin_app.panel import Panel
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            original = Path(folder) / 'local.onnx'; original.write_bytes(b'keep model')
            config = copy.deepcopy(settings.DEFAULTS)
            config.update(voice='local', speed=1.23456789, voices={'local': {
                'path':str(original), 'language':'en_US', 'name':'Local', 'quality':'local', 'sample_rate':22050}})
            settings.save(path, config)
            with patch('akousousin_app.resources.root', return_value=Path(folder)), \
                    patch('akousousin_app.catalogue.catalogue', return_value={}), \
                    patch('akousousin_app.runtime.call', return_value=None), \
                    patch('akousousin_app.updates.is_appimage', return_value=False), \
                    patch('akousousin_app.voice_input.discover_microphones', return_value=[('', 'System default')]):
                panel = Panel(path, offer_install=False)
                try:
                    panel.root.update()
                    status = 'A long diagnostic status — ready for copying.'
                    panel.status.set(status)
                    panel.root.update()
                    panel.status_field.focus_force()
                    panel.status_field.event_generate('<Control-a>'); panel.root.update()
                    panel.status_field.event_generate('<Control-c>'); panel.root.update()
                    self.assertEqual(panel.root.clipboard_get(), status)
                    copy_button = next(child for child in panel.status_field.master.winfo_children()
                                if isinstance(child, ttk.Button) and child.cget('text') == 'Copy')
                    copy_button.invoke(); panel.root.update()
                    self.assertEqual(panel.root.clipboard_get(), status)
                    self.assertEqual(panel.speed.get(), 1.25)
                    panel.speed_slider.set(2.123456)
                    panel.root.update()
                    self.assertEqual(panel.speed.get(), 2.0)
                    self.assertLessEqual(len(panel.speed_spin.get().partition('.')[2]), 2)
                    panel.speed_slider.set(4)
                    self.assertTrue(panel.save())
                    self.assertEqual(settings.load(path)['speed'], 4)
                    panel.root.geometry('760x480')
                    panel.show('Voice library')
                    panel.root.update()
                    self.assertTrue(panel.delete_voice_button.winfo_ismapped())
                    self.assertLessEqual(panel.delete_voice_button.winfo_rooty() + panel.delete_voice_button.winfo_height(),
                                         panel.root.winfo_rooty() + panel.root.winfo_height())
                    panel.tree.selection_set('local')
                    panel.tree.event_generate('<<TreeviewSelect>>'); panel.root.update()
                    self.assertFalse(panel.delete_voice_button.instate(['disabled']))
                    with patch('akousousin_app.panel.messagebox.askyesno', return_value=True):
                        panel.delete_voice_button.invoke()
                    deadline = time.monotonic() + 3
                    while panel.busy and time.monotonic() < deadline:
                        panel.root.update(); time.sleep(.01)
                    self.assertFalse(panel.busy)
                    self.assertFalse(settings.load(path)['voices'])
                    self.assertEqual(original.read_bytes(), b'keep model')
                    self.assertNotIn('local', panel.tree.get_children())
                    panel.show('Overview'); panel.root.update()
                    self.assertTrue(panel.starter_card.winfo_ismapped())
                finally:
                    panel.root.destroy()

    def test_header_uses_actual_application_image(self):
        from akousousin_app.panel import Panel
        with tempfile.TemporaryDirectory() as folder:
            icon_root = tk.Tk()
            picture = tk.PhotoImage(master=icon_root, width=128, height=128)
            picture.put('#087e82', to=(0, 0, 128, 128))
            picture.write(str(Path(folder) / 'akousousin.png'), format='png')
            icon_root.destroy()
            with patch('akousousin_app.resources.root', return_value=Path(folder)), \
                    patch('akousousin_app.resources.bootstrap', return_value=copy.deepcopy(settings.DEFAULTS)), \
                    patch('akousousin_app.catalogue.catalogue', return_value={}), \
                    patch('akousousin_app.runtime.call', return_value=None), \
                    patch('akousousin_app.updates.is_appimage', return_value=False), \
                    patch('akousousin_app.voice_input.discover_microphones', return_value=[('', 'System default')]):
                panel = Panel(Path(folder) / 'settings.json', offer_install=False)
                try:
                    panel.root.update()
                    self.assertEqual(panel.header_icon.width(), 32)
                    self.assertEqual(panel.header_icon.get(0, 0), (8, 126, 130))
                    header = panel.root.winfo_children()[0]
                    labels = [child for child in header.winfo_children() if isinstance(child, ttk.Label)]
                    self.assertTrue(any(str(child.cget('image')) for child in labels))
                    self.assertTrue(any(child.cget('text') == 'Akousousin' for child in labels))
                    self.assertFalse(any('▥' in str(child.cget('text')) for child in labels))
                finally:
                    panel.root.destroy()

    def test_update_notifications_in_every_format_install_action_only_in_appimage(self):
        from akousousin_app.panel import Panel
        def widgets(parent):
            for child in parent.winfo_children():
                yield child
                yield from widgets(child)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            settings.save(path, copy.deepcopy(settings.DEFAULTS))
            for appimage in (False, True):
                settings.save(path, copy.deepcopy(settings.DEFAULTS))
                root = tk.Tk()
                try:
                    panel = Panel.__new__(Panel)
                    panel.path, panel.root = path, root
                    panel.pages = {'Updates': ttk.Frame(root)}
                    panel.pages['Updates'].pack(fill='both', expand=True)
                    panel.config = settings.load(path)
                    panel.status = tk.StringVar(root)
                    panel.updating = False
                    panel.busy = False
                    with patch('akousousin_app.updates.is_appimage', return_value=appimage):
                        panel.build_updates(); root.update()
                        checks = [w for w in widgets(root) if isinstance(w, ttk.Checkbutton)]
                        self.assertEqual(len(checks), 2)
                        weekly = next(w for w in checks if w.cget('text') == 'Check for updates weekly')
                        weekly.invoke(); root.update()
                        self.assertFalse(settings.load(path)['update_weekly'])
                        beta = next(w for w in checks if w.cget('text') == 'Show beta testing updates')
                        beta.invoke(); root.update()
                        self.assertFalse(settings.load(path)['update_betas'])
                        label = panel.install_update_button.cget('text')
                        self.assertEqual(label, 'Install available update…' if appimage else 'Open update download page…')
                        if not appimage:
                            from akousousin_app import updates
                            candidate = {'version': '99.0.0', 'page': updates.RELEASES + '/tag/v99.0.0'}
                            with patch('akousousin_app.panel.messagebox.askyesno', return_value=True), \
                                    patch('akousousin_app.panel.webbrowser.open') as browser, \
                                    patch('akousousin_app.updates.install') as install:
                                panel.confirm_update(candidate)
                                browser.assert_called_once_with(candidate['page'])
                                install.assert_not_called()
                finally:
                    root.destroy()

    def test_restart_error_has_selectable_text_and_copy_command(self):
        from akousousin_app.dialogs import show_error
        from akousousin_app.speech_dispatcher import RestartError, RESTART_COMMAND
        root = tk.Tk(); self.addCleanup(root.destroy)
        error = RestartError("systemctl: /tmp/.mount_AKS/libcrypto.so.3: version OPENSSL_3.4.0 not found")
        window = show_error(root, error); root.update()
        def widgets(parent):
            for child in parent.winfo_children():
                yield child
                yield from widgets(child)
        children = list(widgets(window))
        field = next(child for child in children if isinstance(child, ttk.Entry))
        self.assertEqual(field.get(), RESTART_COMMAND)
        self.assertEqual(str(field.cget('state')), 'readonly')
        command = next(child for child in children if isinstance(child, ttk.Button) and child.cget('text') == 'Copy command')
        command.invoke(); root.update()
        self.assertEqual(root.clipboard_get(), RESTART_COMMAND)
        summary = next(child for child in children if isinstance(child, tk.Text))
        summary.tag_add('sel', '1.0', '1.12')
        summary.event_generate('<<Copy>>'); root.update()
        self.assertEqual(root.clipboard_get(), summary.get('1.0', '1.12'))
        reveal = next(child for child in children if isinstance(child, ttk.Button) and child.cget('text') == 'Show technical details')
        reveal.invoke(); root.update()
        detail = next(child for child in children if isinstance(child, tk.Text) and 'OPENSSL_3.4.0' in child.get('1.0', 'end'))
        self.assertTrue(detail.winfo_ismapped())
        copy = next(child for child in children if isinstance(child, ttk.Button) and child.cget('text') == 'Copy details')
        copy.invoke(); root.update()
        self.assertIn(error.details, root.clipboard_get())

    def test_first_use_is_explicit_and_progress_uses_real_byte_counts(self):
        from akousousin_app.panel import Panel
        with tempfile.TemporaryDirectory() as folder, patch('akousousin_app.resources.bootstrap', return_value=copy.deepcopy(settings.DEFAULTS)), \
                patch('akousousin_app.catalogue.catalogue', return_value={}), \
                patch('akousousin_app.voice_input.discover_microphones', return_value=[('', 'System default')]), \
                patch('akousousin_app.runtime.call', return_value=None), \
                patch('akousousin_app.resources.download_starter') as download:
            panel = Panel(Path(folder) / 'settings.json'); self.addCleanup(panel.root.destroy)
            panel.root.geometry('760x480'); panel.root.update()
            download.assert_not_called()
            self.assertTrue(panel.starter_card.winfo_ismapped())
            start = next(child for child in panel.starter_card.winfo_children()
                         if isinstance(child, ttk.Button) and 'Download starter voice' in child.cget('text'))
            self.assertLess(start.winfo_rooty() + start.winfo_height(), panel.root.winfo_rooty() + panel.root.winfo_height())
            voice = {'path': str(Path(folder) / 'voice.onnx'), 'sample_rate': 22050,
                     'language': 'en_US', 'name': 'LJSpeech', 'quality': 'medium'}
            download.return_value = dict(copy.deepcopy(settings.DEFAULTS), voices={settings.DEFAULTS['voice']: voice})
            start.invoke()
            deadline = time.monotonic() + 2
            while panel.busy and time.monotonic() < deadline:
                panel.root.update(); time.sleep(.01)
            download.assert_called_once_with(panel.path)
            self.assertFalse(hasattr(panel, 'starter_card'))
            value = {'id': 'test', 'label': 'Voice', 'phase': 'Downloading', 'completed': 25,
                     'total': 100, 'status': 'active'}
            with patch('akousousin_app.download_status.current', return_value=[value]):
                panel.downloads.poll()
                _, label, bar = panel.downloads.rows['test']
                self.assertIn('25%', label.cget('text'))
                self.assertEqual(float(bar.cget('value')), 25)
                self.assertEqual(str(bar.cget('mode')), 'determinate')
                value['total'] = None
                panel.downloads.poll()
                self.assertNotIn('%', label.cget('text'))
                self.assertEqual(str(bar.cget('mode')), 'indeterminate')

    def test_start_button_is_visible_and_starts_a_recording(self):
        with tempfile.TemporaryDirectory() as folder:
            root = tk.Tk(); self.addCleanup(root.destroy)
            root.geometry('1000x680+0+0')
            panel = Mock(root=root, path=Path(folder) / 'settings.json', config=copy.deepcopy(settings.DEFAULTS))
            def card(parent, title):
                frame = ttk.Frame(parent, padding=12)
                frame.pack(fill='x', pady=8)
                ttk.Label(frame, text=title).pack(anchor='w')
                return frame
            panel.card = card
            container = ttk.Frame(root); container.pack(fill='both', expand=True)
            with patch('akousousin_app.voice_input.discover_microphones', return_value=[('', 'System default'), ('mic', 'Built-in microphone')]), patch('akousousin_app.voice_input.runtime.call', return_value=None) as call:
                page = VoiceInput(panel, container)
                page.ensure_model = Mock()
                root.update()
                page.canvas.yview_moveto(1)
                root.update()
                button = page.record_button
                x = button.winfo_rootx() + button.winfo_width() // 2
                y = button.winfo_rooty() + button.winfo_height() // 2
                self.assertIs(root.winfo_containing(x, y), button, 'Start button is obscured or clipped')
                self.assertEqual(button.cget('text'), 'Start recording (10 seconds)')
                button.invoke()
                deadline = time.monotonic() + 2
                while page.busy and time.monotonic() < deadline:
                    root.update(); time.sleep(.01)
                self.assertTrue(any(item.args[1] == {'command': 'stt-start', 'seconds': 10} for item in call.call_args_list))

    def test_device_selection_language_search_and_last_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = tk.Tk(); self.addCleanup(root.destroy)
            root.geometry('1000x680+0+0')
            panel = Mock(root=root, path=Path(folder) / 'settings.json', config=copy.deepcopy(settings.DEFAULTS))
            def card(parent, title):
                frame = ttk.Frame(parent); frame.pack(fill='x'); return frame
            panel.card = card
            container = ttk.Frame(root); container.pack(fill='both', expand=True)
            with patch('akousousin_app.voice_input.discover_microphones', return_value=[('', 'System default'), ('usb-input', 'USB microphone')]), patch('akousousin_app.voice_input.runtime.call', return_value=None):
                page = VoiceInput(panel, container)
                root.update()
                page.apply_sources([('', 'System default'), ('usb-input', 'USB microphone')])
                self.assertEqual(page.source_caption.get(), 'System default')
                page.source_caption.set('USB microphone'); page.select_source()
                self.assertEqual(settings.load(panel.path)['stt_source'], 'usb-input')
                picker = page.language_picker
                picker.open(); root.update()
                self.assertGreater(len(picker.tree.get_children()), 90)
                self.assertLess(picker.tree.yview()[1], 1, 'Language list must scroll')
                picker.search.set('German'); root.update()
                self.assertEqual(picker.tree.get_children(), ('de',))
                picker.choose()
                self.assertEqual(settings.load(panel.path)['stt_language'], 'de')
                picker.open(); picker.search.set('Multilingual'); root.update()
                picker.choose()
                self.assertEqual(page.language.get(), '')
                page.shared({'busy': False, 'state': 'Ready', 'desktop': {'state': 'Disabled'}, 'sequence': 1,
                             'results': [{'text': 'Guten Morgen', 'language': 'de', 'language_source': 'detected', 'output': 'displayed',
                                          'timings': {'recognition_seconds': .67, 'insertion_seconds': .07}}]})
                self.assertIn('German (de)', page.detected_language.get())
                page.result.focus_force(); root.update()
                page.result.event_generate('<Control-a>'); root.update()
                self.assertEqual(page.result.get('sel.first', 'sel.last'), page.result.get('1.0', 'end-1c'))
                before = page.result.get('1.0', 'end-1c')
                page.result.insert('1.0', '888888')
                self.assertEqual(page.result.get('1.0', 'end-1c'), before)
                self.assertEqual(str(page.result.cget('state')), 'disabled')
                page.copy()
                self.assertIn('recognition: 0.67s', root.clipboard_get())
                self.assertIn('insertion: 0.07s', root.clipboard_get())
                self.assertEqual(page.language.get(), '', 'Detection must not silently lock the language')
                with patch('akousousin_backend.recognition.ready_cue') as cue:
                    page.sound_button.invoke()
                    deadline = time.monotonic() + 2
                    while page.sound_testing and time.monotonic() < deadline:
                        root.update(); time.sleep(.01)
                    cue.assert_called_once_with()
                    self.assertIn('Playback completed', page.sound_status.get())


    def test_wheel_routes_only_to_visible_scroll_area(self):
        from akousousin_app.scrolling import ScrollArea
        root = tk.Tk(); self.addCleanup(root.destroy)
        root.geometry('450x300')
        first, second = ScrollArea(root), ScrollArea(root)
        first.pack(fill='both', expand=True)
        labels = []
        for area in (first, second):
            for number in range(50):
                label = ttk.Label(area.inner, text='Row ' + str(number), padding=10)
                label.pack()
                if number == 0:
                    labels.append(label)
        root.update()
        labels[0].event_generate('<MouseWheel>', delta=-120); root.update()
        self.assertGreater(first.canvas.yview()[0], 0)
        before = first.canvas.yview()
        first.pack_forget(); second.pack(fill='both', expand=True); root.update()
        labels[1].event_generate('<MouseWheel>', delta=-120); root.update()
        self.assertGreater(second.canvas.yview()[0], 0)
        self.assertEqual(first.canvas.yview(), before)
        labels[1].event_generate('<MouseWheel>', delta=120); root.update()
        self.assertEqual(second.canvas.yview()[0], 0)

    def test_settings_fit_small_window_and_library_has_scrollbars(self):
        from akousousin_app.panel import Panel
        with tempfile.TemporaryDirectory() as folder, patch('akousousin_app.resources.bootstrap', return_value=copy.deepcopy(settings.DEFAULTS)), patch('akousousin_app.catalogue.catalogue', return_value={}), patch('akousousin_app.voice_input.discover_microphones', return_value=[('', 'System default')]), patch('akousousin_app.runtime.call', return_value=None):
            panel = Panel(Path(folder) / 'settings.json')
            self.addCleanup(panel.root.destroy)
            panel.root.geometry('760x480')
            panel.show('Settings'); panel.root.update()
            scroll = panel.settings_scroll
            self.assertTrue(scroll.scrollbar.winfo_ismapped())
            self.assertLess(scroll.canvas.yview()[1], 1)
            scroll.canvas.yview_moveto(1); panel.root.update()
            def buttons(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Button): yield child
                    yield from buttons(child)
            save = next(button for button in buttons(scroll.inner) if button.cget('text') == 'Save settings')
            self.assertLess(save.winfo_rooty() + save.winfo_height(), panel.root.winfo_rooty() + panel.root.winfo_height())
            panel.show('Voice library'); panel.root.update()
            self.assertTrue(panel.library_scrollbar.winfo_ismapped())
            panel.show('Voice Input'); panel.root.update()
            page = panel.voice_input
            page.shared({'busy': False, 'loaded': True, 'enabled': True, 'state': 'Ready', 'desktop': {'state': 'Disabled'}, 'sequence': 0, 'results': []})
            self.assertEqual(page.model_button.cget('text'), 'Unload recognition model')
            with patch.object(page, 'unload') as unload:
                page.model_button.invoke()
                unload.assert_called_once()

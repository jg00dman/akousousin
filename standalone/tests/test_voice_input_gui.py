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
    def setUp(self):
        self.callback_errors = []
        reporter = patch.object(tk.Tk, 'report_callback_exception', side_effect=lambda *args: self.callback_errors.append(args))
        reporter.start(); self.addCleanup(reporter.stop)
        self.addCleanup(lambda: self.assertEqual(self.callback_errors, [], 'Tk callback errors'))

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
                picker.open(); picker.search.set('Automatic'); root.update()
                picker.choose()
                self.assertEqual(page.language.get(), '')
                page.shared({'busy': False, 'state': 'Ready', 'desktop': {'state': 'Disabled'}, 'sequence': 1,
                             'results': [{'text': 'Guten Morgen', 'language': 'de', 'language_source': 'detected', 'output': 'displayed'}]})
                self.assertIn('German (de)', page.detected_language.get())
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
            labels.append(label)
        root.update()
        labels[0].event_generate('<Button-5>'); root.update()
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
            self.assertEqual(page.model_button.cget('text'), 'Disable voice input')
            with patch.object(page, 'unload') as unload:
                page.model_button.invoke()
                unload.assert_called_once()

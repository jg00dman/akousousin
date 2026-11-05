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

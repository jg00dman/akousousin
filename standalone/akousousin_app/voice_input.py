# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Voice Input model management and diagnostic recording, off the UI thread."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from . import settings, runtime
from .input_choices import LanguagePicker, discover_microphones, language_caption


class VoiceInput:
    def __init__(self, panel, page):
        self.panel = panel
        self.events = queue.Queue()
        self.busy = False
        self.closed = False
        from .scrolling import ScrollArea
        self.scroller = ScrollArea(page)
        self.scroller.pack(fill='both', expand=True)
        self.canvas = self.scroller.canvas
        page = self.scroller.inner
        self.input_enabled = False
        config = panel.config
        self.model = tk.StringVar(value=config.get('stt_model', 'small'))
        self.language = tk.StringVar(value=config.get('stt_language', ''))
        self.source = tk.StringVar(value=config.get('stt_source', ''))
        self.source_caption = tk.StringVar(value='Finding selected microphone…' if self.source.get() else 'System default')
        self.source_options = {'System default': ''}
        self.device_status = tk.StringVar(value='Finding microphones…')
        self.detected_language = tk.StringVar(value='No speech detected yet')
        self.refreshing_sources = False
        self.mode = tk.StringVar(value=config.get('stt_mode', 'toggle'))
        self.local_error = False
        self.shared_polling = False
        self.shared_busy = False
        self.operation_lock = threading.Lock()
        self.action_cancelled = threading.Event()
        self.last_sequence = 0
        self.latest_text = ''
        self.beep = tk.BooleanVar(value=config.get('stt_beep', True))
        self.state = tk.StringVar(value='Voice input is not loaded.')
        frame = panel.card(page, 'Voice input')
        ttk.Label(frame, text='Local Whisper recognition · model downloads are retained between upgrades',
                  style='Card.TLabel').pack(anchor='w')
        from akousousin_backend.recognition import model_root
        ttk.Label(frame, text=str(model_root()), style='Card.TLabel', wraplength=760).pack(anchor='w', pady=8)
        row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=8)
        ttk.Label(row, text='Model', style='Card.TLabel').pack(side='left')
        self.combo = ttk.Combobox(row, textvariable=self.model, values=['small', 'turbo'], state='readonly', width=18)
        self.combo.pack(side='left', padx=12)
        ttk.Label(frame, text='Small: about 485 MB download. Turbo: import a converted local model; download support pending.',
                  style='Card.TLabel', wraplength=760).pack(anchor='w')
        self.buttons = []
        row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=10)
        self.model_button = ttk.Button(row, text='Enable voice input', command=self.toggle_input)
        self.model_button.pack(side='left', padx=3)
        ttk.Button(row, text='Import existing model…', command=self.import_model).pack(side='left', padx=3)
        ttk.Label(frame, text='Enable downloads the model once if needed and loads it. Disable stops dictation and frees model memory; downloaded files stay.',
                  style='Card.TLabel', wraplength=760).pack(anchor='w', pady=5)
        ttk.Label(frame, textvariable=self.state, style='Card.TLabel', wraplength=760).pack(anchor='w', pady=8)
        frame = panel.card(page, 'Desktop dictation — KDE Wayland')
        row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x')
        ttk.Label(row, text='Activation', style='Card.TLabel').pack(side='left')
        mode = ttk.Combobox(row, textvariable=self.mode, values=['toggle', 'push-to-talk'], state='readonly', width=18)
        mode.pack(side='left', padx=10)
        mode.bind('<<ComboboxSelected>>', lambda event: self.save())
        ttk.Button(row, text='Enable desktop shortcuts', command=self.enable_desktop).pack(side='left', padx=3)
        ttk.Button(row, text='Disable', command=lambda: self.command('stt-desktop-disable')).pack(side='left')
        self.desktop_state = tk.StringVar(value='Desktop dictation is disabled')
        ttk.Label(frame, textvariable=self.desktop_state, style='Card.TLabel', wraplength=760).pack(anchor='w', pady=5)
        ttk.Label(frame, text='KDE asks you to approve shortcuts and keyboard input. Default shortcut: Ctrl+Alt+Space. Switching windows holds the transcript instead of inserting it.',
                  style='Card.TLabel', wraplength=760).pack(anchor='w')
        frame = panel.card(page, 'Recording and transcripts')
        ttk.Label(frame, text='Microphone', style='Card.TLabel').pack(anchor='w')
        row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=5)
        self.source_combo = ttk.Combobox(row, textvariable=self.source_caption, values=['System default'], state='readonly', height=12)
        self.source_combo.pack(side='left', fill='x', expand=True)
        self.source_combo.bind('<<ComboboxSelected>>', lambda event: self.select_source())
        ttk.Button(row, text='Refresh', command=self.refresh_sources).pack(side='right', padx=(6, 0))
        ttk.Label(frame, textvariable=self.device_status, style='Card.TLabel', wraplength=760).pack(anchor='w')
        ttk.Label(frame, text='Dictation language', style='Card.TLabel').pack(anchor='w', pady=(6, 0))
        self.language_picker = LanguagePicker(frame, self.language, changed=self.save)
        self.language_picker.pack(fill='x', pady=5)
        ttk.Label(frame, textvariable=self.detected_language, style='Card.TLabel', wraplength=760).pack(anchor='w')
        ttk.Label(frame, text='Selections apply to the next recording.', style='Card.TLabel').pack(anchor='w')
        row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=6)
        ttk.Checkbutton(row, text='Play two short ready tones (300 Hz)', variable=self.beep,
                        command=self.save).pack(side='left')
        self.sound_button = ttk.Button(row, text='Test ready sound', command=self.test_ready_sound)
        self.sound_button.pack(side='left', padx=8)
        self.sound_status = tk.StringVar(value='Sound uses the system default playback device.')
        self.sound_testing = False
        ttk.Label(frame, textvariable=self.sound_status, style='Card.TLabel', wraplength=760).pack(anchor='w')
        row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x')
        self.record_button = ttk.Button(row, text='Start recording (10 seconds)', command=self.record)
        self.record_button.pack(side='left', pady=5)
        self.buttons.append(self.record_button)
        ttk.Button(row, text='Stop recording', command=lambda: self.command('stt-finish')).pack(side='left', padx=5)
        ttk.Button(row, text='Cancel', command=lambda: self.command('stt-cancel')).pack(side='left')
        ttk.Button(row, text='Copy transcript', command=self.copy).pack(side='right')
        ttk.Label(frame, text='The recording test displays text below. The desktop shortcut inserts text into the original window. Wait for the ready tones before speaking.',
                  style='Card.TLabel', wraplength=760).pack(anchor='w')
        self.result = tk.Text(frame, height=4, wrap='word')
        self.result.pack(fill='x', pady=8)
        panel.root.bind('<Destroy>', self.destroy, add='+')
        self.refresh_sources()
        panel.root.after(100, self.poll)

    def select_source(self):
        self.source.set(self.source_options[self.source_caption.get()])
        self.save()

    def refresh_sources(self):
        if self.refreshing_sources:
            return
        self.refreshing_sources = True
        self.device_status.set('Finding microphones…')
        def task():
            try:
                self.events.put(('devices', (discover_microphones(), None)))
            except Exception as error:
                self.events.put(('devices', ([('', 'System default')], str(error))))
        threading.Thread(target=task, daemon=True).start()

    def apply_sources(self, choices, error=None):
        current = self.source.get()
        if current and not any(code == current for code, caption in choices):
            previous = self.source_caption.get()
            caption = previous if previous.startswith('Unavailable — ') else 'Unavailable — ' + (previous if previous not in ('System default', 'Finding selected microphone…') else 'saved microphone')
            choices = [*choices, (current, caption)]
        self.source_options = {caption: code for code, caption in choices}
        self.source_combo.configure(values=list(self.source_options))
        self.source_caption.set(next(caption for code, caption in choices if code == current))
        self.device_status.set(error or ('No microphones found. Check Linux audio settings.' if len(choices) == 1 else ''))
        self.refreshing_sources = False

    def save(self):
        self.panel.config.update(stt_model=self.model.get(), stt_language=self.language.get().strip(),
                                 stt_source=self.source.get().strip(), stt_beep=self.beep.get(), stt_mode=self.mode.get())
        settings.save(self.panel.path, self.panel.config)
        return self.model.get(), self.source.get().strip() or None, self.language.get().strip() or None, self.beep.get()

    def status(self, text):
        self.events.put(('status', text))

    def run(self, task):
        if self.busy:
            return
        self.busy = True
        self.local_error = False
        self.action_cancelled = threading.Event()
        self.combo.configure(state='disabled')
        for button in self.buttons:
            button.configure(state='disabled')
        def work():
            try:
                task()
                self.events.put(('done', None))
            except Exception as error:
                self.events.put(('error', str(error)))
        threading.Thread(target=work, daemon=True).start()

    def ensure_model(self, model, source=None):
        import importlib.util
        if importlib.util.find_spec('faster_whisper') is None:
            raise RuntimeError('Voice input is unavailable in this build. Install a recognition-enabled build.')
        from akousousin_backend import models
        if model == 'turbo' and source is None and not models.installed('turbo'):
            if models.installed('small'):
                return  # The worker reports its fallback explicitly.
            raise RuntimeError('Import Turbo or prepare Small first for fallback.')
        if source is not None or not models.installed(model):
            models.install(model, source=source, progress=self.status)

    def ensure_ready(self, model, source=None):
        self.ensure_model(model, source)
        self.start_command({'command': 'stt-prepare'})

    def toggle_input(self):
        if self.input_enabled or self.busy:
            self.unload()
        else:
            self.prepare()

    def prepare(self):
        self.save()
        self.run(lambda: self.start_command({'command': 'stt-prepare'}))

    def import_model(self):
        model, *_ = self.save()
        folder = filedialog.askdirectory(parent=self.panel.root, title='Choose the model folder containing model.bin')
        if folder:
            self.run(lambda: self.ensure_ready(model, Path(folder)))

    def start_command(self, request):
        # Serialize start/cancel RPCs as well as cancelling pending local setup.
        # Cancel during a slow model import must not start a mic afterwards.
        with self.operation_lock:
            if not self.closed and not self.action_cancelled.is_set():
                return runtime.call(self.panel.path, request)

    def command(self, command):
        if command in ('stt-cancel', 'stt-finish', 'stt-unload', 'stt-desktop-disable'):
            self.action_cancelled.set()
        self.save()
        def task():
            try:
                with self.operation_lock:
                    runtime.call(self.panel.path, {'command': command}, launch=False)
            except Exception as error:
                self.events.put(('control-error', str(error)))
        threading.Thread(target=task, daemon=True).start()

    def unload(self):
        self.command('stt-unload')

    def enable_desktop(self):
        self.save()
        self.run(lambda: self.start_command({'command': 'stt-desktop-enable'}))

    def record(self):
        self.save()
        self.run(lambda: self.start_command({'command': 'stt-start', 'seconds': 10}))

    def test_ready_sound(self):
        if self.shared_busy:
            self.sound_status.set('Stop recording before testing the ready sound.')
            return
        if self.sound_testing:
            return
        self.sound_testing = True
        self.sound_button.configure(state='disabled')
        self.sound_status.set('Playing on the system default output…')
        def play():
            from akousousin_backend.recognition import ready_cue
            try:
                ready_cue()
                message = 'Playback completed. If silent, check the default output and AKS volume in KDE audio settings.'
            except Exception as error:
                message = str(error)
            self.events.put(('sound', message))
        threading.Thread(target=play, daemon=True).start()

    def copy(self):
        if self.latest_text:
            self.panel.root.clipboard_clear()
            self.panel.root.clipboard_append(self.latest_text)

    def shared_poll(self):
        if self.shared_polling:
            return
        self.shared_polling = True
        def task():
            try:
                result = runtime.call(self.panel.path, {'command': 'stt-status'}, launch=False)
                self.events.put(('shared', result))
            except Exception as error:
                if 'Unknown Akousousin command' in str(error):
                    self.events.put(('control-error', 'An older AKS controller is running. Quit AKS from its tray, then relaunch this build.'))
                self.events.put(('shared', None))
            finally:
                self.shared_polling = False
        threading.Thread(target=task, daemon=True).start()

    def shared(self, result):
        if not result:
            return
        self.shared_busy = result['busy']
        self.input_enabled = result.get('enabled', result.get('loaded', False))
        if hasattr(self, 'model_button'):
            self.model_button.configure(text='Disable voice input' if self.input_enabled else 'Enable voice input')
        if not self.local_error and not self.busy:
            self.state.set(result['state'])
        self.desktop_state.set(result['desktop']['state'])
        if result['sequence'] != self.last_sequence:
            self.last_sequence = result['sequence']
            self.latest_text = ' '.join(item['text'] for item in result['results'])
            detected = next((item for item in reversed(result['results'])
                             if item.get('language_source') == 'detected' and item.get('text')), None)
            if detected:
                self.detected_language.set('Last automatically detected: ' +
                    (language_caption(detected['language']) if detected.get('language') else 'mixed or undetermined'))
            self.result.delete('1.0', 'end')
            for item in result['results']:
                self.result.insert('end', item['text'] + '\n[' + (item['language'] or 'unknown') + ' · ' + item['output'] + ']\n')
                if item.get('timings'):
                    names = [('audio_seconds', 'Audio'), ('queue_seconds', 'queued'),
                             ('recognition_seconds', 'recognition'), ('insertion_seconds', 'insertion')]
                    self.result.insert('end', ' · '.join(f"{label}: {item['timings'][key]:.2f}s"
                        for key, label in names if key in item['timings']) + '\n')
                if item.get('error'):
                    self.result.insert('end', item['error'] + '\n')

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'sound':
                    self.sound_status.set(value)
                    self.sound_testing = False
                    self.sound_button.configure(state='normal')
                elif kind == 'devices':
                    self.apply_sources(*value)
                elif kind == 'shared':
                    self.shared(result=value)
                elif kind == 'control-error':
                    self.local_error = True
                    self.state.set(value)
                elif kind == 'status':
                    self.state.set(value)
                elif kind == 'result':
                    self.result.delete('1.0', 'end')
                    self.result.insert('1.0', value['text'] or '(No speech detected)')
                    self.result.insert('end', '\n\nLanguage: ' + (value['language'] or 'none'))
                if kind in ('done', 'error'):
                    if kind == 'error':
                        self.local_error = True
                        self.state.set('Voice input: ' + value)
                    self.busy = False
                    self.combo.configure(state='readonly')
                    for button in self.buttons:
                        button.configure(state='normal')
        except queue.Empty:
            pass
        self.shared_poll()
        self.panel.root.after(350, self.poll)

    def destroy(self, event):
        if event.widget is self.panel.root:
            self.closed = True
            # Closing the panel does not stop controller-owned dictation.

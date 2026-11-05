"""Voice Input model management and diagnostic recording, off the UI thread."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from . import settings, runtime


class VoiceInput:
    def __init__(self, panel, page):
        self.panel = panel
        self.events = queue.Queue()
        self.busy = False
        self.closed = False
        canvas = tk.Canvas(page, highlightthickness=0, bg='#f4f5f3')
        scrollbar = ttk.Scrollbar(page, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        inner = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        page = inner
        config = panel.config
        self.model = tk.StringVar(value=config.get('stt_model', 'small'))
        self.language = tk.StringVar(value=config.get('stt_language', ''))
        self.source = tk.StringVar(value=config.get('stt_source', ''))
        self.mode = tk.StringVar(value=config.get('stt_mode', 'toggle'))
        self.local_error = False
        self.shared_polling = False
        self.shared_busy = False
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
        for text, function in [('Enable / prepare model', self.prepare), ('Import existing model…', self.import_model),
                               ('Unload model', self.unload)]:
            button = ttk.Button(row, text=text, command=function)
            button.pack(side='left', padx=3); self.buttons.append(button)
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
        for caption, variable in [('Microphone source (blank = system default)', self.source),
                                  ('Language tag (blank = automatic detection)', self.language)]:
            ttk.Label(frame, text=caption, style='Card.TLabel').pack(anchor='w')
            ttk.Entry(frame, textvariable=variable).pack(fill='x', pady=5)
        ttk.Checkbutton(frame, text='Play two short ready tones (250 Hz)', variable=self.beep).pack(anchor='w', pady=6)
        button = ttk.Button(frame, text='Record 10 seconds', command=self.record)
        row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x')
        button.pack(in_=row, side='left', pady=5); self.buttons.append(button)
        ttk.Button(row, text='Stop recording', command=lambda: self.command('stt-finish')).pack(side='left', padx=5)
        ttk.Button(row, text='Cancel', command=lambda: self.command('stt-cancel')).pack(side='left')
        ttk.Button(row, text='Copy transcript', command=self.copy).pack(side='right')
        ttk.Label(frame, text='The recording test displays text below. The desktop shortcut inserts text into the original window. Wait for the ready tones before speaking.',
                  style='Card.TLabel', wraplength=760).pack(anchor='w')
        self.result = tk.Text(frame, height=4, wrap='word')
        self.result.pack(fill='x', pady=8)
        panel.root.bind('<Destroy>', self.destroy, add='+')
        panel.root.after(100, self.poll)

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
        if not self.closed:
            runtime.call(self.panel.path, {'command': 'stt-prepare'})

    def prepare(self):
        model, *_ = self.save()
        self.run(lambda: self.ensure_ready(model))

    def import_model(self):
        model, *_ = self.save()
        folder = filedialog.askdirectory(parent=self.panel.root, title='Choose the model folder containing model.bin')
        if folder:
            self.run(lambda: self.ensure_ready(model, Path(folder)))

    def command(self, command):
        self.save()
        def task():
            try:
                runtime.call(self.panel.path, {'command': command}, launch=False)
            except Exception as error:
                self.events.put(('control-error', str(error)))
        threading.Thread(target=task, daemon=True).start()

    def unload(self):
        self.command('stt-unload')

    def enable_desktop(self):
        model, *_ = self.save()
        def task():
            self.ensure_model(model)
            runtime.call(self.panel.path, {'command': 'stt-desktop-enable'})
        self.run(task)

    def record(self):
        model, *_ = self.save()
        def task():
            self.ensure_model(model)
            if not self.closed:
                runtime.call(self.panel.path, {'command': 'stt-start', 'seconds': 10})
        self.run(task)

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
        if not self.local_error:
            self.state.set(result['state'])
        self.desktop_state.set(result['desktop']['state'])
        if result['sequence'] != self.last_sequence:
            self.last_sequence = result['sequence']
            self.latest_text = ' '.join(item['text'] for item in result['results'])
            self.result.delete('1.0', 'end')
            for item in result['results']:
                self.result.insert('end', item['text'] + '\n[' + (item['language'] or 'unknown') + ' · ' + item['output'] + ']\n')
                if item.get('error'):
                    self.result.insert('end', item['error'] + '\n')

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'shared':
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

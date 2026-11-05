"""Voice Input model management and diagnostic recording, off the UI thread."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from . import settings


class VoiceInput:
    def __init__(self, panel, page):
        self.panel = panel
        self.events = queue.Queue()
        self.recognizer = None
        self.busy = False
        self.closed = False
        config = panel.config
        self.model = tk.StringVar(value=config.get('stt_model', 'small'))
        self.language = tk.StringVar(value=config.get('stt_language', ''))
        self.source = tk.StringVar(value=config.get('stt_source', ''))
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
        frame = panel.card(page, 'Recording test')
        for caption, variable in [('Microphone source (blank = system default)', self.source),
                                  ('Language tag (blank = automatic detection)', self.language)]:
            ttk.Label(frame, text=caption, style='Card.TLabel').pack(anchor='w')
            ttk.Entry(frame, textvariable=variable).pack(fill='x', pady=5)
        ttk.Checkbutton(frame, text='Play two short ready tones (250 Hz)', variable=self.beep).pack(anchor='w', pady=6)
        button = ttk.Button(frame, text='Record 10 seconds', command=self.record)
        button.pack(anchor='w', pady=8); self.buttons.append(button)
        ttk.Label(frame, text='Wait for “Listening — speak now”. Text appears below; this test does not type into applications.',
                  style='Card.TLabel', wraplength=760).pack(anchor='w')
        self.result = tk.Text(frame, height=6, wrap='word')
        self.result.pack(fill='x', pady=8)
        panel.root.bind('<Destroy>', self.destroy, add='+')
        panel.root.after(100, self.poll)

    def save(self):
        self.panel.config.update(stt_model=self.model.get(), stt_language=self.language.get().strip(),
                                 stt_source=self.source.get().strip(), stt_beep=self.beep.get())
        settings.save(self.panel.path, self.panel.config)
        return self.model.get(), self.source.get().strip() or None, self.language.get().strip() or None, self.beep.get()

    def status(self, text):
        self.events.put(('status', text))

    def run(self, task):
        if self.busy:
            return
        self.busy = True
        self.combo.configure(state='disabled')
        for button in self.buttons:
            button.configure(state='disabled')
        def work():
            try:
                task()
                self.events.put(('done', None))
            except Exception as error:
                self.events.put(('error', str(error)))
            finally:
                if self.closed and self.recognizer:
                    self.recognizer.close()
        threading.Thread(target=work, daemon=True).start()

    def ensure_ready(self, model, source=None):
        import importlib.util
        if importlib.util.find_spec('faster_whisper') is None:
            raise RuntimeError('Voice input is unavailable in this build. Install a recognition-enabled build.')
        from akousousin_backend import models
        from akousousin_backend.recognition import Recognizer
        if source is not None or not models.installed(model):
            models.install(model, source=source, progress=self.status)
        if self.closed:
            return
        if self.recognizer is None or self.recognizer.model['model'] != model:
            if self.recognizer:
                self.recognizer.close()
            self.recognizer = Recognizer(model=model)
        if self.recognizer.process is None or not self.recognizer.process.is_alive():
            self.status('Loading model…')
            self.recognizer.start()
        self.status('Ready — ' + self.recognizer.status['model'].title() + ' loaded. Start a recording test.')

    def prepare(self):
        model, *_ = self.save()
        self.run(lambda: self.ensure_ready(model))

    def import_model(self):
        model, *_ = self.save()
        folder = filedialog.askdirectory(parent=self.panel.root, title='Choose the model folder containing model.bin')
        if folder:
            self.run(lambda: self.ensure_ready(model, Path(folder)))

    def unload(self):
        def task():
            if self.recognizer:
                self.recognizer.close()
            self.recognizer = None
            self.status('Model unloaded. Downloaded files retained.')
        self.run(task)

    def record(self):
        model, source, language, beep = self.save()
        def task():
            from akousousin_backend.recognition import capture, ready_cue
            self.ensure_ready(model)
            if self.closed:
                return
            self.status('Opening microphone…')
            audio = capture(10, source, cue=ready_cue if beep else None,
                            on_ready=lambda: self.status('Listening — speak now (10 seconds)'))
            self.status('Transcribing…')
            result = self.recognizer.transcribe(audio, language)
            self.events.put(('result', result))
            self.status('Ready — model stays loaded for the next recording.')
        self.run(task)

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'status':
                    self.state.set(value)
                elif kind == 'result':
                    self.result.delete('1.0', 'end')
                    self.result.insert('1.0', value['text'] or '(No speech detected)')
                    self.result.insert('end', '\n\nLanguage: ' + (value['language'] or 'none'))
                if kind in ('done', 'error'):
                    if kind == 'error':
                        self.state.set('Voice input: ' + value)
                    self.busy = False
                    self.combo.configure(state='readonly')
                    for button in self.buttons:
                        button.configure(state='normal')
        except queue.Empty:
            pass
        self.panel.root.after(100, self.poll)

    def destroy(self, event):
        if event.widget is self.panel.root:
            self.closed = True
            if not self.busy and self.recognizer:
                self.recognizer.close()

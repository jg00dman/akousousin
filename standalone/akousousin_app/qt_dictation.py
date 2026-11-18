# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
from pathlib import Path
import importlib.util
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCompleter, QFileDialog, QPlainTextEdit

from . import runtime
from .input_choices import discover_microphones, language_choices
from .qt_widgets import actions, check, choices, field, group, label, number, tr


class Dictation:
    def __init__(self, panel, layout):
        self.panel = panel
        cfg = panel.config
        self.supported = os.name != 'nt' and importlib.util.find_spec('faster_whisper') is not None
        self.sequence = -1
        self.test_since = None
        form = group(layout, "Recognition")
        self.state = label()
        form.addRow(self.state)
        self.model = choices(form, "Whisper model", [(v, v) for v in ('base', 'base.en', 'small', 'small.en', 'turbo')], cfg['stt_model'])
        self.lang = choices(form, "Dictation language", language_choices(), cfg['stt_language'])
        self.lang.setEditable(True)
        self.lang.setInsertPolicy(type(self.lang).InsertPolicy.NoInsert)
        self.lang.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.lang.completer().setFilterMode(Qt.MatchContains)
        self.lang.completer().setCaseSensitivity(Qt.CaseInsensitive)
        self.mic = choices(form, "Microphone", [('', tr("System default"))], cfg['stt_source'])
        actions(form, ("Refresh microphones", self.refresh_mics), ("Import model folder…", self.import_model))
        actions(form, ("Prepare or download model", lambda: self.command('stt-prepare')), ("Unload model", lambda: self.command('stt-unload')))
        self.beep = check(form, "Play a ready sound", cfg['stt_beep'])
        actions(form, ("Test ready sound", self.sound), ("Recognition options…", self.options))
        form = group(layout, "Recording")
        actions(form, ("Start recording test", panel.start_test), ("Finish recording", lambda: self.command('stt-finish')),
                ("Cancel recording", lambda: self.command('stt-cancel')))
        self.history = field(form, "Recent transcripts", QPlainTextEdit())
        self.history.setReadOnly(True)
        actions(form, ("Copy transcript", self.copy), ("Recognition details…", self.details))
        self.results = []
        self.recording = False
        for box in (self.lang, self.model, self.mic):
            box.activated.connect(self.save)
        self.beep.clicked.connect(self.save)

    def save(self, *_):
        model = self.model.currentData()
        lang = self.lang.currentData()
        if model.endswith('.en') and lang != 'en':
            model = model[:-3]
            self.model.setCurrentIndex(self.model.findData(model))
        self.panel.save(stt_model=model, stt_language=lang, stt_source=self.mic.currentData(), stt_beep=self.beep.isChecked())

    def options(self):
        cfg = self.panel.config
        dialog, form = self.panel.dialog(tr("Recognition options"))
        threads = number(form, "CPU threads", 1, max(64, cfg['stt_cpu_threads']), cfg['stt_cpu_threads'])
        keep = check(form, "Keep model loaded", cfg['stt_keep_loaded'])
        idle = number(form, "Unload after idle seconds (0 means never)", 0, 86400, cfg['stt_idle_timeout'])
        if self.panel.accept(dialog, form):
            self.panel.save(stt_cpu_threads=threads.value(), stt_keep_loaded=keep.isChecked(), stt_idle_timeout=idle.value())

    def refresh_mics(self):
        def apply(values):
            current = self.mic.currentData()
            self.mic.clear()
            for code, caption in values:
                self.mic.addItem(caption, code)
            if self.mic.findData(current) < 0:
                self.mic.addItem(tr("Unavailable microphone: {name}").format(name=current), current)
            self.mic.setCurrentIndex(self.mic.findData(current))
            self.panel.summary()
        self.panel.run(discover_microphones, apply, background=True, failed=lambda e: self.panel.notice(str(e)))

    def sound(self):
        from akousousin_backend.recognition import ready_cue
        if self.recording:
            self.panel.notice(tr("Finish recording before testing the ready sound."))
            return
        self.panel.run(ready_cue, lambda _: self.panel.notice(tr("Ready sound played.")))

    def command(self, name, **options):
        if name in ('stt-cancel', 'stt-unload', 'stt-finish'):
            self.panel.input_cancel.set()
        self.panel.rpc(name, **options)

    def import_model(self):
        folder = QFileDialog.getExistingDirectory(self.panel, tr("Choose the folder containing model.bin"))
        if folder:
            from akousousin_backend import models
            model = self.model.currentData()
            self.panel.input_cancel.clear()
            def install():
                models.install(model, source=Path(folder))
                if not self.panel.input_cancel.is_set():
                    return runtime.call(self.panel.path, {'command': 'stt-prepare'})
            self.panel.run(install)

    def update(self, status):
        state = status.get('state', tr("Dictation is idle"))
        self.recording = status.get('busy', False)
        if not self.supported:
            state = tr("Local dictation requires a recognition-enabled Linux build.")
        self.state.setText(state)
        self.panel.input_state.setText(state)
        self.panel.dict_shortcuts.setText(status.get('desktop', {}).get('state', tr("Disabled")))
        if self.sequence == status.get('sequence', 0):
            return
        self.sequence = status.get('sequence', 0)
        self.results = status.get('results', [])
        self.history.setPlainText('\n\n'.join(item['text'] for item in self.results))
        if self.test_since is not None:
            self.panel.test_result.setPlainText('\n'.join(item['text'] for item in self.results
                if item.get('sequence', 0) > self.test_since and item.get('output') == 'displayed'))

    def details(self):
        import json
        self.panel.document(tr("Recognition details"), json.dumps(self.results, ensure_ascii=False, indent=2))

    def copy(self):
        selection = self.history.textCursor().selectedText().replace('\u2029', '\n')
        if selection or self.results:
            QApplication.clipboard().setText(selection or self.results[-1]['text'])

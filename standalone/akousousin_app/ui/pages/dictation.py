# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Dictation: how to start, what to listen to, speed against accuracy, and a test."""
import json
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QCheckBox, QFileDialog, QPlainTextEdit, QWidget

from ...input_choices import discover_microphones, language_choices
from ..flow import Columns
from ..lang import dictation_state, keys, language_name
from ..widgets import Card, Choices, Keys, button, combo, fill, labelled, row, set_icon, spread, text
from .base import Page

SIZES = {'base': '145 MB', 'base.en': '145 MB', 'small': '480 MB', 'small.en': '480 MB', 'turbo': '1.6 GB'}


class DictationPage(Page):
    key = 'dictation'
    icon = 'mic'

    def title(self):
        return self.tr('Dictation')

    def subtitle(self):
        return self.tr('Speak into any app. Recognition runs on this computer.')

    def build(self):
        test = self.state.dictation_test
        config = self.state.config

        # Start dictating
        start = Card(self.tr('Start dictating'))
        self.shortcut_keys = Keys()
        self.shortcut_none = text(self.tr('No shortcut yet'), 'muted', wrap=False)
        self.enable = button(self.tr('Set up shortcut…'), lambda: self.state.command('stt-desktop-enable', key='shortcut'))
        self.disable = button(self.tr('Turn off'), lambda: self.state.command('stt-desktop-disable', key='shortcut'))
        caption = text(self.tr('Shortcut'), 'h3', wrap=False)
        start.add(row(caption, self.shortcut_keys, self.shortcut_none, self.enable, self.disable, spacing=14))
        self.mode = Choices([('push-to-talk', self.tr('Hold to talk'), self.tr('Speak while holding the keys')),
                             ('toggle', self.tr('Press to start and stop'), self.tr('Press once to begin, again to finish'))],
                            config['stt_mode'], self.tr('How the shortcut works'))
        self.mode.chosen.connect(lambda mode: self.state.save(stt_mode=mode))
        start.add(self.mode)
        self.desktop_detail = text('', 'small')
        start.add(self.desktop_detail)

        # Listening
        listen = Card(self.tr('Listening'))
        self.language = combo()
        self.language.activated.connect(lambda _: self.save_language())
        self.mic = combo([('', self.tr('System default'))], config['stt_source'])
        self.mic.activated.connect(lambda _: self.state.save(stt_source=self.mic.currentData()))
        refresh = button(self.tr('Refresh'), lambda: self.refresh_mics())
        mic_box = labelled(self.tr('Microphone'), self.mic)
        mic_box.addLayout(row(refresh))
        fields = Columns([[self._box(labelled(self.tr('Language'), self.language,
                                              self.tr('Starts with your system language. Automatic detects it each time.')))],
                          [self._box(mic_box)]], minimum=240)
        listen.add(fields)
        self.beep = QCheckBox(self.tr('Play a short sound when ready to listen'))
        self.beep.setChecked(config['stt_beep'])
        self.beep.toggled.connect(lambda on: self.state.save(stt_beep=on))
        listen.add(row(self.beep, button(self.tr('Test sound'), self.test_sound)))

        # Test
        trial = Card()
        trial.add(spread(text(self.tr('Try it'), 'h2'),
                         button(self.tr('Copy'), self.copy, icon='copy', accessible=self.tr('Copy transcript'))))
        self.record = button('', test.toggle, kind='round', icon='mic', accessible=self.tr('Start test recording'))
        self.transcript = QPlainTextEdit()
        self.transcript.setObjectName('transcript')
        self.transcript.setReadOnly(True)
        self.transcript.setMinimumHeight(90)
        self.transcript.setMaximumHeight(150)
        self.transcript.setAccessibleName(self.tr('Test transcript'))
        self.transcript.setPlaceholderText(self.tr('Press the microphone and say a sentence. What you said appears here; nothing is typed into other apps.'))
        trial.add(row(self.record, self.transcript, spacing=18, stretch=False))
        self.state_line = text('', 'muted')
        trial.add(row(self.state_line, button(self.tr('Recognition details…'), self.details, kind='link')))

        # Speed and accuracy
        model = Card(self.tr('Speed and accuracy'))
        self.model = Choices([('fast', self.tr('Fastest'), ''), ('balanced', self.tr('Balanced'), ''),
                              ('accurate', self.tr('Most accurate'), '')], None, self.tr('Speed and accuracy'))
        self.model.chosen.connect(self.choose_model)
        model.add(self.model)
        self.model_note = text('', 'small')
        model.add(self.model_note)
        self.get_model = button('', self.download_model, kind='primary', icon='download')
        model.add(row(self.get_model, button(self.tr('Import a model folder…'), self.import_model),
                      button(self.tr('Free memory now'), lambda: self.state.command('stt-unload'))))

        self.add(Columns([[start, listen], [trial, model]], minimum=420))
        test.changed.connect(self.recording_changed)
        test.transcript.connect(self.transcript.setPlainText)
        self.settings_changed(config)
        self.status_changed(self.state.status)
        if not self.state.windows:
            QTimer.singleShot(150, lambda: self.refresh_mics(quiet=True))

    @staticmethod
    def _box(layout):
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    # Models -----------------------------------------------------------------
    def tiers(self, language):
        english = language == 'en'
        return {'fast': 'base.en' if english else 'base', 'balanced': 'small.en' if english else 'small', 'accurate': 'turbo'}

    @staticmethod
    def installed(model):
        try:
            from akousousin_backend import models
            return models.installed(model)
        except ImportError:
            return False

    def choose_model(self, tier):
        self.state.save(stt_model=self.tiers(self.state.config['stt_language'])[tier])

    def save_language(self):
        language = self.language.currentData()
        model = self.state.config['stt_model']
        if model.endswith('.en') and language != 'en':
            model = model[:-3]
        elif language == 'en' and model in ('base', 'small'):
            model += '.en'
        self.state.save(stt_language=language, stt_model=model)

    def download_model(self):
        if self.state.config['stt_model'] == 'turbo':
            self.import_model()
            return
        self.state.command('stt-prepare', key='model', download=True)
        self.notice(self.tr('Downloading the dictation model. This can take a few minutes.'))

    def import_model(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr('Choose the folder containing model.bin'))
        if not folder:
            return
        model = self.state.config['stt_model']

        def install():
            from akousousin_backend import models
            models.install(model, source=Path(folder))
            return self.state.call('stt-prepare')

        self.run(install, lambda _: (self.settings_changed(self.state.config), self.notice(self.tr('Model imported.'))),
                 key='model', busy=self.tr('Importing the model…'))

    # Updates ----------------------------------------------------------------
    def settings_changed(self, config):
        fill(self.language, [(code, language_name(code) if code else self.tr('Detect automatically'))
                             for code, _caption in language_choices()], config['stt_language'])
        self.mode.select(config['stt_mode'])
        tiers = self.tiers(config['stt_language'])
        for tier, model in tiers.items():
            state = self.tr('Downloaded') if self.installed(model) else (
                self.tr('Import only') if model == 'turbo' else self.tr('Download'))
            self.model.items[tier].set_detail(f"Whisper {model.replace('.en', '').title()} · {SIZES[model]} · {state}")
        current = next((tier for tier, model in tiers.items() if model == config['stt_model']), None)
        self.model.select(current)
        model = config['stt_model']
        missing = not self.installed(model)
        self.get_model.setVisible(missing)
        self.get_model.setText(self.tr('Import model…') if model == 'turbo' else
                               self.tr('Download · %1').replace('%1', SIZES[model]))
        self.model_note.setText(self.tr('Faster settings suit older computers. Models download only when you choose Download.'))
        self.beep.blockSignals(True)
        self.beep.setChecked(config['stt_beep'])
        self.beep.blockSignals(False)

    def status_changed(self, status):
        dictation = status.dictation or {}
        sentence, _tone = dictation_state(dictation, self.state.dictation_test.supported)
        detail = dictation.get('state', '')
        self.state_line.setText(sentence + (f' — {detail}' if detail and detail != sentence else ''))
        desktop = dictation.get('desktop') or {}
        found = keys(desktop.get('keys', ''))
        enabled = bool(desktop.get('enabled'))
        self.shortcut_keys.set(found if enabled else [])
        self.shortcut_none.setVisible(not (enabled and found))
        self.enable.setVisible(not enabled)
        self.disable.setVisible(enabled)
        self.desktop_detail.setText('' if enabled else desktop.get('state', ''))
        self.desktop_detail.setVisible(not enabled and bool(desktop.get('state')))

    def recording_changed(self, recording):
        set_icon(self.record, 'stop' if recording else 'mic', 'round')
        self.record.setAccessibleName(self.tr('Finish test recording') if recording else self.tr('Start test recording'))

    # Actions ----------------------------------------------------------------
    def refresh_mics(self, quiet=False):
        def apply(values):
            fill(self.mic, values, self.state.config['stt_source'])
            if self.mic.findData(self.state.config['stt_source']) < 0:
                self.mic.addItem(self.tr('Unavailable microphone'), self.state.config['stt_source'])

        def failed(_error):
            if not quiet:
                self.notice(self.tr('Could not list microphones. Check that PipeWire or PulseAudio is running, then choose Refresh.'))

        self.tasks.run(discover_microphones, apply, failed=failed, background=True)

    def test_sound(self):
        if self.state.dictation_test.recording:
            self.notice(self.tr('Finish the test before playing the sound.'))
            return
        from akousousin_backend.recognition import ready_cue
        self.run(ready_cue, lambda _: self.notice(self.tr('Ready sound played.')), key='sound')

    def copy(self):
        words = self.transcript.toPlainText()
        if words:
            QApplication.clipboard().setText(words)
            self.notice(self.tr('Transcript copied.'))

    def details(self):
        from .. import dialogs
        results = (self.state.status.dictation or {}).get('results', [])
        dialogs.document(self, self.tr('Recognition details'), json.dumps(results, ensure_ascii=False, indent=2))

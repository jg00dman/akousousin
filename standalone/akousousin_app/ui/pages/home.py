# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Home: is everything ready, and a place to try reading and dictation."""
import os
from pathlib import Path

from PySide6.QtWidgets import QFrame, QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

from ... import resources
from .. import theme
from ..flow import Columns
from ..lang import dictation_state, keys, language_name, number, speech_state
from ..widgets import Card, Keys, StatusLine, button, row, set_icon, text
from .base import Page


class HomePage(Page):
    key = 'home'
    icon = 'home'

    def title(self):
        return self.tr('Home')

    def build(self):
        self.summary = text('', 'muted')
        self.layout_.insertWidget(1, self.summary)
        preview, test = self.state.preview, self.state.dictation_test

        # Status cards
        self.read_card = Card(self.tr('Reading aloud'), icon='voices')
        self.read_status = StatusLine()
        self.read_card.add(self.read_status)
        self.read_keys = Keys()
        self.read_hint = text(self.tr('Select text anywhere and press'), 'muted')
        self.read_card.add(row(self.read_hint, self.read_keys, spacing=8))
        self.dict_card = Card(self.tr('Dictation'), icon='mic')
        self.dict_status = StatusLine()
        self.dict_card.add(self.dict_status)
        self.dict_keys = Keys()
        self.dict_hint = text('', 'muted')
        self.dict_card.add(row(self.dict_hint, self.dict_keys, spacing=8))
        self.add(Columns([[self.read_card], [self.dict_card]], minimum=300))

        # Try it
        card = Card(self.tr('Try it'))
        speak_side = QVBoxLayout()
        speak_side.setSpacing(10)
        self.sample = QPlainTextEdit(self.tr('The quick brown fox jumps over the lazy dog.'))
        self.sample.setMaximumHeight(96)
        self.sample.setTabChangesFocus(True)
        caption = text(self.tr('Text to read'), 'small')
        caption.setBuddy(self.sample)
        self.sample.setAccessibleName(self.tr('Text to read'))
        speak_side.addWidget(caption)
        speak_side.addWidget(self.sample)
        self.speak = button(self.tr('Speak'), self.speak_sample, kind='primary', icon='play')
        self.voice_name = text('', 'muted', wrap=False)
        self.change_voice = button(self.tr('Change voice'), lambda: self.state.navigate.emit('voices'), kind='link')
        self.starter = button(self.tr('Download a starter voice (64 MB)'), self.download_starter, icon='download')
        speak_side.addLayout(row(self.speak, self.voice_name, self.change_voice, self.starter))
        test_side = QVBoxLayout()
        test_side.setSpacing(10)
        self.transcript = QPlainTextEdit()
        self.transcript.setObjectName('transcript')
        self.transcript.setReadOnly(True)
        self.transcript.setMaximumHeight(96)
        self.transcript.setPlaceholderText(self.tr('Your words appear here as you speak.'))
        transcript_caption = text(self.tr('Test transcript'), 'small')
        transcript_caption.setBuddy(self.transcript)
        self.transcript.setAccessibleName(self.tr('Test transcript'))
        test_side.addWidget(transcript_caption)
        test_side.addWidget(self.transcript)
        self.test = button(self.tr('Test dictation'), test.toggle, icon='mic')
        self.listening = text(self.tr('Listening…'), 'ok', wrap=False)
        self.listening.hide()
        test_side.addLayout(row(self.test, self.listening))
        card.add(Columns([[self._box(speak_side)], [self._box(test_side)]], spacing=24, minimum=300))
        self.add(card)

        # Connected apps
        apps = Card()
        heading = text(self.tr('Connected apps'), 'h2')
        apps.add(row(heading, button(self.tr('Manage apps'), lambda: self.state.navigate.emit('apps'), kind='link')))
        self.apps_row = QHBoxLayout()
        self.apps_row.setSpacing(12)
        apps.add(self.apps_row)
        self.add(apps)

        shield = text()
        shield.setPixmap(theme.pixmap('shield', 16, theme.current().ok))
        self.add(row(shield, text(self.tr('Your text and voice are always processed on this computer.'), 'muted'),
                     button(self.tr('About privacy'), lambda: self.state.navigate.emit('privacy'), kind='link'), spacing=8))

        preview.changed.connect(self.preview_changed)
        test.changed.connect(self.test_changed)
        test.transcript.connect(self.transcript.setPlainText)
        self.settings_changed(self.state.config)
        self.status_changed(self.state.status)

    @staticmethod
    def _box(layout):
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    # Updates ------------------------------------------------------------
    def settings_changed(self, config):
        voice = config['voices'].get(config['voice'])
        self.speak.setEnabled(bool(voice))
        self.starter.setVisible(not voice)
        self.change_voice.setVisible(bool(voice))
        self.voice_name.setText(f"{voice['name']} · {language_name(voice['language'])}" if voice else '')
        self.refresh_apps(config)
        self.status_changed(self.state.status)

    def status_changed(self, status):
        config = self.state.config
        voice = config['voices'].get(config['voice'])
        sentence, tone = speech_state(status.speech, bool(voice))
        if voice:
            sentence = ' · '.join((sentence, voice['name'], language_name(voice['language']),
                                   self.tr('%1×').replace('%1', number(config['speed']))))
        self.read_status.set(sentence, tone)
        reading = status.reading
        read_keys = keys((reading.get('keys') or {}).get('read-selection', ''))
        if reading.get('reading'):
            self.read_hint.setText(self.tr('Reading — press the same keys again to stop'))
        elif reading.get('shortcuts_enabled') and read_keys:
            self.read_hint.setText(self.tr('Select text anywhere and press'))
        else:
            self.read_hint.setText(self.tr('Turn on the reading shortcut in Shortcuts'))
            read_keys = []
        self.read_keys.set(read_keys)

        test = self.state.dictation_test
        dictation = status.dictation or {}
        sentence, tone = dictation_state(dictation, test.supported)
        if test.supported and dictation:
            mic = self.state.config.get('stt_source') or ''
            sentence = ' · '.join((sentence, language_name(config['stt_language']),
                                   self.tr('Default microphone') if not mic else self.tr('Chosen microphone')))
        self.dict_status.set(sentence, tone)
        desktop = dictation.get('desktop') or {}
        dict_keys = keys(desktop.get('keys', ''))
        if desktop.get('enabled') and dict_keys:
            hold = config.get('stt_mode') == 'push-to-talk'
            self.dict_hint.setText(self.tr('Hold these keys and speak') if hold else self.tr('Press these keys and speak'))
        else:
            self.dict_hint.setText(self.tr('Turn on the dictation shortcut in Shortcuts'))
            dict_keys = []
        self.dict_keys.set(dict_keys)

        if not voice:
            self.summary.setText(self.tr('Choose a voice to start reading aloud.'))
        elif tone == 'danger':
            self.summary.setText(self.tr('Dictation needs your attention.'))
        else:
            self.summary.setText(self.tr('Everything is ready. Nothing needs your attention.'))

    def refresh_apps(self, config):
        while self.apps_row.count():
            item = self.apps_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        chips = []
        for entry in config.get('registrations', []):
            prefix = entry.get('prefix') or ''
            name = Path(prefix).name if prefix else self.tr('Windows apps')
            chips.append((name, self.tr('Wine prefix · Voices registered') if prefix else self.tr('Voices registered')))
        if os.name != 'nt':
            from ...speech_dispatcher import dispatcher_paths
            if dispatcher_paths()[1].exists():
                chips.append((self.tr('Linux apps and Orca'), self.tr('Speech Dispatcher · On')))
        for name, detail in chips:
            chip = QFrame()
            chip.setObjectName('choice')
            layout = QHBoxLayout(chip)
            layout.setContentsMargins(12, 10, 14, 10)
            image = text()
            image.setPixmap(theme.pixmap('check', 20, theme.current().ok))
            words = QVBoxLayout()
            words.setSpacing(0)
            words.addWidget(text(name, 'h3', wrap=False))
            words.addWidget(text(detail, 'small', wrap=False))
            layout.addWidget(image)
            layout.addLayout(words)
            chip.setAccessibleName(f'{name}, {detail}')
            self.apps_row.addWidget(chip)
        if not chips:
            self.apps_row.addWidget(text(self.tr('Not connected to any apps yet. Add Logos or another Windows app in Apps.'), 'muted'))
        self.apps_row.addStretch(1)

    # Actions -------------------------------------------------------------
    def speak_sample(self):
        self.state.preview.toggle(self.state.config['voice'], self.sample.toPlainText(), failed=self.error)

    def preview_changed(self, playing):
        self.speak.setText(self.tr('Stop') if playing else self.tr('Speak'))
        set_icon(self.speak, 'stop' if playing else 'play', 'primary')

    def test_changed(self, recording):
        self.test.setText(self.tr('Finish') if recording else self.tr('Test dictation'))
        set_icon(self.test, 'stop' if recording else 'mic')
        self.listening.setVisible(recording)

    def download_starter(self):
        self.run(lambda: resources.download_starter(self.state.path), lambda _: self.state.reload(),
                 key='download', busy=self.tr('Downloading the starter voice…'))

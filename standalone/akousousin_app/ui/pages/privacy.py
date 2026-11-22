# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Privacy: what always stays on this computer, and the few uses of the internet."""
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QVBoxLayout, QWidget

from .. import theme
from ..widgets import Card, SettingRow, text
from .base import Page


def point(icon, title, explanation):
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(14)
    image = text()
    image.setPixmap(theme.pixmap(icon, 22, theme.current().ok))
    layout.addWidget(image, 0)
    words = QVBoxLayout()
    words.setSpacing(2)
    words.addWidget(text(title, 'h3'))
    words.addWidget(text(explanation, 'muted'))
    layout.addLayout(words, 1)
    widget.setAccessibleName(title)
    widget.setAccessibleDescription(explanation)
    return widget


class PrivacyPage(Page):
    key = 'privacy'
    icon = 'shield'

    def title(self):
        return self.tr('Privacy')

    def subtitle(self):
        return self.tr('Akousousin works on this computer. Here is exactly what stays here, and the few times it uses the internet.')

    def build(self):
        always = Card(self.tr('Always on this computer'))
        always.add(point('voices', self.tr('Text you hear read aloud'),
                         self.tr('Speech is made by the voices installed here. The text is never sent anywhere.')))
        always.add(point('mic', self.tr('Your voice when you dictate'),
                         self.tr('Recognition runs here. The recording is discarded once it has been written down, '
                                 'and recent transcripts are kept only until Akousousin quits.')))
        always.add(point('shield', self.tr('No accounts, analytics or tracking'),
                         self.tr('Akousousin has no sign-in and collects nothing about how you use it.')))
        self.add(always)

        internet = Card(self.tr('When Akousousin uses the internet'), self.tr('Only for these, and never with your text or voice.'))
        self.weekly = QCheckBox(self.tr('Check weekly'))
        self.weekly.toggled.connect(lambda on: self.state.save(update_weekly=on))
        internet.add(SettingRow(self.tr('Checking for updates'),
                                self.tr('Once a week, Akousousin asks GitHub whether a newer release exists. Nothing about you is sent.'),
                                self.weekly, first=True))
        internet.add(SettingRow(self.tr('Downloading voices and dictation models'),
                                self.tr('Only when you choose one, from the Piper and Whisper libraries on Hugging Face.'),
                                text(self.tr('Only when you ask'), 'muted', wrap=False)))
        self.samples = QCheckBox(self.tr('Allow samples'))
        self.samples.toggled.connect(lambda on: self.state.save(voice_samples=on))
        internet.add(SettingRow(self.tr('Hearing a voice before you download it'),
                                self.tr('Plays a short recording from the voice library.'), self.samples))
        self.add(internet)

        block = Card()
        self.blocked = QCheckBox(self.tr('Block all internet access'))
        self.blocked.setStyleSheet('font-size: 17px; font-weight: 600')
        self.blocked.toggled.connect(self.set_blocked)
        explanation = self.tr('Turns off update checks, downloads and online samples. Reading aloud, dictation and every '
                              'installed voice keep working exactly as before. You can still add voices and models from files.')
        self.blocked.setAccessibleDescription(explanation)
        block.add(self.blocked)
        block.add(text(explanation, 'muted'))
        self.blocked_note = text(self.tr('Akousousin will not connect to the internet.'), 'ok')
        block.add(self.blocked_note)
        self.add(block)
        self.settings_changed(self.state.config)

    def settings_changed(self, config):
        for box, key in ((self.weekly, 'update_weekly'), (self.samples, 'voice_samples'), (self.blocked, 'network_blocked')):
            box.blockSignals(True)
            box.setChecked(bool(config.get(key)))
            box.blockSignals(False)
        blocked = bool(config.get('network_blocked'))
        self.weekly.setEnabled(not blocked)
        self.samples.setEnabled(not blocked)
        self.blocked_note.setVisible(blocked)

    def set_blocked(self, on):
        self.state.save(network_blocked=on)
        self.notice(self.tr('Internet access blocked.') if on else self.tr('Internet access allowed for the uses listed.'))

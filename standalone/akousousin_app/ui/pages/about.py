# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""About: what the name means, where the project came from, and credits."""
from pathlib import Path

from PySide6.QtWidgets import QInputDialog, QVBoxLayout

from ... import __version__, resources
from .. import dialogs, theme
from ..flow import Columns
from ..widgets import Card, Rule, button, link, row, text
from .base import Page

VERSE = 'https://biblia.com/bible/bsb/john/5/25'


class AboutPage(Page):
    key = 'about'
    icon = 'info'

    def title(self):
        return self.tr('About')

    def subtitle(self):
        return self.tr('Where the name comes from, and who makes it possible.')

    def build(self):
        hero = Card(padding=28)
        logo = text()
        logo.setPixmap(theme.pixmap('voices', 56, theme.current().accent_text))
        words = QVBoxLayout()
        words.setSpacing(4)
        name = text('Akousousin  ἀκούσουσιν', 'title')
        words.addWidget(name)
        words.addWidget(text(self.tr('Greek for “they will hear”'), 'h3'))
        words.addWidget(text(self.tr('Version %1').replace('%1', __version__), 'muted'))
        layout = row(logo, spacing=24, stretch=False)
        layout.addLayout(words, 1)
        hero.add(layout)
        self.add(hero)

        verse = Card(self.tr('The name'))
        verse.add(text(self.tr('ἀκούσουσιν (akoúsousin) is the Greek word for “they will hear”. It comes from John 5:25:'), 'muted'))
        verse.add(text(self.tr('“Truly, truly, I tell you, the hour is coming and has now come when the dead will hear the voice '
                               'of the Son of God, and those who hear will live.”'), 'verse'))
        verse.add(link(self.tr('John 5:25, Berean Standard Bible · Read on Biblia'), VERSE))
        story = Card(self.tr('Our story'))
        story.add(text(self.tr('Akousousin began with an effort to make Logos Bible Software work on Linux through Wine. '
                               'Support for biblical languages remains one of the project’s goals.'), 'muted'))
        story.add(text(self.tr('That work drew our attention to a gap in speech accessibility on Linux desktops. Akousousin grew '
                               'to help people hear text read aloud and dictate in the applications they already use.'), 'muted'))

        credits = Card(self.tr('Credits and licences'))
        for title, detail in (
                ('Piper', self.tr('Speech synthesis, maintained by the Open Home Foundation’s voice project · GPL-3.0-or-later')),
                ('Whisper', self.tr('Speech recognition models by OpenAI · MIT')),
                ('faster-whisper · CTranslate2', self.tr('Local dictation, by SYSTRAN and contributors · MIT')),
                ('Akousousin', self.tr('© 2026 John Goodman · GPL-3.0-or-later. The SAPI engine is LGPL-2.1-or-later and keeps Wine’s copyright notices.'))):
            credits.add(Rule())
            credits.add(text(title, 'h3'))
            credits.add(text(detail, 'muted'))
        credits.add(text(self.tr('Each voice has its own licence, shown on the Voices page. The Berean Standard Bible quotation is in the public domain.'), 'small'))
        credits.add(row(link(self.tr('Source code'), 'https://github.com/jg00dman/akousousin'),
                        link(self.tr('Report a problem'), 'https://github.com/jg00dman/akousousin/issues'),
                        button(self.tr('Full licence texts…'), self.notices, kind='link'), spacing=16))
        self.add(Columns([[verse, story], [credits]], minimum=420))

    def notices(self):
        folder = resources.root().parent / 'licenses'
        if folder.is_dir():
            files = {str(p.relative_to(folder)): p for p in sorted(folder.rglob('*')) if p.is_file()}
        else:
            root = Path(__file__).resolve().parents[4]
            files = {name: root / name for name in ('LICENSING.md', 'LICENSE', 'LICENSES/LGPL-2.1-or-later.txt',
                     'recognition/Whisper-LICENSE', 'standalone/resources/CATALOGUE-LICENSE.md') if (root / name).is_file()}
        if not files:
            self.notice(self.tr('No licence texts were found in this installation.'))
            return
        name, ok = QInputDialog.getItem(self, self.tr('Licences and notices'), self.tr('Document'), list(files), 0, False)
        if ok:
            dialogs.document(self, name, files[name].read_text(encoding='utf-8', errors='replace'))

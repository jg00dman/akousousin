# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Voices: the default voice, one list of every voice by language, and how they read."""
import json
from pathlib import Path
import re
import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QFileDialog, QHeaderView, QInputDialog,
                               QLineEdit, QPushButton, QTreeView, QVBoxLayout, QWidget)

from ... import catalogue, network, resources, settings
from .. import theme
from ..flow import Columns
from ..lang import language_family, language_name, megabytes, number
from ..widgets import Card, ValueSlider, button, combo, fill, labelled, restyle, row, set_icon, spread, text
from .base import Page
from .voice_list import KEY, VoiceFilter, VoiceLibrary, size_of


class VoicesPage(Page):
    key = 'voices'
    icon = 'voices'

    def title(self):
        return self.tr('Voices')

    def subtitle(self):
        return self.tr('Choose how Akousousin sounds, overall and in each language.')

    def build(self):
        self.catalogue = catalogue.catalogue(resources.root())
        index = resources.root() / 'voice-samples.json'
        self.samples = set(json.loads(index.read_text())) if index.is_file() else set()

        # Default voice
        default = Card()
        star = text()
        star.setPixmap(theme.pixmap('star', 18, theme.current().accent_text))
        words = QVBoxLayout()
        words.setSpacing(4)
        words.addLayout(row(star, text(self.tr('Default voice'), 'h2'), spacing=8))
        words.addWidget(text(self.tr('Used when an app does not ask for a language, or when a language has no voice of its own.'), 'muted'))
        self.default = combo()
        self.default.setAccessibleName(self.tr('Default voice'))
        self.default.setMinimumWidth(280)
        self.default.setPlaceholderText(self.tr('No voices installed yet'))
        self.default.activated.connect(lambda _: self.assign(self.default.currentData(), True))
        top = row(stretch=False, spacing=24)
        top.addLayout(words, 1)
        top.addWidget(self.default, 0, Qt.AlignVCenter)
        default.add(top)
        self.add(default)

        # Search and filter
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr('Search voices or languages'))
        self.search.setAccessibleName(self.tr('Search voices'))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(theme.icon('search', theme.current().muted, 18), QLineEdit.LeadingPosition)
        self.show_group = QButtonGroup(self)
        shows = QWidget()
        shows.setAccessibleName(self.tr('Show'))
        layout = row(stretch=False, spacing=0)
        for key, caption in (('all', self.tr('All')), ('installed', self.tr('Installed')), ('available', self.tr('Available'))):
            option = QPushButton(caption)
            option.setCheckable(True)
            option.setProperty('segment', key)
            option.setChecked(key == 'all')
            self.show_group.addButton(option)
            layout.addWidget(option)
        shows.setLayout(layout)
        self.show_group.buttonClicked.connect(self.show_changed)
        self.import_button = button(self.tr('Import a Piper voice…'), self.import_voice)
        self.add(spread(self.search, shows, self.import_button, spacing=12))
        self.show_changed()

        # List and detail
        self.library = VoiceLibrary(self.catalogue)
        self.filter = VoiceFilter(self.library)
        self.tree = QTreeView()
        self.tree.setModel(self.filter)
        self.tree.setAccessibleName(self.tr('Voice library'))
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setMinimumHeight(460)
        self.tree.setMinimumWidth(400)
        self.tree.setRootIsDecorated(False)
        self.tree.setItemsExpandable(False)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setMinimumSectionSize(90)
        self.tree.selectionModel().currentChanged.connect(lambda *_: self.selection_changed())
        self.search.textChanged.connect(self.search_changed)

        self.detail = Card()
        self.name = text('', 'title')
        self.facts = text('', 'muted')
        self.role_line = text('', 'ok')
        self.note = text('', 'muted')
        self.play = button(self.tr('Play sample'), self.play_sample, kind='primary', icon='play')
        self.make_default = button(self.tr('Make default voice'), lambda: self.assign(self.key_(), True), icon='star')
        self.use_for = button('', lambda: self.assign(self.key_(), False))
        self.download = button('', self.review, icon='download')
        self.licence = button(self.tr('Licence and model card'), self.show_licence, kind='link')
        self.remove = button(self.tr('Remove voice…'), self.delete, kind='link')
        self.remove.setProperty('kind', 'link')
        for widget in (self.name, self.facts, self.role_line, self.note):
            self.detail.add(widget)
        self.detail.add(row(self.play, self.make_default, self.use_for, self.download))
        self.detail.add(row(self.licence, self.remove, spacing=16))

        reading = Card(self.tr('How voices read'))
        config = self.state.config
        self.speed = ValueSlider(self.tr('Speed'), .5, 4, .25, config['speed'], lambda v: number(v) + '×')
        self.volume = ValueSlider(self.tr('Volume'), 0, 100, 5, round(config['volume'] * 100),
                                  lambda v: self.tr('%1%').replace('%1', str(round(v))))
        self.speed.committed.connect(lambda v: self.save_reading(speed=v))
        self.volume.committed.connect(lambda v: self.save_reading(volume=round(v) / 100))
        self.language = combo()
        self.language.activated.connect(lambda _: self.save_reading(book_language=self.language.currentData()))
        reading.add(self.speed)
        reading.add(self.volume)
        reading.add(labelled(self.tr('Reading language'), self.language,
                             self.tr('Apps such as Logos say which language each passage is in.')))
        self.add(Columns([[self.tree], [self.detail, reading]], minimum=400, weights=[3, 2]))

        self.state.preview.changed.connect(self.preview_changed)
        self.settings_changed(config)
        self.select(config['voice'])

    # Model and selection ---------------------------------------------------
    def key_(self):
        index = self.tree.currentIndex()
        return index.siblingAtColumn(0).data(KEY) if index.isValid() else None

    def select(self, key):
        if key not in self.library.rows:
            return
        source = self.library.indexFromItem(self.library.rows[key][0])
        index = self.filter.mapFromSource(source)
        if index.isValid():
            self.tree.setCurrentIndex(index)
            self.tree.scrollTo(index)

    def search_changed(self, needle):
        current = self.key_()
        self.filter.set_search(needle)
        self.tree.expandAll()
        if current:
            self.select(current)
        if not self.key_():
            first = self.first_voice()
            if first is not None:
                self.tree.setCurrentIndex(first)
        self.selection_changed()

    def first_voice(self):
        for row_ in range(self.filter.rowCount()):
            group = self.filter.index(row_, 0)
            if self.filter.rowCount(group):
                return self.filter.index(0, 0, group)
        return None

    def show_changed(self, *_):
        checked = self.show_group.checkedButton()
        for option in self.show_group.buttons():
            restyle(option, kind='primary' if option is checked else None)
        if hasattr(self, 'filter'):
            self.filter.set_show(checked.property('segment'))
            self.search_changed(self.search.text())

    def settings_changed(self, config):
        self.library.update(config)
        self.tree.expandAll()
        installed = sorted(config['voices'].items(), key=lambda item: (language_name(item[1]['language']).casefold(), item[1]['name']))
        fill(self.default, [(key, f"{self.library.display_name(key)} · {language_name(voice['language'])}")
                            for key, voice in installed], config['voice'] if installed else None)
        self.default.setEnabled(bool(installed))
        languages = sorted({voice['language'] for voice in config['voices'].values()}, key=lambda c: language_name(c).casefold())
        fill(self.language, [('', self.tr('Follow each application')),
                             *((code, language_name(code)) for code in languages)], config['book_language'])
        self.speed.set(config['speed'])
        self.volume.set(round(config['volume'] * 100))
        self.selection_changed()

    def selection_changed(self):
        key = self.key_()
        config = self.state.config
        self.detail.setVisible(key is not None)
        if key is None:
            return
        entry = self.library.entries[key]
        voice = config['voices'].get(key)
        code = entry['language']['code']
        family_blocked = language_family(code) in catalogue.UNSUPPORTED_AUXILIARY
        self.name.setText(self.library.display_name(key))
        size = size_of(entry)
        facts = [language_name(code), self.tr('%1 quality').replace('%1', self.library.quality(entry.get('quality', '')))]
        if size:
            facts.append(megabytes(size))
        self.facts.setText(' · '.join(facts))
        is_default = bool(voice) and config['voice'] == key
        is_language = bool(voice) and config['language_voices'].get(voice['language']) == key
        self.role_line.setText(self.tr('This is your default voice') if is_default else
                               self.tr('Used for %1').replace('%1', language_name(code)) if is_language else '')
        self.role_line.setVisible(is_default or is_language)
        sample = self.sample_folder(key)
        self.play.setEnabled(bool(voice) or bool(sample and network.samples_allowed(self.state.path)))
        self.make_default.setVisible(bool(voice) and not is_default)
        self.use_for.setText(self.tr('Use for %1').replace('%1', language_name(code)))
        self.use_for.setVisible(bool(voice) and not is_language)
        self.download.setVisible(not voice)
        self.download.setEnabled(not family_blocked)
        self.download.setText(self.tr('Download · %1').replace('%1', megabytes(size)) if size else self.tr('Download'))
        self.remove.setVisible(bool(voice))
        notes = []
        if family_blocked:
            notes.append(self.tr('Voices for this language need extra language resources that are not available yet.'))
        elif not voice and not sample:
            notes.append(self.tr('No sample is available for this voice.'))
        elif not voice and not network.samples_allowed(self.state.path):
            notes.append(self.tr('Samples of voices you have not downloaded are turned off in Privacy.'))
        self.note.setText(' '.join(notes))
        self.note.setVisible(bool(notes))

    def sample_folder(self, key):
        model = next((p for p in self.library.entries[key].get('files', {}) if p.endswith('.onnx')), '')
        folder = model.rpartition('/')[0]
        return folder if folder in self.samples else None

    # Actions -------------------------------------------------------------
    def play_sample(self):
        key = self.key_()
        installed = key in self.state.config['voices']
        text_ = self.tr('Hello. This is how I sound when I read to you.')
        self.state.preview.toggle(key, text_, None if installed else self.sample_folder(key), failed=self.error)

    def preview_changed(self, playing):
        self.play.setText(self.tr('Stop') if playing else self.tr('Play sample'))
        set_icon(self.play, 'stop' if playing else 'play', 'primary')

    def assign(self, key, default):
        if not key:
            return

        def done(result):
            self.state.reload()
            pending = (result or {}).get('pending_registration')
            self.notice(self.tr('Saved. Restart Windows apps so they use the new voice.') if pending
                        else self.tr('%1 is now the default voice.').replace('%1', self.library.display_name(key)) if default
                        else self.tr('Voice saved for its language.'))

        self.run(lambda: self.state.call('voice' if default else 'language-voice', voice=key), done, key='assign')

    def save_reading(self, **changes):
        self.state.save(**changes)
        self.notice(self.tr('Saved.'))

    def review(self):
        key = self.key_()
        entry = self.library.entries[key]
        path = self.state.path

        def reviewed(card):
            message = self.tr('Each voice has its own licence. Please read it before downloading %1.').replace('%1', self.library.display_name(key))
            if self.confirm(self.tr('Voice licence'), message, self.tr('Accept and download'), details=card):
                self.run(lambda: catalogue.install(entry, settings.data_path() / 'voices', True, path=path),
                         lambda voice: self.register(key, voice), key='download',
                         busy=self.tr('Downloading %1…').replace('%1', self.library.display_name(key)))

        self.run(lambda: catalogue.card(entry, path), reviewed, key='licence', busy=self.tr('Fetching the voice licence…'))

    def register(self, key, voice):
        def finish():
            config = resources.register_voice(self.state.path, key, voice)
            if config.get('speechd_setup_pending'):
                from ...speech_dispatcher import complete_pending_setup
                complete_pending_setup(self.state.path)

        def done(_):
            self.state.reload()
            self.select(key)
            self.notice(self.tr('%1 is ready to use.').replace('%1', self.library.display_name(key)))

        self.run(finish, done, key='register')

    def show_licence(self):
        key = self.key_()
        voice = self.state.config['voices'].get(key)
        card = Path(voice['path']).parent / 'MODEL_CARD' if voice else None
        from .. import dialogs
        if card and card.is_file():
            dialogs.document(self, self.tr('Voice licence'), card.read_text(encoding='utf-8'))
        elif self.library.entries[key].get('files'):
            self.run(lambda: catalogue.card(self.library.entries[key], self.state.path),
                     lambda content: dialogs.document(self, self.tr('Voice licence'), content), key='licence')
        else:
            self.notice(self.tr('This imported voice has no MODEL_CARD file beside it.'))

    def delete(self):
        key = self.key_()
        name = self.library.display_name(key)
        if not self.confirm(self.tr('Remove voice'),
                            self.tr('Remove %1? Speech stops for a moment. Downloaded files are deleted; files you imported are kept.').replace('%1', name),
                            self.tr('Remove voice')):
            return

        def remove():
            self.state.call('stop', launch=False)
            resources.remove_voice(self.state.path, key)

        self.run(remove, lambda _: (self.state.reload(), self.notice(self.tr('%1 was removed.').replace('%1', name))), key='remove')

    def import_voice(self):
        filename, _ = QFileDialog.getOpenFileName(self, self.tr('Import a Piper voice'), '', self.tr('Piper voices (*.onnx)'))
        if not filename:
            return
        try:
            config = json.loads(Path(filename + '.json').read_text(encoding='utf-8'))
            code = config.get('language', {}).get('code')
            if not code:
                code, ok = QInputDialog.getText(self, self.tr('Voice language'), self.tr('Language code, for example en_US'))
                if not ok or not code.strip():
                    return
                code = code.strip()
            if language_family(code) in catalogue.UNSUPPORTED_AUXILIARY:
                raise ValueError(self.tr('Voices for this language need extra language resources that are not available yet.'))
            key = re.sub('[^A-Za-z0-9_-]', '_', Path(filename).stem)[:110]
            existing = self.state.config['voices'].get(key)
            if existing and existing['path'] != filename:
                key += '_' + uuid.uuid4().hex[:8]
            self.register(key, dict(name=key, path=filename, quality='local', language=code,
                                    sample_rate=config['audio']['sample_rate']))
        except (ValueError, OSError, KeyError) as problem:
            self.error(problem)

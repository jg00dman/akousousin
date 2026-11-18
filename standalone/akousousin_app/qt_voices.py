# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import json
from pathlib import Path
import re
import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QFormLayout,
                               QHeaderView, QInputDialog, QLineEdit, QTreeWidget, QTreeWidgetItem)

from . import catalogue, resources, runtime, settings
from .languages import label as language_name
from .qt_widgets import actions, choices, field, group, label, number, tr


class Voices:
    def __init__(self, panel, layout):
        self.panel = panel
        self.catalogue = catalogue.catalogue(resources.root())
        index = resources.root() / 'voice-samples.json'
        self.samples = set(json.loads(index.read_text())) if index.is_file() else set()
        form = QFormLayout()
        layout.addLayout(form)
        self.search = field(form, "Search voices", QLineEdit())
        languages = {v['language']['code'] for v in self.catalogue.values()}
        languages.update(v['language'] for v in panel.config['voices'].values())
        self.filter = choices(form, "Filter by language", [('', tr("All languages")),
            *((code, language_name(code)) for code in sorted(languages))], '')
        self.installed = QCheckBox(tr("Installed only"))
        form.addRow(self.installed)
        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setHeaderLabels([tr("Voice"), tr("Language"), tr("Quality"), tr("Status")])
        self.tree.setAccessibleName(tr("Voice library"))
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.setMinimumHeight(150)
        layout.addWidget(self.tree, 1)
        form = QFormLayout()
        layout.addLayout(form)
        self.detail = label()
        form.addRow(self.detail)
        self.preview, self.download, self.remove = actions(form,
            ("Play sample", self.play), ("Review licence and download…", self.review),
            ("Remove voice…", self.delete))
        self.prefer, self.default = actions(form, ("Use for this language", lambda: self.select(False)),
                                            ("Set as default voice", lambda: self.select(True)))
        actions(form, ("Import a Piper voice…", self.import_voice), ("Voice licence…", self.licence))
        actions(form, ("Reading preferences…", self.preferences))
        self.search.textChanged.connect(self.refresh)
        self.filter.currentIndexChanged.connect(self.refresh)
        self.installed.toggled.connect(self.refresh)
        self.tree.itemSelectionChanged.connect(self.selection_changed)
        self.reload()

    def preferences(self):
        panel = self.panel
        dialog, form = panel.dialog(tr("Reading preferences"))
        self.policy = choices(form, "Reading language", [('', tr("Follow application language"))], '')
        cfg = panel.config
        for code in sorted({v['language'] for v in cfg['voices'].values()}):
            self.policy.addItem(language_name(code), code)
        self.policy.setCurrentIndex(max(0, self.policy.findData(cfg['book_language'])))
        self.speed = number(form, "Speed", .5, 4., round(cfg['speed'] * 4) / 4, .25)
        self.volume = number(form, "Volume (%)", 0, 100, round(cfg['volume'] * 100))
        actions(form, ("Advanced synthesis…", panel.synthesis_options))
        if panel.accept(dialog, form):
            self.save()

    def reload(self):
        cfg = self.panel.config
        self.entries = dict(self.catalogue)
        for key, v in cfg['voices'].items():
            self.entries.setdefault(key, dict(key=key, name=v['name'], quality=v.get('quality', ''),
                                              language={'code': v['language']}, files={}))
        codes = sorted({v['language'] for v in cfg['voices'].values()})
        for code in codes:
            if self.filter.findData(code) < 0:
                self.filter.addItem(language_name(code), code)
        self.refresh()

    def key(self):
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    def refresh(self, *_):
        previous = self.key() or self.panel.config['voice']
        self.tree.blockSignals(True)
        self.tree.clear()
        cfg = self.panel.config
        needle = self.search.text().casefold()
        for key, entry in sorted(self.entries.items()):
            lang = entry['language']
            code = lang['code']
            installed = key in cfg['voices']
            if self.installed.isChecked() and not installed:
                continue
            if self.filter.currentData() and self.filter.currentData() != code:
                continue
            if needle not in ' '.join((key, entry['name'], *lang.values())).casefold():
                continue
            roles = [tr("Installed") if installed else tr("Available")]
            if installed and cfg['language_voices'].get(code) == key:
                roles.append(tr("Preferred for language"))
            if installed and cfg['voice'] == key:
                roles.append(tr("Default"))
            item = QTreeWidgetItem(self.tree, [entry['name'], language_name(code), entry['quality'], ', '.join(roles)])
            item.setData(0, Qt.UserRole, key)
            if key == previous:
                self.tree.setCurrentItem(item)
        if self.tree.currentItem() is None and self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.tree.blockSignals(False)
        self.selection_changed()

    def sample(self, key):
        model = next((p for p in self.entries[key]['files'] if p.endswith('.onnx')), '')
        folder = model.rpartition('/')[0]
        return folder if folder in self.samples else None

    def selection_changed(self):
        key = self.key()
        entry = self.entries.get(key, {})
        installed = key in self.panel.config['voices']
        for button in (self.prefer, self.default, self.remove):
            button.setEnabled(installed)
        self.prefer.setText(tr("Use for {language}").format(language=language_name(entry['language']['code']))
                            if entry else tr("Use for this language"))
        self.preview.setEnabled(bool(entry and (installed or self.sample(key))))
        supported = entry.get('language', {}).get('family') not in catalogue.UNSUPPORTED_AUXILIARY
        self.download.setVisible(not installed)
        self.download.setEnabled(bool(entry and supported))
        for button in (self.prefer, self.default, self.remove):
            button.setVisible(installed)
        size = sum(v['size_bytes'] for v in entry.get('files', {}).values()) / 1e6
        details = []
        if size and not installed:
            details.append(tr("Download size: {size} MB").format(size=round(size)))
        if entry and not self.preview.isEnabled():
            details.append(tr("No preview available."))
        if not supported:
            details.append(tr("Additional language resources are unavailable."))
        self.detail.setText('  '.join(details))

    def save(self):
        speed = round(self.speed.value() * 4) / 4
        self.speed.setValue(speed)
        self.panel.save(speed=speed, volume=self.volume.value()/100, book_language=self.policy.currentData())

    def play(self):
        key = self.key()
        self.panel.play(key, None if key in self.panel.config['voices'] else self.sample(key))

    def select(self, default):
        key = self.key()
        def selected(result):
            self.panel.reload()
            self.panel.notice(tr("Voice saved. Reapply voice registration in App integrations.")
                              if result and result.get('pending_registration') else tr("Voice preference saved."))
        self.panel.run(lambda: runtime.call(self.panel.path, {'command': 'voice' if default else 'language-voice',
                                                              'voice': key}), selected)

    def review(self):
        key = self.key()
        entry = self.entries[key]
        def reviewed(card):
            if self.panel.confirm(tr("Review voice licence"), card, tr("Accept and download")):
                self.panel.run(lambda: catalogue.install(entry, settings.data_path() / 'voices', True),
                               lambda voice: self.register(key, voice))
        self.panel.run(lambda: catalogue.card(entry), reviewed)

    def licence(self):
        key = self.key()
        if not key:
            return
        voice = self.panel.config['voices'].get(key)
        card = Path(voice['path']).parent / 'MODEL_CARD' if voice else None
        if card and card.is_file():
            self.panel.document(tr("Voice licence"), card.read_text(encoding='utf-8'))
        elif self.entries[key]['files']:
            self.panel.run(lambda: catalogue.card(self.entries[key]), lambda s: self.panel.document(tr("Voice licence"), s))
        else:
            self.panel.notice(tr("The imported voice has no adjacent MODEL_CARD file."))

    def register(self, key, voice):
        def finish():
            cfg = resources.register_voice(self.panel.path, key, voice)
            if cfg.get('speechd_setup_pending'):
                from .speech_dispatcher import complete_pending_setup
                complete_pending_setup(self.panel.path)
        self.panel.run(finish, lambda _: self.changed())

    def changed(self):
        self.panel.reload()
        self.panel.notice(tr("Voice library changed. Reapply voice registration in App integrations if needed."))

    def import_voice(self):
        filename, _ = QFileDialog.getOpenFileName(self.panel, tr("Import a Piper voice"), '', 'Piper (*.onnx)')
        if not filename:
            return
        try:
            cfg = json.loads(Path(filename + '.json').read_text(encoding='utf-8'))
            code = cfg.get('language', {}).get('code')
            if not code:
                code, ok = QInputDialog.getText(self.panel, tr("Model language"), tr("Language code, for example en_US"))
                if not ok or not code.strip():
                    return
            if code.split('_')[0] in catalogue.UNSUPPORTED_AUXILIARY:
                raise ValueError(tr("Additional language resources are unavailable."))
            key = re.sub('[^A-Za-z0-9_-]', '_', Path(filename).stem)[:110]
            existing = self.panel.config['voices'].get(key)
            if existing and existing['path'] != filename:
                key += '_' + uuid.uuid4().hex[:8]
            self.register(key, dict(name=key, path=filename, quality='local', language=code, sample_rate=cfg['audio']['sample_rate']))
        except (ValueError, OSError, KeyError) as error:
            self.panel.error(error)

    def delete(self):
        key = self.key()
        if not self.panel.confirm(tr("Remove voice"), tr("Remove {name}? Speech will stop. Downloaded files will be deleted. Imported originals are kept. Removing the last voice disables speech output.").format(name=self.entries[key]['name']), tr("Remove voice")):
            return
        def remove():
            runtime.call(self.panel.path, {'command': 'stop'}, launch=False)
            resources.remove_voice(self.panel.path, key)
        self.panel.run(remove, lambda _: self.changed())

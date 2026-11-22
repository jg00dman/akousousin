# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The voice library as a Qt model, grouped by language.

The model is built once and then updated in place, so a screen reader keeps
its position when a voice is downloaded, removed or made the default.
"""
from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QStandardItem, QStandardItemModel

from ... import catalogue
from .. import theme
from ..lang import language_family, language_name, megabytes

KEY = Qt.UserRole + 1
SEARCH = Qt.UserRole + 2
INSTALLED = Qt.UserRole + 3


def size_of(entry):
    return sum(value.get('size_bytes', 0) for value in entry.get('files', {}).values())


class VoiceLibrary(QStandardItemModel):
    def __init__(self, entries):
        super().__init__()
        self.setHorizontalHeaderLabels([self.tr('Voice'), self.tr('Quality'), self.tr('Status')])
        self.entries = {}
        self.groups = {}
        self.rows = {}
        for key, entry in sorted(entries.items(), key=lambda item: (language_name(item[1]['language']['code']).casefold(),
                                                                     item[1]['name'].casefold())):
            self.add(key, entry)

    def add(self, key, entry):
        self.entries[key] = entry
        code = entry['language']['code']
        group = self.groups.get(code)
        if group is None:
            group = QStandardItem(language_name(code))
            font = QFont()
            font.setBold(True)
            group.setFont(font)
            group.setSelectable(False)
            group.setEditable(False)
            language = entry['language']
            group.setData(' '.join(filter(None, (code, language_name(code), language.get('name_english', ''),
                                                 language.get('name_native', '')))).casefold(), SEARCH)
            self.groups[code] = group
            self.appendRow([group, self._blank(), self._blank()])
        name = QStandardItem(entry['name'].replace('_', ' ').title() if entry['name'].islower() else entry['name'])
        name.setData(key, KEY)
        name.setData(' '.join((key, entry['name'], group.data(SEARCH))).casefold(), SEARCH)
        name.setEditable(False)
        quality = QStandardItem(self.quality(entry.get('quality', '')))
        quality.setEditable(False)
        status = QStandardItem('')
        status.setEditable(False)
        group.appendRow([name, quality, status])
        self.rows[key] = (name, quality, status)

    @staticmethod
    def _blank():
        item = QStandardItem('')
        item.setSelectable(False)
        item.setEditable(False)
        return item

    def quality(self, value):
        return {'x_low': self.tr('Very low'), 'low': self.tr('Low'), 'medium': self.tr('Medium'),
                'high': self.tr('High'), 'local': self.tr('Imported')}.get(value, value.title())

    def display_name(self, key):
        return self.rows[key][0].text() if key in self.rows else key

    def role(self, key, config):
        """What this voice does, in a few words."""
        voice = config['voices'].get(key)
        entry = self.entries[key]
        if not voice:
            if language_family(entry['language']['code']) in catalogue.UNSUPPORTED_AUXILIARY:
                return self.tr('Not available yet')
            return self.tr('Download · %1').replace('%1', megabytes(size_of(entry)))
        if config['voice'] == key:
            return self.tr('Default voice')
        if config['language_voices'].get(voice['language']) == key:
            return self.tr('Used for %1').replace('%1', language_name(voice['language']))
        return self.tr('Installed')

    def update(self, config):
        for key, voice in config['voices'].items():
            if key not in self.rows:
                self.add(key, dict(key=key, name=voice['name'], quality=voice.get('quality', 'local'),
                                   language={'code': voice['language']}, files={}))
        for key, (name, _quality, status) in self.rows.items():
            installed = key in config['voices']
            if installed and config['voices'][key].get('name') and name.text() != config['voices'][key]['name']:
                name.setText(config['voices'][key]['name'])
            text = self.role(key, config)
            if status.text() != text:
                status.setText(text)
                palette = theme.current()
                status.setForeground(QBrush(QColor(palette.ok if installed else palette.caution)))
            name.setData(installed, INSTALLED)


class VoiceFilter(QSortFilterProxyModel):
    """Search text plus an All / Installed / Available choice."""
    def __init__(self, library):
        super().__init__()
        self.setSourceModel(library)
        self.setRecursiveFilteringEnabled(True)
        self.needle = ''
        self.show = 'all'

    def set_search(self, needle):
        self.needle = needle.strip().casefold()
        self.invalidateFilter()

    def set_show(self, show):
        self.show = show
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        index = self.sourceModel().index(row, 0, parent)
        if not parent.isValid():
            return False  # groups appear when one of their voices does
        installed = bool(index.data(INSTALLED))
        if self.show == 'installed' and not installed or self.show == 'available' and installed:
            return False
        return not self.needle or self.needle in (index.data(SEARCH) or '')

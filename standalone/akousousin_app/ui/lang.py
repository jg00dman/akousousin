# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Language names and translated status sentences.

Language names are shown in their own language ("Ελληνικά", "Español"), so
they read correctly whatever language the panel itself is in. Status comes
from the controller as codes and is worded here, in the panel's language.
"""
from functools import lru_cache
import os

from PySide6.QtCore import QCoreApplication, QLocale

from .. import languages

translate = QCoreApplication.translate


def _capital(value):
    return value[:1].upper() + value[1:] if value else value


@lru_cache(maxsize=1)
def _native_names():
    from .. import catalogue, resources
    names = {}
    try:
        for entry in catalogue.catalogue(resources.root()).values():
            language = entry['language']
            names.setdefault(language['family'], language['name_native'].replace('\u200e', '').strip())
    except (OSError, ValueError, KeyError):
        pass
    return names


@lru_cache(maxsize=None)
def language_name(code):
    """'el_GR' → 'Ελληνικά (Ελλάδα)'; unknown codes fall back to the catalogue."""
    if not code:
        return translate('Language', 'Automatic')
    locale = QLocale(code.replace('-', '_'))
    if locale.language() == QLocale.C:
        return languages.label(code)
    # The family's own name ("English"), not a regional variant ("American English").
    name = _capital(_native_names().get(language_family(code)) or locale.nativeLanguageName())
    if '_' in code or '-' in code:
        territory = locale.nativeTerritoryName()
        if territory:
            return f'{name} ({territory})'
    return name


def language_family(code):
    return (code or '').replace('-', '_').split('_')[0].lower()


def number(value, decimals=1):
    return QLocale().toString(float(value), 'f', decimals)


def megabytes(size_bytes):
    size = size_bytes / 1e6
    if size >= 1000:
        return translate('Units', '%1 GB').replace('%1', number(size / 1000, 1))
    return translate('Units', '%1 MB').replace('%1', QLocale().toString(round(size)))


def keys(description):
    """'CTRL+ALT+SPACE' or 'Ctrl+Alt+Space' → ['Ctrl', 'Alt', 'Space']."""
    if not description or description == 'Unassigned':
        return []
    names = {'CTRL': 'Ctrl', 'ALT': 'Alt', 'SHIFT': 'Shift', 'SPACE': 'Space', 'META': 'Meta', 'SUPER': 'Super'}
    return [names.get(part.strip().upper(), part.strip().title() if len(part.strip()) > 1 else part.strip().upper())
            for part in description.replace(' ', '').split('+') if part.strip()]


def dictation_state(status, supported=True):
    """A short sentence for the dictation phase and whether it needs attention."""
    if not supported:
        if os.name == 'nt':
            return translate('Status', 'Dictation is not available on Windows yet'), 'off'
        return translate('Status', 'Dictation needs a Linux build with recognition'), 'off'
    if not status:
        return translate('Status', 'Dictation status unavailable'), 'off'
    phase = status.get('phase', 'unloaded')
    if phase == 'error':
        return translate('Status', 'Dictation problem — see Dictation'), 'danger'
    if status.get('busy'):
        return {
            'loading': (translate('Status', 'Preparing dictation…'), 'caution'),
            'opening': (translate('Status', 'Opening the microphone…'), 'caution'),
            'listening': (translate('Status', 'Listening…'), 'ok'),
            'transcribing': (translate('Status', 'Writing down what you said…'), 'ok'),
        }.get(phase, (translate('Status', 'Dictation busy…'), 'caution'))
    return translate('Status', 'Ready'), 'ok'


def speech_state(health, has_voice):
    if not has_voice:
        return translate('Status', 'No voice yet — choose one in Voices'), 'caution'
    if health and health.get('ready'):
        if health.get('speaking'):
            return translate('Status', 'Speaking'), 'ok'
        return translate('Status', 'Ready'), 'ok'
    # The service starts by itself when an app needs speech.
    return translate('Status', 'Ready — starts when needed'), 'ok'

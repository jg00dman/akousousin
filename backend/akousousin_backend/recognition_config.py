# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Lightweight recognition defaults; no model imports or network access."""
import locale
import os

TIERS = ('base', 'base.en', 'small', 'small.en', 'turbo')
LANGUAGES = frozenset('af am ar as az ba be bg bn bo br bs ca cs cy da de el en es et eu fa fi fo fr gl gu ha haw he hi hr ht hu hy id is it ja jw ka kk km kn ko la lb ln lo lt lv mg mi mk ml mn mr ms mt my ne nl nn no oc pa pl ps pt ro ru sa sd si sk sl sn so sq sr su sv sw ta te tg th tk tl tr tt uk ur uz vi yi yo zh yue'.split())


def system_language():
    value = next((os.environ[key] for key in ('LC_ALL', 'LC_MESSAGES', 'LANG') if os.environ.get(key)), None)
    if not value:
        value = locale.getlocale()[0] or 'en'
    token = value.split('.')[0].split('@')[0].replace('_', '-').split('-')[0].lower()
    return {'iw':'he', 'in':'id', 'ji':'yi'}.get(token, token) if token in LANGUAGES or token in ('iw', 'in', 'ji') else 'en'


def default_model(language):
    return 'base.en' if language == 'en' else 'base'


def cpu_threads(value=None):
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError('CPU threads must be an integer of at least 1')
        return value
    try:
        import psutil
        return max(1, psutil.cpu_count(logical=False) or os.cpu_count() or 1)
    except ImportError:
        return max(1, os.cpu_count() or 1)

# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The one switch that keeps Akousousin from using the internet.

Text and audio are always processed locally. The internet is used only for
update checks, downloads the user asks for, and online voice samples. Every
one of those calls ``require`` first, so "Block all internet access" in
Privacy is enforced in one place.
"""
from . import settings


class NetworkBlocked(RuntimeError):
    title = 'Internet access is blocked'


def blocked(path=None):
    try:
        return bool(settings.load(path or settings.config_path()).get('network_blocked', False))
    except (OSError, ValueError):
        return False


def require(path=None, purpose='this'):
    if blocked(path):
        raise NetworkBlocked(f'Internet access is blocked in Privacy, so {purpose} is not available. '
                             'Reading aloud, dictation and installed voices keep working.')


def samples_allowed(path=None):
    try:
        config = settings.load(path or settings.config_path())
    except (OSError, ValueError):
        return True
    return config.get('voice_samples', True) and not config.get('network_blocked', False)

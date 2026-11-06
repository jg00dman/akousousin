# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Stable identity for unsandboxed desktop-portal peers, including AppImages."""
import os
from pathlib import Path
import tempfile

APP_ID = 'org.akousousin.Akousousin'
MARKER = 'X-Akousousin-ManagedIdentity=true'


def desktop_exec(arguments):
    """Quote argv for Desktop Entry Exec (not a shell command)."""
    quoted = []
    for argument in arguments:
        value = str(argument)
        if any(character in value for character in ('\n', '\r', '\0')):
            raise ValueError('Application path contains an unsupported control character')
        # First quote Exec arguments, then escape the desktop-file string layer.
        value = value.replace('%', '%%')
        for character in ('\\', '"', '`', '$'):
            value = value.replace(character, '\\' + character)
        quoted.append('"' + value + '"')
    return ' '.join(quoted).replace('\\', '\\\\')


def ensure_desktop_entry(arguments=None, data_home=None):
    from . import runtime, settings
    base = Path(data_home) if data_home is not None else settings.data_path().parent
    directory = base / 'applications'
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / (APP_ID + '.desktop')
    if destination.is_symlink() or (destination.exists() and MARKER not in destination.read_text(encoding='utf-8')):
        # An existing user-installed launcher already supplies this identity.
        # Do not rewrite a custom launcher to make portal registration work.
        return destination
    if arguments is None:
        image = os.environ.get('APPIMAGE')
        if image and not Path(image).is_file():
            raise RuntimeError('The running AppImage has moved or been removed. Quit AKS and launch it from its current location.')
        if image and not os.access(image, os.X_OK):
            raise RuntimeError('The AppImage is not executable. Enable executable permission in its file Properties, then restart AKS.')
    invocation = runtime.command('--configure') if arguments is None else arguments
    content = ('[Desktop Entry]\nType=Application\nName=Akousousin\n'
               'Comment=Local neural speech and dictation\nNoDisplay=true\nTerminal=false\n'
               'Exec=' + desktop_exec(invocation) + '\n' + MARKER + '\n')
    # Do not invalidate the desktop service's application cache on every attempt.
    if destination.exists() and destination.read_text(encoding='utf-8') == content:
        return destination
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
                                         prefix='.' + APP_ID, delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
        temporary.chmod(0o644)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

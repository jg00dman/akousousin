# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Host WAV preview with cancellation and copyable player diagnostics."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time

from . import runtime


class PlaybackError(RuntimeError):
    title = 'Preview playback failed'

    def __init__(self, player, path, reason, diagnostic=''):
        self.command = shlex.join([player, str(path)])
        self.message = f'Audio was generated, but {Path(player).name} {reason}.'
        if diagnostic:
            self.message += '\n' + diagnostic
        self.details = 'Saved WAV: ' + str(path) + '\nPlayer: ' + player + '\n' + reason
        if diagnostic:
            self.details += '\n' + diagnostic
        super().__init__(self.message)


def play_wav(path, cancelled=lambda: False, timeout=120):
    player = next((found for name in ('pw-play', 'paplay', 'aplay') if (found := shutil.which(name))), None)
    if not player:
        raise RuntimeError('Preview audio was generated at ' + str(path) +
                           ', but no pw-play, paplay or aplay executable was found.')
    if cancelled():
        return False
    # A temporary file cannot deadlock on a full stderr pipe, even for a noisy
    # driver. Only the final 4 KiB is included in the user-visible diagnostic.
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.Popen([player, str(path)], env=runtime.host_environment(),
                                       stdout=output, stderr=subprocess.STDOUT)
        except OSError as error:
            raise PlaybackError(player, path, 'could not start', str(error)) from error
        try:
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if cancelled():
                    return False
                if time.monotonic() >= deadline:
                    raise PlaybackError(player, path, f'timed out after {timeout} seconds')
                time.sleep(.025)
            if process.returncode:
                output.seek(0, os.SEEK_END)
                output.seek(max(0, output.tell() - 4096))
                detail = output.read().decode(errors='replace').strip()
                raise PlaybackError(player, path, f'exited with status {process.returncode}', detail)
            return True
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)

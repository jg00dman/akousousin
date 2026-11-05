# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit, persistent recognition model installation, separate from inference."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .recognition import model_root

FILES = ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt')
SMALL_REVISION = '536b0662742c02347bc0e980a01041f333bce120'


def installed(model='small', root=None):
    directory = Path(root if root is not None else model_root()) / model
    return all((directory / name).is_file() and (directory / name).stat().st_size > 0 for name in FILES)


def install(model='small', root=None, source=None, progress=lambda text: None):
    """Stage completely before publishing; a failed install leaves old assets intact."""
    if model not in ('small', 'turbo'):
        raise ValueError('Unknown model')
    if source is None and model != 'small':
        raise ValueError('Turbo download is not configured yet; import a converted local model')
    from filelock import FileLock
    root = Path(root if root is not None else model_root())
    root.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / '.install.lock'), timeout=0):
        # A cancelled download worker may leave its temporary stage behind.
        # The exclusive install lock proves these stages have no live installer.
        for orphan in root.glob('.install-*'):
            if orphan.is_dir() and not orphan.is_symlink():
                shutil.rmtree(orphan)
        if installed(model, root):
            return root / model
        with tempfile.TemporaryDirectory(prefix='.install-', dir=root) as temporary:
            stage = Path(temporary) / model
            stage.mkdir()
            if source is None:
                progress('Downloading Small (about 485 MB)…')
                from huggingface_hub import snapshot_download
                snapshot_download('Systran/faster-whisper-small', revision=SMALL_REVISION,
                                  local_dir=stage, allow_patterns=[*FILES, 'README.md'])
            else:
                progress('Importing model…')
                for name in (*FILES, 'README.md'):
                    file = Path(source) / name
                    if file.is_file():
                        shutil.copy2(file, stage / name)
            progress('Verifying model files…')
            hashes = {}
            for name in FILES:
                file = stage / name
                if not file.is_file() or file.stat().st_size == 0:
                    raise ValueError('Incomplete model: ' + name)
                with file.open('rb') as stream:
                    hashes[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
            json.loads((stage / 'config.json').read_text())
            json.loads((stage / 'tokenizer.json').read_text())
            (stage / 'installation.json').write_text(json.dumps({'model': model, 'sha256': hashes,
                'repository': 'Systran/faster-whisper-small' if source is None else 'local import',
                'revision': SMALL_REVISION if source is None else None}, indent=2))
            target = root / model
            # Only an incomplete installation is replaced; imports cannot silently
            # overwrite an already installed model.
            backup = root / ('.previous-' + model)
            if backup.exists():
                raise RuntimeError('Previous interrupted installation requires recovery: ' + str(backup))
            if target.exists():
                target.rename(backup)
            try:
                stage.rename(target)
            except BaseException:
                if backup.exists():
                    backup.rename(target)
                raise
            if backup.exists():
                shutil.rmtree(backup)
            return target

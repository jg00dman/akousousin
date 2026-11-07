# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Explicit, persistent recognition model installation, separate from inference."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .recognition import model_root
from .downloads import Transfer
from .recognition_config import TIERS
from .model_pins import REVISIONS

CORE_FILES = ('model.bin', 'config.json', 'tokenizer.json')
FILES = (*CORE_FILES, 'vocabulary.txt')
VOCABULARIES = ('vocabulary.txt', 'vocabulary.json')
SMALL_REVISION = REVISIONS['small']


def installed(model='small', root=None):
    directory = Path(root if root is not None else model_root()) / model
    return all((directory / name).is_file() and (directory / name).stat().st_size > 0 for name in CORE_FILES) and any(
        (directory / name).is_file() and (directory / name).stat().st_size > 0 for name in VOCABULARIES)


def install(model='small', root=None, source=None, progress=lambda text: None):
    """Stage completely before publishing; a failed install leaves old assets intact."""
    if model not in TIERS:
        raise ValueError('Unknown model')
    if source is None and model not in REVISIONS:
        raise ValueError('Download is not configured for this model; import a converted local model')
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
        with Transfer('Whisper · ' + model.title()) as transfer, tempfile.TemporaryDirectory(prefix='.install-', dir=root) as temporary:
            stage = Path(temporary) / model
            stage.mkdir()
            if source is None:
                progress('Downloading ' + model + '…')
                from huggingface_hub import HfApi, hf_hub_url
                repository = 'Systran/faster-whisper-' + model
                revision = REVISIONS[model]
                info = HfApi().model_info(repository, revision=revision,
                                         files_metadata=True)
                entries = {file.rfilename: file for file in info.siblings}
                vocabulary = next((name for name in VOCABULARIES if name in entries), 'vocabulary.txt')
                names = [*CORE_FILES, vocabulary, 'README.md']
                if any(name not in entries or not entries[name].size for name in names):
                    raise ValueError('Whisper download metadata is incomplete')
                transfer.phase('Downloading', total=sum(entries[name].size for name in names))
                for name in names:
                    file = entries[name]
                    transfer.fetch(hf_hub_url(repository, name, revision=revision),
                                   stage / name, size=file.size,
                                   sha256=file.lfs.sha256 if file.lfs else None,
                                   git_sha1=None if file.lfs else file.blob_id)
            else:
                progress('Importing model…')
                transfer.phase('Importing model')
                for name in (*CORE_FILES, *VOCABULARIES, 'README.md'):
                    file = Path(source) / name
                    if file.is_file():
                        shutil.copy2(file, stage / name)
            if source is None:
                shutil.copy2(Path(__file__).with_name('Whisper-LICENSE.txt'), stage / 'LICENSE.txt')
            elif (Path(source) / 'LICENSE.txt').is_file():
                shutil.copy2(Path(source) / 'LICENSE.txt', stage / 'LICENSE.txt')
            progress('Verifying model files…')
            transfer.phase('Verifying model files')
            hashes = {}
            vocabulary = next((name for name in VOCABULARIES if (stage / name).is_file()), 'vocabulary.txt')
            for name in (*CORE_FILES, vocabulary):
                file = stage / name
                if not file.is_file() or file.stat().st_size == 0:
                    raise ValueError('Incomplete model: ' + name)
                with file.open('rb') as stream:
                    hashes[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
            json.loads((stage / 'config.json').read_text())
            json.loads((stage / 'tokenizer.json').read_text())
            (stage / 'installation.json').write_text(json.dumps({'model': model, 'sha256': hashes,
                'repository': repository if source is None else 'local import',
                'revision': revision if source is None else None}, indent=2))
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

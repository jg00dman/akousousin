# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Pinned Piper catalogue; user-selected downloads preserve upstream licence cards."""
import json
from pathlib import Path
import re
import tempfile
import urllib.request

from akousousin_backend.downloads import Transfer

REVISION = 'b4e358ffcb232591bf73a540e70f7de528e4174a'
BASE = f'https://huggingface.co/rhasspy/piper-voices/resolve/{REVISION}'
UNSUPPORTED_AUXILIARY = {'ar', 'he'}
APPROVED = {'en_US-ljspeech-medium': 'Repository MIT declaration; public-domain LJ Speech; trained from scratch'}


def catalogue(resource):
    return json.loads((Path(resource) / 'catalogue.json').read_text(encoding='utf-8'))


def card(entry):
    path = next(p for p in entry['files'] if p.endswith('/MODEL_CARD'))
    with Transfer('Voice licence · ' + entry['name']) as transfer, tempfile.TemporaryDirectory() as temporary:
        transfer.phase('Downloading licence', total=entry['files'][path]['size_bytes'])
        destination = Path(temporary) / 'MODEL_CARD'
        transfer.fetch(BASE + '/' + path, destination, size=entry['files'][path]['size_bytes'])
        return destination.read_text(encoding='utf-8')


def install(entry, directory, reviewed=False, publish=True):
    key = entry['key']
    if entry['language']['family'] in UNSUPPORTED_AUXILIARY:
        raise ValueError('Arabic/Hebrew preprocessing models are not distributed in this program-only beta')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', key):
        raise ValueError('Invalid voice identifier')
    if key not in APPROVED and not reviewed:
        raise ValueError('Review this voice’s model and dataset licences before downloading')
    model = next(p for p in entry['files'] if p.endswith('.onnx'))
    config = model + '.json'
    folder = model.rsplit('/', 1)[0]
    # SHA-256 is the content-addressed LFS object ID, from the pinned tree.
    url = f'https://huggingface.co/api/models/rhasspy/piper-voices/tree/{REVISION}/{folder}'
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / key
    if target.exists():
        raise ValueError('This voice is already installed')
    with Transfer('Voice · ' + entry['name'], publish=publish) as transfer, tempfile.TemporaryDirectory(dir=directory) as temporary:
        stage = Path(temporary)
        transfer.phase('Fetching voice information')
        with urllib.request.urlopen(url, timeout=30) as response:
            listing = json.load(response)
        sha = next(x['lfs']['oid'] for x in listing if x['path'] == model)
        model_card = next(p for p in entry['files'] if p.endswith('/MODEL_CARD'))
        paths = [(model, key + '.onnx'), (config, key + '.onnx.json'), (model_card, 'MODEL_CARD')]
        transfer.phase('Downloading', total=sum(entry['files'][path]['size_bytes'] for path, _ in paths))
        for path, filename in paths:
            transfer.fetch(BASE + '/' + path, stage / filename, size=entry['files'][path]['size_bytes'],
                           sha256=sha if path == model else None)
        transfer.phase('Downloading licence notices')
        transfer.fetch(BASE + '/README.md', stage / 'UPSTREAM-README.md')
        transfer.phase('Verifying voice')
        cfg = json.loads((stage / (key + '.onnx.json')).read_text(encoding='utf-8'))
        sample_rate = cfg['audio']['sample_rate']
        provenance = {'revision': REVISION, 'model_sha256': sha, 'source': BASE + '/' + model,
                      'reviewed_by_user': reviewed, 'project_review': APPROVED.get(key, '')}
        (stage / 'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
        stage.rename(target)
    return {'path': str(target / (key + '.onnx')), 'language': entry['language']['code'],
            'sample_rate': sample_rate, 'name': entry['name'], 'quality': entry['quality']}

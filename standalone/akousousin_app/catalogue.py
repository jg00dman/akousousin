"""Pinned Piper catalogue; user-selected downloads preserve upstream licence cards."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import urllib.request

REVISION = 'b4e358ffcb232591bf73a540e70f7de528e4174a'
BASE = f'https://huggingface.co/rhasspy/piper-voices/resolve/{REVISION}'
UNSUPPORTED_AUXILIARY = {'ar', 'he'}
APPROVED = {'en_US-ljspeech-medium': 'Repository MIT declaration; public-domain LJ Speech; trained from scratch'}


def fetch(url, destination, expected=None):
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=30) as response, Path(destination).open('wb') as output:
        while data := response.read(1024 * 1024):
            digest.update(data)
            output.write(data)
    if expected and digest.hexdigest() != expected:
        raise ValueError('Downloaded file checksum does not match the pinned source')
    return digest.hexdigest()


def catalogue(resource):
    return json.loads((Path(resource) / 'catalogue.json').read_text(encoding='utf-8'))


def card(entry):
    path = next(p for p in entry['files'] if p.endswith('/MODEL_CARD'))
    with urllib.request.urlopen(BASE + '/' + path, timeout=30) as response:
        return response.read(128 * 1024).decode('utf-8')


def install(entry, directory, reviewed=False):
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
    with urllib.request.urlopen(url, timeout=30) as response:
        listing = json.load(response)
    sha = next(x['lfs']['oid'] for x in listing if x['path'] == model)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / key
    if target.exists():
        raise ValueError('This voice is already installed')
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        stage = Path(temporary)
        fetch(BASE + '/' + model, stage / (key + '.onnx'), sha)
        fetch(BASE + '/' + config, stage / (key + '.onnx.json'))
        (stage / 'MODEL_CARD').write_text(card(entry), encoding='utf-8')
        fetch(BASE + '/README.md', stage / 'UPSTREAM-README.md')
        provenance = {'revision': REVISION, 'model_sha256': sha, 'source': BASE + '/' + model,
                      'reviewed_by_user': reviewed, 'project_review': APPROVED.get(key, '')}
        (stage / 'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
        shutil.move(str(stage), str(target))
    cfg = json.loads((target / (key + '.onnx.json')).read_text(encoding='utf-8'))
    return {'path': str(target / (key + '.onnx')), 'language': entry['language']['code'],
            'sample_rate': cfg['audio']['sample_rate'], 'name': entry['name'], 'quality': entry['quality']}

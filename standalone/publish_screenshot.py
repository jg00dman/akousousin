#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Publish the tested release's real control-panel screenshot on the repo homepage."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys

repository = os.environ['GITHUB_REPOSITORY']


def api(path, payload=None, method=None):
    command = ['gh', 'api', 'repos/' + repository + path]
    if payload is not None:
        command += ['--method', method or 'POST', '--input', '-']
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


picture = Path(sys.argv[1]).read_bytes()
if not picture.startswith(b'\x89PNG\r\n\x1a\n'):
    raise ValueError('The control-panel screenshot is not a PNG')
version = re.search(r'^version = "([^"]+)"', Path('standalone/pyproject.toml').read_text(), re.M)[1]
head = api('/git/ref/heads/main')['object']['sha']
parent = api('/git/commits/' + head)
readme = base64.b64decode(api('/contents/README.md?ref=' + head)['content']).decode('utf-8')
start, end = '<!-- akousousin-screenshot:start -->', '<!-- akousousin-screenshot:end -->'
block = (start + '\n![Akousousin ' + version + ' control panel showing the speech service, '
         'voice preview and desktop reading navigation](docs/images/control-panel.png)\n' + end)
if start in readme and end in readme:
    readme = re.sub(re.escape(start) + r'.*?' + re.escape(end), block, readme, flags=re.S)
else:
    position = readme.find('\n## ')
    position = position if position >= 0 else len(readme)
    readme = readme[:position].rstrip() + '\n\n' + block + '\n' + readme[position:]
blob = api('/git/blobs', {'content': base64.b64encode(picture).decode('ascii'), 'encoding': 'base64'})
tree = api('/git/trees', {'base_tree': parent['tree']['sha'], 'tree': [
    {'path': 'docs/images/control-panel.png', 'mode': '100644', 'type': 'blob', 'sha': blob['sha']},
    {'path': 'docs/images/control-panel.png.license', 'mode': '100644', 'type': 'blob',
     'content': 'SPDX-License-Identifier: GPL-3.0-or-later\nSPDX-FileCopyrightText: 2026 John Goodman\n'},
    {'path': 'README.md', 'mode': '100644', 'type': 'blob', 'content': readme}]})
commit = api('/git/commits', {'tree': tree['sha'], 'parents': [head],
                            'message': 'docs: show the ' + version + ' control panel on the homepage [skip ci]'})
# The new commit has the observed head as its parent. A concurrent update makes
# this non-fast-forward and is rejected instead of overwriting anybody's work.
api('/git/refs/heads/main', {'sha': commit['sha'], 'force': False}, method='PATCH')
print('Published README screenshot:', commit['sha'])

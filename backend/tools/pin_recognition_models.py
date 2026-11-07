#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Explicit developer operation: resolve immutable model revisions, without weights."""
import argparse
import pprint
from pathlib import Path
from huggingface_hub import HfApi


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    revisions = {'small':'536b0662742c02347bc0e980a01041f333bce120'}
    for tier in ('base', 'base.en', 'small.en'):
        info = HfApi().model_info('Systran/faster-whisper-' + tier, files_metadata=True)
        required = {'model.bin', 'config.json', 'tokenizer.json', 'README.md'}
        entries = {item.rfilename:item for item in info.siblings}
        if not required <= entries.keys() or not {'vocabulary.txt', 'vocabulary.json'} & entries.keys() or any(not entries[name].size for name in required):
            raise ValueError('Incomplete model metadata: ' + tier)
        if len(info.sha) != 40 or any(char not in '0123456789abcdef' for char in info.sha):
            raise ValueError('Invalid immutable revision: ' + tier)
        revisions[tier] = info.sha
    args.output.write_text('# SPDX-License-Identifier: GPL-3.0-or-later\n'
                           '# SPDX-FileCopyrightText: 2026 John Goodman\n'
                           '"""Immutable upstream model revisions; update only by explicit review."""\n'
                           'REVISIONS = ' + pprint.pformat(revisions, sort_dicts=False, width=88) + '\n')
    print(revisions)


if __name__ == '__main__':
    main()

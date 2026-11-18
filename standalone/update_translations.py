#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Update a Qt Linguist catalogue for the panel, preserving existing translations."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import tempfile


def literals(expr):
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        yield expr.value
    elif isinstance(expr, ast.IfExp):
        yield from literals(expr.body)
        yield from literals(expr.orelse)


def messages(source):
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and any(isinstance(k, ast.Name) and k.id == 'destinations' for k in node.targets):
            for name in node.value.elts:
                yield from literals(name)
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        name = node.func.id
        if name == 'tr' and node.args:
            yield from literals(node.args[0])
        if name in ('field', 'group', 'number', 'choices', 'check') and len(node.args) >= 2:
            yield from literals(node.args[1])
        if name == 'actions':
            for pair in node.args[1:]:
                if isinstance(pair, ast.Tuple):
                    yield from literals(pair.elts[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('locale', help='Qt locale such as fr or pt_BR')
    locale = parser.parse_args().locale
    if not re.fullmatch(r'[a-z]{2,3}(?:_[A-Za-z0-9]+)*', locale):
        parser.error('Invalid locale')
    root = Path(__file__).resolve().parent
    app = root / 'akousousin_app'
    sources = [app / 'panel.py', *app.glob('qt_*.py')]
    strings = sorted({s for path in sources for s in messages(path.read_text(encoding='utf-8'))})
    target = root / 'resources/translations' / ('akousousin_' + locale + '.ts')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stub = Path(tmp) / 'messages.cpp'
        stub.write_text('\n'.join('QT_TRANSLATE_NOOP("Panel", ' + json.dumps(s, ensure_ascii=False) + ');'
                                  for s in strings), encoding='utf-8')
        subprocess.run(['pyside6-lupdate', str(stub), '-locations', 'none', '-source-language', 'en',
                        '-target-language', locale, '-ts', str(target)], check=True)


if __name__ == '__main__':
    main()

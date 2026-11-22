#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Update Qt Linguist catalogues for the panel and tray, keeping existing translations.

    python standalone/update_translations.py es          # create or update akousousin_es.ts
    python standalone/update_translations.py --review es # write a side-by-side review table
    python standalone/update_translations.py --pseudo DIR # build a pseudo-translation for layout checks

Strings are found by the standard pyside6-lupdate: ``self.tr()`` inside Qt
classes and ``translate('Context', ...)`` elsewhere.
"""
import argparse
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ElementTree

ROOT = Path(__file__).resolve().parent
TRANSLATIONS = ROOT / 'resources/translations'


def sources():
    app = ROOT / 'akousousin_app'
    return sorted(str(path) for path in (app / 'ui').rglob('*.py'))


def update(locale):
    target = TRANSLATIONS / f'akousousin_{locale}.ts'
    TRANSLATIONS.mkdir(parents=True, exist_ok=True)
    subprocess.run(['pyside6-lupdate', *sources(), '-locations', 'none', '-no-obsolete',
                    '-source-language', 'en', '-target-language', locale, '-ts', str(target)], check=True)
    return target


def review(locale):
    """A Markdown table of every string, for proofreading without Qt Linguist."""
    target = TRANSLATIONS / f'akousousin_{locale}.ts'
    rows = ['| Context | English | Translation |', '| --- | --- | --- |']
    for context in ElementTree.parse(target).getroot().iter('context'):
        name = context.findtext('name')
        for message in context.iter('message'):
            cell = lambda value: (value or '').replace('|', '\\|').replace('\n', ' ')
            rows.append(f'| {name} | {cell(message.findtext("source"))} | {cell(message.findtext("translation"))} |')
    output = TRANSLATIONS / f'REVIEW-{locale}.md'
    output.write_text(f'# Akousousin translation review: {locale}\n\n' + '\n'.join(rows) + '\n', encoding='utf-8')
    return output


def pseudo(directory):
    """Longer, accented text makes untranslated strings and clipped layouts obvious."""
    accents = str.maketrans('aeiouAEIOUcnsy', 'áéîõüÁÉÎÕÜçñšý')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    ts = directory / 'akousousin_eo.ts'
    subprocess.run(['pyside6-lupdate', *sources(), '-locations', 'none', '-target-language', 'eo', '-ts', str(ts)], check=True)
    tree = ElementTree.parse(ts)
    for message in tree.getroot().iter('message'):
        source = message.findtext('source') or ''
        parts = re.split(r'(%\d|%n|<[^>]+>)', source)
        stretched = ''.join(part if re.fullmatch(r'%\d|%n|<[^>]+>', part) else part.translate(accents) for part in parts)
        translation = message.find('translation')
        translation.attrib.pop('type', None)
        translation.text = '[' + stretched + ' ~~~~]'
    tree.write(ts, encoding='utf-8', xml_declaration=True)
    subprocess.run(['pyside6-lrelease', str(ts), '-qm', str(ts.with_suffix('.qm'))], check=True)
    return ts.with_suffix('.qm')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('locale', nargs='?', help='Qt locale such as es or pt_BR')
    parser.add_argument('--review', action='store_true', help='Write REVIEW-<locale>.md beside the catalogue')
    parser.add_argument('--pseudo', metavar='DIR', help='Build a pseudo-translation .qm into DIR')
    options = parser.parse_args()
    if options.pseudo:
        print(pseudo(options.pseudo))
        return
    if not options.locale or not re.fullmatch(r'[a-z]{2,3}(?:_[A-Za-z0-9]+)*', options.locale):
        parser.error('Give a locale such as es')
    print(review(options.locale) if options.review else update(options.locale))


if __name__ == '__main__':
    main()

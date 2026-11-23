# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Wine prefixes are found where people keep them, hidden folders included."""
from pathlib import Path
import tempfile
import unittest

from akousousin_app import wine_prefixes


def prefix(path):
    (path / 'drive_c').mkdir(parents=True)
    (path / 'system.reg').write_text('WINE REGISTRY Version 2\n')
    return path


class FindTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)

    def test_finds_logos_hidden_and_tool_managed_prefixes(self):
        logos = prefix(self.home / 'LogosBible10/data/wine64_bottle')
        wine = prefix(self.home / '.wine')
        bottle = prefix(self.home / '.var/app/com.usebottles.bottles/data/bottles/bottles/Office')
        lutris = prefix(self.home / 'Games/some-game')
        (self.home / 'Projects/not-a-prefix/drive_c').mkdir(parents=True)  # no system.reg
        found = wine_prefixes.find(self.home)
        self.assertEqual(found[0], logos, 'visible app folders such as OuDedetai Logos come first')
        self.assertEqual(set(found), {logos, wine, bottle, lutris})

    def test_does_not_look_inside_a_prefix_or_too_deep(self):
        outer = prefix(self.home / 'apps/outer')
        prefix(outer / 'drive_c/users/nested')
        prefix(self.home / 'a/b/c/d/too-deep')
        self.assertEqual(wine_prefixes.find(self.home), [outer])

    def test_nothing_found_is_an_empty_list(self):
        self.assertEqual(wine_prefixes.find(self.home), [])

    def test_display_shortens_the_home_folder(self):
        self.assertEqual(wine_prefixes.display(self.home / '.wine', self.home), '~/.wine')
        self.assertEqual(wine_prefixes.display('/opt/wine', self.home), '/opt/wine')


if __name__ == '__main__':
    unittest.main()

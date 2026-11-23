# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""A remembered or requested voice that is not installed must not silence speech."""
import unittest

from akousousin_app.settings import usable_voice

CONFIG = {
    'voice': 'en_US-ljspeech-medium',
    'voices': {'en_US-ljspeech-medium': {'language': 'en_US'}, 'es_ES-davefx-medium': {'language': 'es_ES'}},
    # Both were chosen once and have since been removed.
    'language_voices': {'en_GB': 'en_GB-alan-medium', 'en_US': 'en_US-ljspeech-medium', 'de_DE': 'de_DE-thorsten-medium'},
}


class UsableVoiceTests(unittest.TestCase):
    def test_installed_request_wins(self):
        self.assertEqual(usable_voice(CONFIG, 'es_ES-davefx-medium', language='en-GB'), 'es_ES-davefx-medium')

    def test_unknown_voice_name_falls_back_to_the_language(self):
        self.assertEqual(usable_voice(CONFIG, 'english', language='es'), 'es_ES-davefx-medium')

    def test_removed_voice_for_a_language_falls_back_within_its_family(self):
        # Orca asks for en-GB; the British voice was removed; the US voice speaks.
        self.assertEqual(usable_voice(CONFIG, CONFIG['language_voices']['en_GB'], language='en-GB'), 'en_US-ljspeech-medium')

    def test_language_without_voices_uses_the_default(self):
        self.assertEqual(usable_voice(CONFIG, language='de_DE'), 'en_US-ljspeech-medium')

    def test_removed_default_uses_any_installed_voice(self):
        config = dict(CONFIG, voice='gone', voices={'es_ES-davefx-medium': {'language': 'es_ES'}})
        self.assertEqual(usable_voice(config, language='fr'), 'es_ES-davefx-medium')

    def test_nothing_installed(self):
        self.assertIsNone(usable_voice(dict(CONFIG, voices={}), 'en_US-ljspeech-medium', language='en'))


if __name__ == '__main__':
    unittest.main()

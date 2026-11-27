# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import unittest

from akousousin_app import speech_input
from akousousin_app.speech_input import Pause, Run


def source_of(source, run, start, end):
    a, b = run.source(start, end)
    return source[a:b]


class TextTests(unittest.TestCase):
    def test_plain_text_is_one_run_traced_character_by_character(self):
        [run] = speech_input.parse('Hello world', 'text', 'en-GB')
        self.assertEqual((run.text, run.language), ('Hello world', 'en_GB'))
        self.assertEqual(run.source(6, 11), (6, 11))

    def test_overlong_input_is_refused(self):
        with self.assertRaises(ValueError):
            speech_input.parse('a' * (speech_input.LONGEST_INPUT + 1))


class SsmlTests(unittest.TestCase):
    def parse(self, source):
        return speech_input.parse(source, 'ssml')

    def test_marks_are_placed_in_the_text_and_offsets_point_into_the_markup(self):
        source = '<speak>Hello <mark name="a"/>wide <mark name="b"/>world</speak>'
        [run] = self.parse(source)
        self.assertEqual(run.text, 'Hello wide world')
        self.assertEqual(run.marks, [(6, 'a'), (11, 'b')])
        self.assertEqual(source_of(source, run, 11, 16), 'world')

    def test_marks_at_the_very_start_and_end(self):
        source = '<speak><mark name="first"/>Hi<mark name="last"/></speak>'
        [run] = self.parse(source)
        self.assertEqual(run.marks, [(0, 'first'), (2, 'last')])
        [only] = self.parse('<speak><mark name="alone"/></speak>')
        self.assertEqual((only.text, only.marks), ('', [(0, 'alone')]))

    def test_entities_map_back_to_their_whole_reference(self):
        source = '<speak>Tom &amp; Jerry &#233;t&#xE9;</speak>'
        [run] = self.parse(source)
        self.assertEqual(run.text, 'Tom & Jerry été')
        index = run.text.index('&')
        self.assertEqual(source_of(source, run, index, index + 1), '&amp;')
        self.assertEqual(source_of(source, run, 12, 15), '&#233;t&#xE9;')

    def test_non_ascii_offsets_are_characters_not_bytes(self):
        source = '<speak>Ἐν ἀρχῇ <mark name="m"/>ἦν ὁ λόγος</speak>'
        [run] = self.parse(source)
        self.assertEqual(source_of(source, run, run.text.index('λόγος'), len(run.text)), 'λόγος')

    def test_breaks_and_sentences_divide_runs(self):
        items = self.parse('<speak><s>One</s><s>two</s> three<break time="250ms"/>four<break strength="strong"/></speak>')
        self.assertEqual([type(i).__name__ for i in items], ['Run', 'Run', 'Run', 'Pause', 'Run', 'Pause'])
        self.assertEqual([i.text if isinstance(i, Run) else i.milliseconds for i in items],
                         ['One', 'two', ' three', 250, 'four', 700])

    def test_prosody_and_language_start_runs_with_their_settings(self):
        items = self.parse('<speak xml:lang="en-US">Read <lang xml:lang="el">λόγος</lang> '
                           '<prosody rate="slow" volume="-6dB">slowly <prosody rate="200%">now</prosody></prosody></speak>')
        summary = [(i.text, i.language, round(i.rate, 3), round(i.volume, 3)) for i in items]
        self.assertEqual(summary, [('Read ', 'en_US', 1.0, 1.0), ('λόγος', 'el', 1.0, 1.0), (' ', 'en_US', 1.0, 1.0),
                                   ('slowly ', 'en_US', .75, .501), ('now', 'en_US', 1.5, .501)])

    def test_substitutions_are_spoken_and_traced_to_the_element(self):
        source = '<speak>See <sub alias="World Wide Web Consortium">W3C</sub> now</speak>'
        [run] = self.parse(source)
        self.assertEqual(run.text, 'See World Wide Web Consortium now')
        start = run.text.index('World')
        self.assertIn('W3C', source_of(source, run, start, start + 5))

    def test_characters_are_spelled(self):
        source = '<speak><say-as interpret-as="characters">ab?</say-as></speak>'
        [run] = self.parse(source)
        self.assertEqual(run.text, 'a b question mark')
        self.assertEqual(source_of(source, run, run.text.index('question'), len(run.text)), '?')

    def test_unknown_elements_are_spoken_as_their_text_and_metadata_is_not(self):
        [run] = self.parse('<speak><emphasis>very</emphasis> <audio src="x.wav">beep</audio><desc>no</desc></speak>')
        self.assertEqual(run.text, 'very beep')

    def test_unsafe_or_invalid_ssml_is_refused(self):
        for source in ('<!DOCTYPE speak [<!ENTITY x "y">]><speak>&x;</speak>',
                       '<speak>unclosed', '<p>not speak</p>',
                       '<speak><mark name=""/></speak>',
                       '<speak>' + '<s>' * 100 + 'deep' + '</s>' * 100 + '</speak>'):
            with self.subTest(source=source[:40]), self.assertRaises(ValueError):
                self.parse(source)

    def test_cdata_and_line_endings_keep_their_place(self):
        source = '<speak>a\r\nb <![CDATA[<raw>]]> c</speak>'
        [run] = self.parse(source)
        self.assertEqual(run.text, 'a\nb <raw> c')
        self.assertEqual(source_of(source, run, run.text.index('<raw>'), run.text.index('<raw>') + 5), '<raw>')


class FragmentTests(unittest.TestCase):
    def test_sapi_fragments_keep_the_engines_offsets(self):
        items = speech_input.parse([
            {'text': 'Hello ', 'offset': 10, 'length_scale': 1.0, 'language': 'en-US'},
            {'bookmark': 'b1'},
            {'text': 'world', 'offset': 30, 'length_scale': .5},
            {'silence': 300},
            {'text': 'again', 'offset': 50}], 'fragments')
        self.assertEqual([type(i).__name__ for i in items], ['Run', 'Run', 'Pause', 'Run'])
        first, second, pause, third = items
        # The bookmark ends the first run: heard after "Hello", before "world".
        self.assertEqual((first.text, first.source(0, 5), first.marks), ('Hello ', (10, 15), [(6, 'b1')]))
        self.assertEqual((second.text, second.rate, second.marks, second.source(0, 5)), ('world', 2.0, [], (30, 35)))
        self.assertEqual(pause.milliseconds, 300)

    def test_bad_fragments_are_refused(self):
        for fragments in ('text', [1], [{'text': 5}], [{'text': 'a', 'offset': -1}], [{'silence': 10 ** 9}],
                          [{'text': 'a', 'length_scale': float('nan')}], [{'bookmark': 3}]):
            with self.subTest(fragments=fragments), self.assertRaises(ValueError):
                speech_input.parse(fragments, 'fragments')


if __name__ == '__main__':
    unittest.main()

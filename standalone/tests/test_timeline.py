# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import unittest

from akousousin_app import timeline


def ph(text):
    return list(text)


class TokenTests(unittest.TestCase):
    def test_tokens_keep_punctuation_for_the_phonemizer(self):
        text = 'Dr. Smith paid $3.50, "quietly".'
        self.assertEqual([text[s:e] for s, e in timeline.tokens(text)], ['Dr.', 'Smith', 'paid', '$3.50,', '"quietly".'])

    def test_punctuation_alone_is_silent(self):
        for token, expected in (('–', True), ('?', True), ('...', True), ('&', False), ('%', False), ('$5', False), ('a.', False)):
            self.assertEqual(timeline.silent(token), expected, token)

    def test_ranges_are_trimmed_of_punctuation_but_not_spoken_symbols(self):
        for text, expected in (('"Hello"', 'Hello'), ('(quietly)', 'quietly'), ('dog.', 'dog'),
                               ('$3.50,', '$3.50'), ('50%', '50%'), ("O'Neill's", "O'Neill's"),
                               ('—', None), ('...', None), ('«très»', 'très')):
            span = timeline.trimmed(text, 0, len(text))
            self.assertEqual(text[span[0]:span[1]] if span else None, expected, text)


class ChunkTests(unittest.TestCase):
    def test_short_sentences_stay_whole(self):
        sentences = [ph('ðə kwɪk bɹaʊn fɑːks.'), ph('haɪ.')]
        self.assertEqual(list(timeline.chunks(sentences)), sentences)

    def test_long_sentences_split_after_clause_punctuation(self):
        clause = ph('wʌn tuː θɹiː foːɹ faɪv,') + [' ']
        sentence = clause * 8 + ph('ɛnd.')
        pieces = list(timeline.chunks([sentence], longest=50))
        self.assertGreater(len(pieces), 1)
        self.assertEqual(''.join(''.join(p) for p in pieces).replace(' ', ''), ''.join(sentence).replace(' ', ''))
        for piece in pieces[:-1]:
            self.assertEqual(piece[-1], ',')
            self.assertLessEqual(len(piece), 50 + len(clause))
        self.assertFalse(any(piece[0] == ' ' for piece in pieces))

    def test_a_long_sentence_without_clauses_is_not_cut_mid_word(self):
        sentence = ph('a' * 200 + '.')
        self.assertEqual(list(timeline.chunks([sentence], longest=50)), [sentence])


class MatchTests(unittest.TestCase):
    def owners(self, sentence, words, *chunks):
        matcher = timeline.Matcher([ph(word) for word in words])
        return [matcher.chunk(ph(chunk)) for chunk in (chunks or (sentence,))]

    def test_one_to_one(self):
        [owners] = self.owners('ðə kwɪk bɹaʊn.', ['ðə', 'kwɪk', 'bɹaʊn.'])
        self.assertEqual(owners, [0, 0, None, 1, 1, 1, 1, None, 2, 2, 2, 2, 2, None])

    def test_fused_words_are_split(self):
        # espeak-ng phonemizes "in the" as one word, ɪnðə
        [owners] = self.owners('ɹuːld ɪnðə sɪksti', ['ɹuːld', 'ɪn', 'ðə', 'sɪksti'])
        text = 'ɹuːld ɪnðə sɪksti'
        by_word = {}
        for character, owner in zip(text, owners):
            by_word.setdefault(owner, '')
            by_word[owner] += character
        self.assertEqual({k: v for k, v in by_word.items() if k is not None}, {0: 'ɹuːld', 1: 'ɪn', 2: 'ðə', 3: 'sɪksti'})

    def test_an_expansion_belongs_to_its_one_written_word(self):
        # "in 1984," : the number is three spoken words
        [owners] = self.owners('ɪn naɪntiːn eɪɾi fɔːɹ,', ['ɪn', 'naɪntiːn eɪɾi fɔːɹ,'])
        self.assertEqual(set(o for o in owners if o is not None), {0, 1})
        self.assertEqual(owners[3:], [1 if c not in ' ,' else None for c in 'naɪntiːn eɪɾi fɔːɹ,'])

    def test_stress_marks_go_with_the_syllable_they_stress(self):
        [owners] = self.owners('ðə ˈkwɪk', ['ðə', 'kwɪk'])  # the word alone may lack the stress mark
        self.assertEqual(owners[3], 1)

    def test_words_without_phonemes_are_skipped(self):
        matcher = timeline.Matcher([ph('bʌt'), [], ph('naʊ')])  # "but – now"
        owners = matcher.chunk(ph('bʌt naʊ'))
        self.assertEqual(owners, [0, 0, 0, None, 2, 2, 2])

    def test_small_differences_from_context_still_land_on_the_right_word(self):
        # Alone "the" is ðiː; before a consonant in the sentence it is ðə.
        [owners] = self.owners('ðə dɔɡ', ['ðiː', 'dɔɡ'])
        self.assertEqual(owners, [0, 0, None, 1, 1, 1])

    def test_chunks_continue_where_the_last_one_ended(self):
        words = ['wʌn', 'tuː,', 'θɹiː', 'foːɹ.']
        first, second = self.owners(None, words, 'wʌn tuː,', 'θɹiː foːɹ.')
        self.assertEqual(set(o for o in first if o is not None), {0, 1})
        self.assertEqual(set(o for o in second if o is not None), {2, 3})

    def test_a_repeated_word_is_not_matched_ahead_of_its_place(self):
        words = ['hoʊli,'] * 3 + ['lɔːɹd.']
        a, b, c = self.owners(None, words, 'hoʊli,', 'hoʊli,', 'hoʊli, lɔːɹd.')
        self.assertEqual({o for o in a if o is not None}, {0})
        self.assertEqual({o for o in b if o is not None}, {1})
        self.assertEqual({o for o in c if o is not None}, {2, 3})


class SpanTests(unittest.TestCase):
    def test_spans_follow_the_samples_and_pauses_fall_between_words(self):
        owners = [0, 0, None, 1, 1, None]
        samples = [100, 100, 300, 50, 50, 400]
        self.assertEqual(timeline.word_spans(owners, samples), [(0, 0, 200), (1, 500, 600)])

    def test_silent_tokens_get_no_span(self):
        self.assertEqual(timeline.word_spans([0, 1], [100, 0]), [(0, 0, 100)])


try:
    from piper import espeakbridge
    from piper.phonemize_espeak import ESPEAK_DATA_DIR
except ImportError:
    espeakbridge = None


@unittest.skipIf(espeakbridge is None, 'needs Piper')
class RealPhonemizerTests(unittest.TestCase):
    """Every word that is spoken gets a span, in the order written, across languages and awkward text."""
    CASES = {
        'en-us': ['The quick brown fox jumps over the lazy dog.',
                  'Henry VIII ruled in the 1500s, and in 1984, Dr. Smith paid $3.50 for 2 books at 10:30am.',
                  "It's a well-known fact; e.g. the U.S.A. isn't Europe!",
                  'Read John 3:16, then Rom. 8:28 – both verses.',
                  'Visit https://example.org/page or email a@b.com.',
                  'Holy, holy, holy, Lord God Almighty.',
                  'NASA, the FBI and UTF-8 in C++ & Logos 10, about 50% off.'],
        'fr': ['Les amis sont arrivés à 8 heures.', "Qu'est-ce que c'est ?"],
        'de': ['Am 3. Mai 2024 kostete es 12,50 €.'],
        'es': ['El 25 de diciembre de 2023 llegaron 3 personas.'],
        'pt': ['O Sr. Silva pagou R$ 10,50 em 1º de maio.'],
        'el': ['Ἐν ἀρχῇ ἦν ὁ λόγος, καὶ ὁ λόγος ἦν πρὸς τὸν θεόν.'],
    }

    @classmethod
    def setUpClass(cls):
        espeakbridge.initialize(str(ESPEAK_DATA_DIR))

    def phonemize(self, voice, text):
        espeakbridge.set_voice(voice)
        sentences = []
        for phonemes, terminator, end in espeakbridge.get_phonemes(text):
            sentences.append(timeline.normalized(list(phonemes)) + [terminator])
        return sentences

    def test_words_are_found_in_order(self):
        for voice, texts in self.CASES.items():
            for text in texts:
                with self.subTest(voice=voice, text=text):
                    spans = timeline.tokens(text)
                    words = [[] if timeline.silent(text[s:e]) else sum(self.phonemize(voice, text[s:e]), [])
                             for s, e in spans]
                    matcher = timeline.Matcher(words)
                    heard = []
                    for chunk in timeline.chunks(self.phonemize(voice, text)):
                        owners = matcher.chunk(chunk)
                        heard.extend(token for token, _, _ in timeline.word_spans(owners, [1] * len(chunk)))
                    spoken = [i for i, w in enumerate(words) if any(p not in timeline.SEPARATORS for p in w)]
                    self.assertEqual(sorted(set(heard)), spoken)
                    self.assertEqual(heard, sorted(heard))


if __name__ == '__main__':
    unittest.main()

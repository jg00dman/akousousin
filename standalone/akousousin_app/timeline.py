# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Where each word is heard: matching a voice's phonemes back to the words of the text.

The phonemizer (espeak-ng for most voices) turns whole sentences into phonemes
but doesn't say which word each phoneme came from. Phonemizing each word on its
own and matching those phonemes, character by character, against the
sentence's recovers it, even where the phonemizer fuses short words ("in the"
becomes one phoneme word) or expands one ("1984" becomes three). The voice
reports how many audio samples each phoneme lasts, so each word's place in the
audio follows exactly.

Everything here is plain Python over lists of phoneme strings, so it is tested
without a voice.
"""
from difflib import SequenceMatcher
import re
import unicodedata

# Phonemes that separate words or carry punctuation's pauses: not matched, owned by no word.
SEPARATORS = frozenset(' \t\n') | frozenset(',.;:!?¡¿—–-…"\'()[]{}«»“”‘’')
# Stress and length marks belong to a word but aren't matched: they take the owner of their neighbour.
BEFORE = frozenset('ˈˌ')          # stress marks come before the syllable they stress
AFTER = frozenset('ːˑ̩̯̃͜͡‿')   # length, nasal, syllabic, non-syllabic, ties
# Punctuation that is spoken, and so stays inside a word's range.
SPOKEN = frozenset('%‰‱&@#§')

# Chunk length, in phonemes, above which a sentence is split at clause boundaries.
# About five seconds of speech at normal speed (13 phonemes a second, measured).
LONGEST = 80
CLAUSE_ENDS = frozenset(',;:—–')


def tokens(text):
    """(start, end) of each whitespace-separated token. Punctuation stays attached, for the phonemizer's sake."""
    return [(match.start(), match.end()) for match in re.finditer(r'\S+', text)]


def trimmed(text, start, end):
    """The range without leading and trailing punctuation, or None if nothing would be left."""
    def punctuation(character):
        return unicodedata.category(character).startswith('P') and character not in SPOKEN
    while start < end and punctuation(text[start]):
        start += 1
    while end > start and punctuation(text[end - 1]):
        end -= 1
    return (start, end) if start < end else None


def silent(token):
    """Whether a token is only punctuation, heard as a pause rather than words.

    Phonemized alone, espeak-ng reads punctuation out by name ("en dash"); in a
    sentence it is a pause. Such tokens are matched as having no phonemes.
    """
    return all(unicodedata.category(c).startswith('P') and c not in SPOKEN for c in token)


def normalized(phonemes):
    """One phoneme per code point, decomposed, as Piper's phonemizers produce them."""
    return [part for phoneme in phonemes for part in unicodedata.normalize('NFD', phoneme)]


def chunks(sentences, longest=LONGEST):
    """Split long sentences after clause punctuation, so no chunk is much longer than ``longest`` phonemes.

    Short sentences are left whole. A clause is never split inside, so the voice's
    phrasing is kept; the split falls where the voice pauses anyway.
    """
    for sentence in sentences:
        if len(sentence) <= longest:
            if sentence:
                yield sentence
            continue
        piece, last_break = [], None
        for phoneme in sentence:
            piece.append(phoneme)
            if phoneme in CLAUSE_ENDS:
                last_break = len(piece)
            if len(piece) >= longest and last_break:
                yield piece[:last_break]
                piece, last_break = piece[last_break:], None
                while piece and piece[0].isspace():
                    piece.pop(0)
        if piece:
            yield piece


class Matcher:
    """Assigns each phoneme of each chunk, in order, to the token it was spoken for.

    ``token_phonemes[i]`` are the phonemes of token i phonemized on its own. Chunks
    are matched against a window of the tokens that follow the previous chunk,
    which keeps the work linear for long texts and stops a repeated word from
    being matched far ahead.
    """
    def __init__(self, token_phonemes):
        self.keys = []      # matchable phonemes of each token
        for phonemes in token_phonemes:
            self.keys.append([p for p in normalized(phonemes) if p not in SEPARATORS | BEFORE | AFTER])
        self.cursor = 0     # first token the next chunk can belong to

    def chunk(self, phonemes):
        """The owning token index (or None) for each phoneme of the next chunk."""
        owners = [None] * len(phonemes)
        keyed = [(index, phoneme) for index, phoneme in enumerate(phonemes)
                 if phoneme not in SEPARATORS | BEFORE | AFTER]
        if keyed and self.cursor < len(self.keys):
            flat, flat_owner = self._window(len(keyed))
            matcher = SequenceMatcher(None, [phoneme for _, phoneme in keyed], flat, autojunk=False)
            assigned = [None] * len(keyed)
            for tag, a0, a1, b0, b1 in matcher.get_opcodes():
                if tag == 'equal':
                    for k in range(a0, a1):
                        assigned[k] = flat_owner[b0 + k - a0]
                elif tag == 'replace':
                    for k in range(a0, a1):  # spread the differing run proportionally
                        assigned[k] = flat_owner[b0 + (k - a0) * (b1 - b0) // (a1 - a0)]
            # Phonemes the words alone didn't produce take the word before them (or after, at the start).
            previous = None
            for k, owner in enumerate(assigned):
                if owner is None:
                    assigned[k] = previous
                previous = assigned[k]
            following = None
            for k in range(len(assigned) - 1, -1, -1):
                if assigned[k] is None:
                    assigned[k] = following
                following = assigned[k]
            for (index, _), owner in zip(keyed, assigned):
                owners[index] = owner
            used = [owner for owner in assigned if owner is not None]
            if used:
                # The next chunk may begin inside the last word of this one, so keep it in reach.
                self.cursor = max(self.cursor, max(used))
                if self._finished(max(used), assigned):
                    self.cursor = max(used) + 1
        self._attach_marks(phonemes, owners)
        return owners

    def _window(self, size):
        """Matchable phonemes of the next tokens, enough to cover a chunk of ``size`` with room to spare."""
        flat, owner, token = [], [], self.cursor
        enough = size + size // 4 + 8
        while token < len(self.keys) and (len(flat) < enough or not self.keys[token]):
            flat.extend(self.keys[token])
            owner.extend([token] * len(self.keys[token]))
            token += 1
        return flat, owner

    def _finished(self, token, assigned):
        """Whether this chunk used all of the last token's phonemes."""
        return assigned.count(token) >= len(self.keys[token])

    @staticmethod
    def _attach_marks(phonemes, owners):
        for index, phoneme in enumerate(phonemes):
            if owners[index] is not None or phoneme in SEPARATORS:
                continue
            if phoneme in BEFORE:
                neighbour = next((owners[j] for j in range(index + 1, len(phonemes))
                                  if owners[j] is not None or phonemes[j] in SEPARATORS), None)
            else:
                neighbour = next((owners[j] for j in range(index - 1, -1, -1)
                                  if owners[j] is not None or phonemes[j] in SEPARATORS), None)
            owners[index] = neighbour


def word_spans(owners, samples):
    """(token, first sample, end sample) for each token heard in a chunk, in order.

    ``samples[i]`` is how many audio samples phoneme i lasts (as the voice reports,
    without the start and end markers).
    """
    spans, position = {}, 0
    for owner, count in zip(owners, samples):
        if owner is not None:
            start, end = spans.get(owner, (position, position + count))
            spans[owner] = (min(start, position), max(end, position + count))
        position += count
    return sorted(((token, start, end) for token, (start, end) in spans.items() if end > start),
                  key=lambda span: (span[1], span[0]))

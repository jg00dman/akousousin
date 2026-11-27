# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""What to say, from plain text, SSML or SAPI's fragments, with every character traced back to its source.

All front ends hand their input to the voice service in one of three forms,
and it is turned into the same thing: a list of runs (text spoken with one
voice, speed and volume, with the marks inside it) and pauses. Each character
of a run's text carries the range of the original input it came from, so word
and mark events can report positions in the text the caller sent, markup
included. That is what Spiel specifies, and what SAPI's events need.
"""
from bisect import bisect_right
from dataclasses import dataclass, field
import math
import re
import unicodedata
from xml.parsers import expat

LONGEST_INPUT = 200_000         # characters of input in one request
MOST_MARKS = 10_000
DEEPEST = 64                    # nested SSML elements
LONGEST_PAUSE = 10_000          # milliseconds for one break or silence
MOST_PAUSE = 60_000             # milliseconds of breaks in one request
SLOWEST, FASTEST = .25, 4.0     # speed multipliers markup may ask for, before the voice's own limits
LOUDEST = 2.0


@dataclass
class Run:
    """Text spoken with one voice, speed and volume.

    ``starts[i]`` and ``ends[i]`` are the range of the input that character i
    came from. ``marks`` are (index into text, name), in order.
    """
    text: str = ''
    starts: list = field(default_factory=list)
    ends: list = field(default_factory=list)
    language: str = ''
    rate: float = 1.0
    volume: float = 1.0
    marks: list = field(default_factory=list)

    def source(self, start, end):
        """The input range that text[start:end] came from."""
        return self.starts[start], self.ends[end - 1]

    def add(self, text, starts, ends):
        self.text += text
        self.starts.extend(starts)
        self.ends.extend(ends)


@dataclass
class Pause:
    milliseconds: int


def from_text(text, language=''):
    _check_length(text)
    return [Run(text, list(range(len(text))), list(range(1, len(text) + 1)), language=language)]


class _Builder:
    """Collects text, marks and pauses into runs, starting a new run whenever voice, speed or volume change."""
    def __init__(self):
        self.items, self.run, self.pending = [], None, []
        self.marks = self.paused = 0

    def text(self, text, starts, ends, props):
        if not text:
            return
        key = (props['language'], props['rate'], props['volume'])
        if self.run is None or (self.run.language, self.run.rate, self.run.volume) != key:
            self.close()
            self.run = Run(language=key[0], rate=key[1], volume=key[2])
            self.items.append(self.run)
        if self.pending:
            self.run.marks.extend((len(self.run.text), name) for name in self.pending)
            self.pending = []
        self.run.add(text, starts, ends)

    def mark(self, name):
        if not name or len(name) > 256 or any(c in name for c in '\r\n\x00'):
            raise ValueError('Invalid mark')
        self.marks += 1
        if self.marks > MOST_MARKS:
            raise ValueError('Too many marks')
        if self.run is not None:
            self.run.marks.append((len(self.run.text), name))  # before whatever text comes next in this run
        else:
            self.pending.append(name)

    def pause(self, milliseconds):
        milliseconds = max(0, min(LONGEST_PAUSE, int(milliseconds)))
        self.paused += milliseconds
        if self.paused > MOST_PAUSE:
            raise ValueError('Too much silence')
        self.close()
        if milliseconds:
            self.items.append(Pause(milliseconds))

    def close(self):
        """End the current run; later text starts a new one (a sentence or paragraph boundary)."""
        self.run = None

    def finish(self):
        if self.pending:
            self.items.append(Run(marks=[(0, name) for name in self.pending]))
            self.pending = []
        return self.items


def from_fragments(fragments):
    """SAPI's fragments, as the engine sends them.

    Each is {"text", "offset", "length_scale", "language"}, {"silence": ms} or
    {"bookmark": name}. ``offset`` is where the fragment starts in whatever
    numbering the engine uses; events report offset + position in the fragment.
    """
    if not isinstance(fragments, list) or len(fragments) > MOST_MARKS:
        raise ValueError('Invalid fragments')
    builder, total = _Builder(), 0
    for fragment in fragments:
        if not isinstance(fragment, dict):
            raise ValueError('Invalid fragment')
        if 'silence' in fragment:
            builder.pause(_number(fragment['silence'], 0, LONGEST_PAUSE))
        elif 'bookmark' in fragment:
            if not isinstance(fragment['bookmark'], str):
                raise ValueError('Invalid bookmark')
            builder.mark(fragment['bookmark'])
        else:
            text, offset = fragment.get('text'), fragment.get('offset', 0)
            if not isinstance(text, str) or isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                raise ValueError('Invalid fragment')
            total += len(text)
            _check_length('', total)
            rate = 1 / _number(fragment.get('length_scale', 1), .1, 10)
            language = fragment.get('language', '')
            if not isinstance(language, str):
                raise ValueError('Invalid language')
            builder.text(text, [offset + i for i in range(len(text))], [offset + i + 1 for i in range(len(text))],
                         {'language': _language(language), 'rate': rate, 'volume': 1.0})
    return builder.finish()


def from_ssml(source):
    """SSML, as Orca and Spiel send it. Unknown elements are spoken as their text; DTDs and entities are refused."""
    _check_length(source)
    data = source.encode('utf-8')
    # The input character at each UTF-8 byte offset expat reports.
    byte_starts, position = [], 0
    for character in source:
        byte_starts.append(position)
        position += len(character.encode('utf-8'))

    def character_at(byte_index):
        return bisect_right(byte_starts, byte_index) - 1

    builder = _Builder()
    stack = [{'language': '', 'rate': 1.0, 'volume': 1.0, 'skip': False, 'alias': None, 'spell': False}]
    parser = expat.ParserCreate()
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    seen = {'root': False}

    def refuse(*_):
        raise ValueError('XML declarations and entities are not supported')
    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    parser.ExternalEntityRefHandler = refuse

    def start(name, attributes):
        if len(stack) > DEEPEST:
            raise ValueError('SSML is nested too deeply')
        name = name.rsplit(':', 1)[-1]
        if not seen['root']:
            seen['root'] = True
            if name != 'speak':
                raise ValueError('SSML must start with <speak>')
        props = dict(stack[-1], alias=None)
        if 'xml:lang' in attributes:
            props['language'] = _language(attributes['xml:lang'])
        if name in ('p', 's', 'paragraph', 'sentence'):
            builder.close()
        elif name == 'mark':
            builder.mark(attributes.get('name', ''))
        elif name == 'break':
            builder.pause(_break(attributes))
        elif name == 'prosody':
            props['rate'] = _clamp(props['rate'] * _rate(attributes.get('rate', '')), SLOWEST, FASTEST)
            props['volume'] = _clamp(props['volume'] * _volume(attributes.get('volume', '')), 0, LOUDEST)
        elif name == 'sub' and 'alias' in attributes:
            props['alias'] = attributes['alias']
            props['skip'] = True  # the alias is spoken instead of the content
            props['alias_at'] = character_at(parser.CurrentByteIndex)
        elif name == 'say-as' and attributes.get('interpret-as', '') in ('characters', 'spell-out', 'letters'):
            props['spell'] = True
        elif name in ('desc', 'metadata', 'lexicon', 'meta'):
            props['skip'] = True
        stack.append(props)

    def end(name):
        props = stack.pop()
        name = name.rsplit(':', 1)[-1]
        if props.get('alias') is not None:
            at, until = props['alias_at'], character_at(parser.CurrentByteIndex)
            alias = props['alias']
            builder.text(alias, [at] * len(alias), [max(at + 1, until)] * len(alias), props)
        if name in ('p', 's', 'paragraph', 'sentence'):
            builder.close()

    def text(data):
        props = stack[-1]
        if props['skip'] or not data:
            return
        at = character_at(parser.CurrentByteIndex)
        if source.startswith('&', at) and _ENTITY.match(source, at):
            # A character reference: the one character came from all of "&amp;".
            until = _ENTITY.match(source, at).end()
            starts, ends = [at] * len(data), [until] * len(data)
        elif source[at:at + len(data)] == data:
            starts = list(range(at, at + len(data)))
            ends = [i + 1 for i in starts]
        else:
            # A normalised line ending, or a piece expat reports from one place.
            starts, ends = [at] * len(data), [at + 1] * len(data)
        if props['spell']:
            data, starts, ends = spelled(data, starts, ends)
        builder.text(data, starts, ends, props)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = text
    try:
        parser.Parse(data, True)
    except expat.ExpatError as error:
        raise ValueError(f'Invalid SSML: {error}') from error
    return builder.finish()


def parse(input, kind='text', language=''):
    if kind == 'text':
        if not isinstance(input, str):
            raise ValueError('Invalid text')
        return from_text(input, _language(language))
    if kind == 'ssml':
        if not isinstance(input, str):
            raise ValueError('Invalid SSML')
        return from_ssml(input)
    if kind == 'fragments':
        return from_fragments(input)
    raise ValueError('Unknown input format')


def looks_like_ssml(text):
    return text.lstrip().startswith(('<speak', '<?xml'))


def spelled(text, starts, ends):
    """Each character spoken on its own: letters and digits as themselves, anything else by name."""
    out, out_starts, out_ends = [], [], []
    for character, start, end in zip(text, starts, ends):
        if character.isspace():
            continue
        spoken = character if character.isalnum() else unicodedata.name(character, character).lower()
        if out:
            out.append(' ')
            out_starts.append(start)
            out_ends.append(end)
        out.extend(spoken)
        out_starts.extend([start] * len(spoken))
        out_ends.extend([end] * len(spoken))
    return ''.join(out), out_starts, out_ends


def _check_length(text, length=None):
    if (len(text) if length is None else length) > LONGEST_INPUT:
        raise ValueError('Input is too long')


def _number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('Invalid number')
    return value


def _clamp(value, low, high):
    return max(low, min(high, value))


def _language(tag):
    """A BCP 47 tag (en-GB) as the settings write languages (en_GB)."""
    tag = (tag or '').strip().replace('-', '_')
    if not tag:
        return ''
    if len(tag) > 35 or not re.fullmatch(r'[A-Za-z]{2,8}(_[A-Za-z0-9]{1,8})*', tag):
        raise ValueError('Invalid language')
    parts = tag.split('_')
    return '_'.join([parts[0].lower()] + [p.upper() if len(p) == 2 else p for p in parts[1:]])


_ENTITY = re.compile(r'&(?:#[0-9]+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);')
_RATES = {'x-slow': .5, 'slow': .75, 'medium': 1.0, 'default': 1.0, 'fast': 1.5, 'x-fast': 2.0}
_VOLUMES = {'silent': 0.0, 'x-soft': .3, 'soft': .6, 'medium': 1.0, 'default': 1.0, 'loud': 1.3, 'x-loud': 1.6}
_STRENGTHS = {'none': 0, 'x-weak': 100, 'weak': 200, 'medium': 400, 'strong': 700, 'x-strong': 1000}


def _rate(value):
    value = value.strip()
    if not value:
        return 1.0
    if value in _RATES:
        return _RATES[value]
    percent = re.fullmatch(r'([+-]?)(\d+(?:\.\d+)?)%', value)
    if percent:
        sign, amount = percent.groups()
        amount = float(amount) / 100
        return 1 + amount if sign == '+' else 1 - amount if sign == '-' else amount
    try:
        number = float(value)
    except ValueError:
        return 1.0
    return number if math.isfinite(number) and number > 0 else 1.0


def _volume(value):
    value = value.strip()
    if not value:
        return 1.0
    if value in _VOLUMES:
        return _VOLUMES[value]
    decibels = re.fullmatch(r'([+-]?\d+(?:\.\d+)?)dB', value)
    if decibels:
        return 10 ** (float(decibels.group(1)) / 20)
    percent = re.fullmatch(r'([+-]?)(\d+(?:\.\d+)?)%?', value)
    if percent:
        sign, amount = percent.groups()
        amount = float(amount) / 100
        return 1 + amount if sign == '+' else 1 - amount if sign == '-' else amount
    return 1.0


def _break(attributes):
    time = attributes.get('time', '').strip()
    match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(ms|s)', time)
    if match:
        amount, unit = match.groups()
        return float(amount) * (1000 if unit == 's' else 1)
    return _STRENGTHS.get(attributes.get('strength', 'medium'), 400)

# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Readable microphone and Whisper-language choices without importing inference."""
import subprocess

# ISO/Whisper codes and language names are data; kept in sync with the pinned
# faster-whisper tokenizer. In particular Whisper uses 'jw' for Javanese.
LANGUAGES = dict(item.split(':', 1) for item in '''af:Afrikaans
am:Amharic
ar:Arabic
as:Assamese
az:Azerbaijani
ba:Bashkir
be:Belarusian
bg:Bulgarian
bn:Bengali
bo:Tibetan
br:Breton
bs:Bosnian
ca:Catalan
cs:Czech
cy:Welsh
da:Danish
de:German
el:Greek
en:English
es:Spanish
et:Estonian
eu:Basque
fa:Persian
fi:Finnish
fo:Faroese
fr:French
gl:Galician
gu:Gujarati
ha:Hausa
haw:Hawaiian
he:Hebrew
hi:Hindi
hr:Croatian
ht:Haitian Creole
hu:Hungarian
hy:Armenian
id:Indonesian
is:Icelandic
it:Italian
ja:Japanese
jw:Javanese
ka:Georgian
kk:Kazakh
km:Khmer
kn:Kannada
ko:Korean
la:Latin
lb:Luxembourgish
ln:Lingala
lo:Lao
lt:Lithuanian
lv:Latvian
mg:Malagasy
mi:Maori
mk:Macedonian
ml:Malayalam
mn:Mongolian
mr:Marathi
ms:Malay
mt:Maltese
my:Myanmar
ne:Nepali
nl:Dutch
nn:Norwegian Nynorsk
no:Norwegian
oc:Occitan
pa:Punjabi
pl:Polish
ps:Pashto
pt:Portuguese
ro:Romanian
ru:Russian
sa:Sanskrit
sd:Sindhi
si:Sinhala
sk:Slovak
sl:Slovenian
sn:Shona
so:Somali
sq:Albanian
sr:Serbian
su:Sundanese
sv:Swedish
sw:Swahili
ta:Tamil
te:Telugu
tg:Tajik
th:Thai
tk:Turkmen
tl:Tagalog
tr:Turkish
tt:Tatar
uk:Ukrainian
ur:Urdu
uz:Uzbek
vi:Vietnamese
yi:Yiddish
yo:Yoruba
zh:Chinese
yue:Cantonese'''.splitlines())
AUTOMATIC = 'Multilingual (auto) — detect once per session'


def language_caption(code):
    if not code:
        return AUTOMATIC
    base = code.replace('_', '-').split('-')[0].lower()
    return f'{LANGUAGES[base]} ({code})' if base in LANGUAGES else code


def language_choices(query=''):
    query = query.strip().casefold()
    if query in LANGUAGES:
        return [(query, language_caption(query))]
    values = [('', AUTOMATIC), *sorted(((code, language_caption(code)) for code in LANGUAGES), key=lambda item: item[1].casefold())]
    return [(code, caption) for code, caption in values if not query or query in caption.casefold()]


def is_monitor(source):
    return source.get('name', '').endswith('.monitor') or source.get('monitor_of_sink') not in (None, -1, '-1', 4294967295, '4294967295', 'n/a')


def microphone_choices(sources, default=''):
    by_name = {source['name']: source for source in sources if isinstance(source, dict) and isinstance(source.get('name'), str)}
    current = by_name.get(default)
    default_caption = 'System default'
    if current:
        default_caption += ' — ' + (current.get('description') or current['name'])
        if is_monitor(current):
            default_caption += ' (speaker monitor)'
    values = [('', default_caption)]
    seen = {default_caption}
    for source in sorted(by_name.values(), key=lambda item: (item.get('description') or item['name'], item['name'])):
        if is_monitor(source):
            continue
        caption = source.get('description') or source['name']
        base = caption
        number = 2
        while caption in seen:
            caption = f'{base} — {number}'; number += 1
        seen.add(caption)
        values.append((source['name'], caption))
    return values


def discover_microphones():
    """Microphones from PipeWire (natively) or PulseAudio, whichever is running."""
    from akousousin_backend.audio_system import AudioUnavailable, list_sources
    try:
        return microphone_choices(*list_sources())
    except AudioUnavailable:
        raise
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise RuntimeError('Could not list microphones. Check that PipeWire or PulseAudio is running, then Refresh.') from error

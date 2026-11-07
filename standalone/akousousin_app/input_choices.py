# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Readable microphone and Whisper-language choices without importing inference."""
import json
import subprocess
import tkinter as tk
from tkinter import ttk

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
    try:
        result = subprocess.run(['pactl', '--format=json', 'list', 'sources'],
                                capture_output=True, text=True, check=True, timeout=3)
        sources = json.loads(result.stdout)
        if not isinstance(sources, list):
            raise ValueError('Invalid source list')
        try:
            default = subprocess.run(['pactl', 'get-default-source'], capture_output=True,
                                     text=True, check=True, timeout=3).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            default = ''
        return microphone_choices(sources, default)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise RuntimeError('Could not list microphones. Check PipeWire and pulseaudio-utils, then Refresh.') from error


class LanguagePicker(ttk.Frame):
    def __init__(self, parent, variable, changed=lambda: None):
        super().__init__(parent)
        self.variable, self.changed = variable, changed
        self.caption = tk.StringVar(value=language_caption(variable.get()))
        variable.trace_add('write', lambda *_: self.caption.set(language_caption(variable.get())))
        ttk.Entry(self, textvariable=self.caption, state='readonly').pack(side='left', fill='x', expand=True)
        ttk.Button(self, text='Choose…', command=self.open).pack(side='right', padx=(6, 0))
        self.popup = None

    def open(self):
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.lift(); return
        self.popup = tk.Toplevel(self)
        self.popup.title('Choose dictation language')
        self.popup.geometry('440x460')
        self.popup.transient(self.winfo_toplevel())
        self.search = tk.StringVar()
        ttk.Label(self.popup, text='Search by language name or code').pack(anchor='w', padx=12, pady=(12, 4))
        entry = ttk.Entry(self.popup, textvariable=self.search)
        entry.pack(fill='x', padx=12)
        row = ttk.Frame(self.popup); row.pack(fill='both', expand=True, padx=12, pady=8)
        self.tree = ttk.Treeview(row, show='tree', selectmode='browse', height=12)
        scrollbar = ttk.Scrollbar(row, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.tree.pack(side='left', fill='both', expand=True)
        self.search.trace_add('write', lambda *_: self.filter())
        self.tree.bind('<Double-1>', lambda event: self.choose())
        self.tree.bind('<Return>', lambda event: self.choose())
        entry.bind('<Return>', lambda event: self.choose())
        self.popup.bind('<Escape>', lambda event: self.popup.destroy())
        ttk.Button(self.popup, text='Use selected language', command=self.choose).pack(pady=(0, 12))
        self.filter()
        self.popup.wait_visibility()
        self.popup.grab_set()
        entry.focus_set()

    def filter(self):
        self.tree.delete(*self.tree.get_children())
        choices = language_choices(self.search.get())
        for code, caption in choices:
            self.tree.insert('', 'end', iid=code or 'automatic', text=caption)
        current = self.variable.get().replace('_', '-').split('-')[0].lower() or 'automatic'
        if not self.tree.exists(current):
            current = (choices[0][0] or 'automatic') if choices else None
        if current:
            self.tree.selection_set(current)
            self.tree.see(current)

    def choose(self):
        selected = self.tree.selection()
        if selected:
            self.variable.set('' if selected[0] == 'automatic' else selected[0])
            self.popup.destroy()
            self.changed()

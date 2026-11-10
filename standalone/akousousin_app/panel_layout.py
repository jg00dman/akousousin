# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Task-ordered panel pages. Runtime work stays in the existing controller."""
import json
import os
from pathlib import Path
import platform
import tkinter as tk
from tkinter import ttk
import webbrowser

from . import __version__, resources, runtime, settings, updates
from .languages import label
from .scrolling import ScrollArea

PAGES = ('Status & setup', 'Voices & languages', 'Dictation', 'Connect applications',
         'Shortcuts', 'Application', 'About')
ALIASES = {'Overview': 'Status & setup', 'Voice library': 'Voices & languages',
           'Languages': 'Voices & languages', 'Voice Input': 'Dictation',
           'Settings': 'Application', 'Updates': 'Application', 'Read selection': 'Shortcuts'}


class Disclosure(ttk.Frame):
    def __init__(self, parent, text):
        super().__init__(parent)
        self.pack(fill='x', pady=8)
        self.open = tk.BooleanVar(value=False)
        self.content = ttk.Frame(self)
        def toggle():
            if self.open.get(): self.content.pack(fill='x', pady=8)
            else: self.content.pack_forget()
        ttk.Checkbutton(self, text=text, variable=self.open, command=toggle).pack(anchor='w')


class PanelLayout:
    def setup_pages(self, nav):
        self.nav_pages = {}
        self.hosts = {}
        self.scrolls = {}
        for name in PAGES:
            ttk.Button(nav, text=name, command=lambda name=name: self.show(name)).pack(fill='x', pady=4)
            outer = self.nav_pages[name] = ttk.Frame(self.content)
            if name in ('Voices & languages', 'Dictation'):
                self.hosts[name] = outer
            else:
                scroll = self.scrolls[name] = ScrollArea(outer)
                scroll.pack(fill='both', expand=True)
                self.hosts[name] = scroll.inner
        self.pages = dict(self.hosts)
        self.voice_tabs = ttk.Notebook(self.hosts['Voices & languages'])
        self.voice_tabs.pack(fill='both', expand=True)
        for old, title in (('Voice library', 'Choose voices'), ('Languages', 'Reading languages'),
                           ('Playback', 'Playback & advanced')):
            tab = ttk.Frame(self.voice_tabs)
            self.voice_tabs.add(tab, text=title)
            if old == 'Voice library':
                self.pages[old] = tab
            else:
                scroll = ScrollArea(tab); scroll.pack(fill='both', expand=True)
                self.pages[old] = scroll.inner
        self.pages.update({'Overview': self.hosts['Status & setup'], 'Voice Input': self.hosts['Dictation'],
                           'Settings': self.hosts['Application'], 'Updates': self.hosts['Application'],
                           'Read selection': self.hosts['Shortcuts']})
        self.settings_scroll = self.scrolls['Application']

    def build_overview(self):
        page = self.pages['Overview']
        if getattr(self, 'overview_built', False):
            if not self.config['voices'] and not hasattr(self, 'starter_card'):
                before = page.winfo_children()[0] if page.winfo_children() else None
                self.starter_card = self.card(page, 'Choose a speech voice (optional)')
                if before:
                    self.starter_card.pack_configure(before=before)
                ttk.Button(self.starter_card, text='Choose or download a voice', command=lambda: self.show('Voice library')).pack(anchor='w')
            return
        self.overview_built = True
        self.dictation_status = tk.StringVar(value='Recognition not loaded · Microphone off')
        self.setup_status = tk.StringVar(value='Choose the features you need; speech and dictation work independently.')
        self.speech_strip = tk.StringVar(value='Speech: checking…')
        self.dictation_strip = tk.StringVar(value='Microphone: off')
        self.reading_state = tk.StringVar(value='Ready to read selected text')
        self.reading_shortcuts = tk.StringVar(value='Reading shortcuts are disabled')
        if not self.config['voices']:
            self.starter_card = self.card(page, 'Choose a speech voice (optional)')
            ttk.Label(self.starter_card, text='Download the starter voice once, or choose a voice and language. Dictation does not require a speech voice.',
                      style='Card.TLabel', wraplength=760).pack(anchor='w')
            ttk.Button(self.starter_card, text='Download starter voice (64 MB)', command=self.download_starter).pack(anchor='w', pady=6)
            ttk.Button(self.starter_card, text='Choose another voice', command=lambda: self.show('Voice library')).pack(anchor='w')
        speech = self.card(page, 'Speech output')
        ttk.Label(speech, textvariable=self.server_status, style='Card.TLabel', wraplength=760).pack(anchor='w')
        self.home_voice = ttk.Label(speech, style='Card.TLabel', wraplength=760)
        self.home_voice.pack(anchor='w', pady=6)
        row = ttk.Frame(speech, style='Card.TFrame'); row.pack(fill='x')
        ttk.Button(row, text='Play sample', command=self.play).pack(side='left', padx=3)
        ttk.Button(row, text='Stop speaking', command=lambda: self.control('speech-stop')).pack(side='left', padx=3)
        ttk.Button(row, text='Choose voice / speed / volume', command=lambda: self.show('Playback')).pack(side='left', padx=3)
        if os.name != 'nt':
            row = ttk.Frame(speech, style='Card.TFrame'); row.pack(fill='x', pady=6)
            self.read_selected_button = ttk.Button(row, text='Read selected text', command=lambda: self.read_action(False))
            self.read_selected_button.pack(side='left', padx=3)
            self.read_copied_button = ttk.Button(row, text='Read copied text', command=lambda: self.read_action(True))
            self.read_copied_button.pack(side='left', padx=3)
            ttk.Label(speech, textvariable=self.reading_state, style='Card.TLabel', wraplength=760).pack(anchor='w')
            ttk.Label(speech, text='For reading selected text in another app, use the tray menu or global shortcut. The control panel cannot recover a selection hidden by switching to it.',
                      style='Card.TLabel', wraplength=760).pack(anchor='w', pady=6)
        recognition = self.card(page, 'Dictation')
        ttk.Label(recognition, textvariable=self.dictation_status, style='Card.TLabel', wraplength=760).pack(anchor='w')
        row = ttk.Frame(recognition, style='Card.TFrame'); row.pack(fill='x', pady=8)
        self.home_stop_dictation = ttk.Button(row, text='Stop dictation', command=lambda: self.control('stt-finish'))
        self.home_stop_dictation.pack(side='left', padx=3)
        ttk.Button(row, text='Cancel recognition', command=lambda: self.control('stt-cancel')).pack(side='left', padx=3)
        ttk.Button(row, text='Configure / test microphone', command=lambda: self.show('Dictation')).pack(side='left', padx=3)
        ttk.Label(recognition, text='Start desktop dictation from the tray or shortcut while your editor is focused. Loading recognition never starts the microphone.',
                  style='Card.TLabel', wraplength=760).pack(anchor='w')
        setup = self.card(page, 'Set up the features you want')
        ttk.Label(setup, textvariable=self.setup_status, style='Card.TLabel', wraplength=760).pack(anchor='w')
        for title in ('Voices & languages', 'Dictation', 'Connect applications', 'Shortcuts'):
            ttk.Button(setup, text=title + ' →', command=lambda title=title: self.show(title)).pack(anchor='w', pady=3)

    def control(self, command, **options):
        self.worker(lambda: runtime.call(self.path, {'command':command, **options}),
                    lambda result: self.status.set('Command completed.'), parallel=True)

    def read_action(self, clipboard):
        self.control('selection-toggle', clipboard=clipboard)

    def update_home(self, result):
        reading = result.get('reading', {})
        self.reading_state.set(reading.get('state', 'Ready'))
        self.reading_shortcuts.set(reading.get('shortcut_state', 'Disabled'))
        if hasattr(self, 'read_selected_button'):
            self.read_selected_button.configure(text='Stop reading' if reading.get('reading') and not reading.get('clipboard') else 'Read selected text')
            self.read_copied_button.configure(text='Stop reading' if reading.get('reading') and reading.get('clipboard') else 'Read copied text')
        recognition = result.get('dictation', {})
        self.home_stop_dictation.configure(state='normal' if recognition.get('dictation_active') else 'disabled')
        phase = recognition.get('phase', 'unloaded')
        mic = 'opening' if phase == 'opening' else 'listening' if recognition.get('microphone_open') else 'off'
        ready = 'Recognition ready' if recognition.get('loaded') else 'Recognition not loaded'
        text = ready + ' · Microphone ' + mic + '\n' + recognition.get('state', 'Not loaded')
        if hasattr(self, 'voice_input'):
            text += '\n' + self.voice_input.source_caption.get() + ' · ' + self.voice_input.language_picker.caption.get()
        self.dictation_status.set(text)
        self.dictation_strip.set('Microphone: ' + mic + ' · ' + recognition.get('state', 'Not loaded'))
        voice = self.config['voices'].get(self.config['voice'])
        self.home_voice.configure(text=(voice['name'] + ' · ' + label(voice['language']) if voice else 'No speech voice installed') +
                                  f' · Speed {self.speed.get():.2f} · Volume {self.volume.get():.0f}%')
        desktop = recognition.get('desktop', {})
        self.setup_status.set('Speech voice: ' + ('ready' if voice else 'not configured (optional)') +
            '\nRecognition: ' + ('ready' if recognition.get('loaded') else 'not loaded (optional)') +
            '\nDictation shortcut: ' + ('enabled' if desktop.get('enabled') else 'not enabled') +
            '\nReading shortcuts: ' + ('enabled' if reading.get('shortcuts_enabled') else 'not enabled') +
            ('\nNeeds attention: ' + result['error'] if result.get('error') else ''))

    def build_settings(self):
        page = self.pages['Settings']
        installation = self.card(page, 'Application installation')
        try:
            build = json.loads((resources.root() / 'build.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            build = {'distribution':'source'}
        ttk.Label(installation, text='Format: ' + build.get('distribution', 'source') + '\nLocation: ' + str(resources.root().parent),
                  style='Card.TLabel', wraplength=760).pack(anchor='w')
        if updates.is_appimage():
            ttk.Button(installation, text='Move AppImage / add menu shortcut…', command=lambda: self.offer_appimage_install(manual=True)).pack(anchor='w', pady=8)
        else:
            ttk.Label(installation, text='Use this installation’s installer or package manager to upgrade or remove it.', style='Card.TLabel', wraplength=760).pack(anchor='w')
        self.build_updates()
        advanced = Disclosure(page, 'Advanced service settings').content
        frame = self.card(advanced, 'Speech service')
        for text, variable, minimum, maximum in [('Local service port', self.port, 1024, 65535), ('Unload speech model after idle seconds (0 = never)', self.idle_timeout, 0, 86400)]:
            ttk.Label(frame, text=text, style='Card.TLabel').pack(anchor='w')
            ttk.Spinbox(frame, textvariable=variable, from_=minimum, to=maximum, width=10).pack(anchor='w', pady=5)
        ttk.Label(frame, text='Changing the port requires restarting the service and reapplying voice registration. Never is the default idle timeout.', style='Card.TLabel', wraplength=760).pack(anchor='w')
        row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=8)
        ttk.Button(row, text='Load speech model', command=self.start_server).pack(side='left', padx=3)
        ttk.Button(row, text='Unload speech model', command=self.stop_server).pack(side='left', padx=3)
        ttk.Button(frame, text='Save settings', command=self.save).pack(anchor='w', pady=8)

    def build_shortcuts(self):
        page = self.pages['Shortcuts']
        frame = self.card(page, 'Dictation shortcut and activation')
        self.voice_input.build_shortcuts(frame)
        if os.name != 'nt':
            self.build_selection()
        else:
            ttk.Label(page, text='Native Windows global shortcuts are forthcoming.', wraplength=760).pack(anchor='w')
        ttk.Label(page, text='The tray offers the same read and dictation actions for touch use. Enabling shortcuts never starts recording. Your desktop stores assigned keys and may require permission again if it cannot restore it.', wraplength=760).pack(anchor='w', pady=10)

    def build_about(self):
        page = self.pages['About']
        info = self.card(page, 'About Akousousin')
        try:
            build = json.loads((resources.root() / 'build.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            build = {}
        details = f'Akousousin {__version__}\nBuild: {build.get("build", "source")}\nFormat: {build.get("distribution", "source")}\nPlatform: {platform.system()} {platform.machine()}'
        ttk.Label(info, text=details, style='Card.TLabel', wraplength=760).pack(anchor='w')
        ttk.Label(info, text='Copyright © 2026 John Goodman\nOriginal application: GPL-3.0-or-later\nSAPI engine/API: LGPL-2.1-or-later\nThird-party components and models retain their own licences.', style='Card.TLabel', wraplength=760).pack(anchor='w', pady=10)
        ref = build.get('commit', 'codex/panel-workflow' if '.dev' in __version__ else 'main')
        document = 'PANEL-WORKFLOW-TESTING.md' if '.dev' in __version__ else 'README.md'
        base = 'https://github.com/jg00dman/akousousin/blob/' + ref + '/standalone/'
        links = [('Project homepage', 'https://github.com/jg00dman/akousousin'), ('Documentation', base + document),
                 ('Release notes', base + 'RELEASE-NOTES.md'), ('Report an issue', 'https://github.com/jg00dman/akousousin/issues')]
        for title, url in links:
            ttk.Button(info, text=title, command=lambda url=url: webbrowser.open(url)).pack(anchor='w', pady=3)
        diagnostic = self.card(page, 'Diagnostics and storage')
        from akousousin_backend.recognition import model_root
        paths = '\n'.join(['Configuration: ' + str(self.path), 'Voice data: ' + str(settings.data_path() / 'voices'),
                           'Recognition models: ' + str(model_root()), 'Service log: ' + str(self.service.log)])
        ttk.Label(diagnostic, text=paths, style='Card.TLabel', wraplength=760).pack(anchor='w')
        def copy():
            self.root.clipboard_clear(); self.root.clipboard_append(details + '\n' + paths + '\n' + self.server_status.get() + '\n' + self.dictation_status.get())
            self.status.set('Diagnostics copied. No transcript text or permission tokens included.')
        ttk.Button(diagnostic, text='Copy diagnostics', command=copy).pack(anchor='w', pady=6)
        ttk.Button(diagnostic, text='Open service log', command=lambda: webbrowser.open(self.service.log.as_uri())).pack(anchor='w')
        notices = resources.root().parent / 'licenses'
        ttk.Button(diagnostic, text='Open bundled licence notices', command=lambda: webbrowser.open(notices.as_uri())).pack(anchor='w', pady=6)

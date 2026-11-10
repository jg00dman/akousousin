# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Desktop control panel. All downloads, Wine calls and synthesis run off the UI thread."""
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import urllib.request
import webbrowser

from . import __version__, catalogue, resources, runtime, settings, updates
from .languages import label
from .install import Installer
from .dialogs import show_error
from .service import Service


class Panel:
    def __init__(self, path, offer_install=True):
        self.path = Path(path)
        self.config = resources.bootstrap(path)
        self.library = catalogue.catalogue(resources.root())
        for key, voice in self.config['voices'].items():
            self.library.setdefault(key, {'key': key, 'name': voice['name'], 'quality': voice.get('quality', 'local'),
                                         'files': {}, 'language': {'code': voice['language'],
                                         'name_english': voice['language'], 'name_native': voice['language']}})
        self.service = Service(path)
        self.events = queue.Queue()
        self.busy = 0
        self.updating = False
        self.panel_polling = False
        self.last_panel_activation = 0
        self.root = tk.Tk()
        self.root.title('Akousousin - The unified neural speech engine for Linux (beta)')
        icon = resources.root() / 'akousousin.png'
        if icon.exists():
            self.window_icon = tk.PhotoImage(file=str(icon))
            self.root.iconphoto(True, self.window_icon)
        width = min(1160, max(640, self.root.winfo_screenwidth() - 80))
        height = min(820, max(400, self.root.winfo_screenheight() - 100))
        self.root.geometry(f'{width}x{height}')
        self.root.minsize(min(760, width), min(480, height))
        self.root.configure(bg='#f4f5f3')
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', font=('DejaVu Sans', 10), background='#f4f5f3', foreground='#193c43')
        style.configure('Card.TFrame', background='white')
        style.configure('Card.TLabel', background='white')
        style.configure('Title.TLabel', font=('DejaVu Sans', 23, 'bold'))
        style.configure('Section.TLabel', font=('DejaVu Sans', 14, 'bold'))
        style.configure('Accent.TButton', background='#087e82', foreground='white', padding=(14, 9))
        style.configure('TButton', padding=(10, 7))
        style.configure('Treeview', background='white', fieldbackground='white', rowheight=34)
        style.configure('Treeview.Heading', font=('DejaVu Sans', 10, 'bold'), padding=8)
        header = ttk.Frame(self.root, padding=(24, 18))
        header.pack(fill='x')
        if hasattr(self, 'window_icon'):
            self.header_icon = self.window_icon.subsample(max(1, (self.window_icon.width() + 31) // 32))
            ttk.Label(header, image=self.header_icon, padding=(0, 0, 12, 0)).pack(side='left')
        ttk.Label(header, text='Akousousin', style='Title.TLabel').pack(side='left')
        ttk.Label(header, text='The unified neural speech engine for Linux (beta)',
                  font=('DejaVu Sans', 10, 'italic'), padding=(18, 8), wraplength=460).pack(side='left')
        ttk.Label(header, text=f'Beta {__version__}').pack(side='right')
        body = ttk.Frame(self.root)
        body.pack(fill='both', expand=True, padx=20)
        nav = ttk.Frame(body, width=165, padding=(0, 10, 16, 0))
        nav.pack(side='left', fill='y')
        self.content = ttk.Frame(body)
        self.content.pack(side='left', fill='both', expand=True)
        self.pages = {}
        for name in ('Overview', 'Voice library', 'Voice Input', 'Languages', 'Settings', 'Updates') + (('Read selection',) if os.name != 'nt' else ()):
            ttk.Button(nav, text=name, command=lambda name=name: self.show(name)).pack(fill='x', pady=4)
            self.pages[name] = ttk.Frame(self.content)
        self.status = tk.StringVar(value='Ready')
        self.server_status = tk.StringVar(value='Checking service…')
        self.prefix = tk.StringVar(value=self.config['wine_prefix'])
        self.wine = tk.StringVar(value=self.config['wine'])
        self.preview = tk.StringVar(value='The quick brown fox jumps over the lazy dog.')
        self.speed = tk.DoubleVar(value=round(self.config['speed'] * 4) / 4)
        self.volume = tk.DoubleVar(value=self.config['volume'] * 100)
        self.noise = tk.DoubleVar(value=self.config['noise_scale'])
        self.noise_w = tk.DoubleVar(value=self.config['noise_w_scale'])
        self.language = tk.StringVar(value=label(self.config['book_language']) if self.config['book_language'] else 'Follow application')
        self.port = tk.IntVar(value=self.config['port'])
        self.idle_timeout = tk.IntVar(value=self.config['idle_timeout'])
        self.build_overview()
        self.build_library()
        self.build_languages()
        self.build_settings()
        from .voice_input import VoiceInput
        self.voice_input = VoiceInput(self, self.pages['Voice Input'])
        self.build_updates()
        if self.config.get('speechd_setup_warning'):
            self.status.set(self.config['speechd_setup_warning'])
        if os.name != 'nt':
            self.build_selection()
        from .download_status import DownloadView
        self.downloads = DownloadView(self.root)
        footer = ttk.Frame(self.root, padding=(22, 12))
        footer.pack(fill='x')
        status_style = ttk.Style(self.root)
        status_style.map('Status.TEntry', fieldbackground=[('readonly', '#e6e6e6')],
                         foreground=[('readonly', '#222222')])
        self.status_field = ttk.Entry(footer, textvariable=self.status, state='readonly', style='Status.TEntry')
        self.status_field.pack(side='left', fill='x', expand=True)
        def select_status(event):
            self.status_field.selection_range(0, 'end')
            return 'break'
        self.status_field.bind('<Control-a>', select_status)
        self.status_field.bind('<Control-A>', select_status)
        def copy_status():
            self.root.clipboard_clear(); self.root.clipboard_append(self.status.get())
        ttk.Button(footer, text='Copy', command=copy_status).pack(side='left', padx=8)
        self.progress = ttk.Progressbar(footer, mode='indeterminate', length=110)
        self.progress.pack(side='right')
        self.show('Overview')
        self.refresh_library()
        self.root.after(100, self.poll)
        self.root.after(200, self.check_server)
        self.root.after(300, self.poll_panel)
        if offer_install:
            self.root.after(800, self.offer_appimage_install)

    def show(self, name):
        for page in self.pages.values():
            page.pack_forget()
        self.pages[name].pack(fill='both', expand=True)

    def card(self, parent, title):
        frame = ttk.Frame(parent, style='Card.TFrame', padding=18)
        frame.pack(fill='x', pady=(0, 12))
        ttk.Label(frame, text=title, style='Section.TLabel').pack(anchor='w', pady=(0, 12))
        return frame

    def worker(self, function, success=None, parallel=False):
        if self.busy and not parallel:
            self.status.set('Please wait for the current operation to finish.')
            return
        self.busy += 1
        self.progress.start(12)
        def run():
            try:
                result = function()
                self.events.put(('success', success, result))
            except Exception as error:
                self.events.put(('error', None, error))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, callback, result = self.events.get_nowait()
                if kind == 'panel-status':
                    if result:
                        if result['activation'] != self.last_panel_activation:
                            self.last_panel_activation = result['activation']
                            if result.get('page') in self.pages:
                                self.show(result['page'])
                            self.root.deiconify(); self.root.lift(); self.root.focus_force()
                        if hasattr(self, 'reading_state'):
                            reading = result['reading']
                            self.reading_state.set(reading['state'])
                            self.reading_shortcuts.set(reading['shortcut_state'])
                    continue
                self.busy = max(0, self.busy - 1)
                if kind == 'error':
                    self.updating = False
                    self.status.set(getattr(result, 'message', str(result)))
                    show_error(self.root, result)
                elif callback:
                    callback(result)
        except queue.Empty:
            pass
        if not self.busy:
            self.progress.stop()
        self.root.after(100, self.poll)

    def poll_panel(self):
        if not self.panel_polling:
            self.panel_polling = True
            def task():
                try:
                    result = runtime.call(self.path, {'command': 'panel-status'}, launch=False)
                    self.events.put(('panel-status', None, result))
                except Exception:
                    pass
                finally:
                    self.panel_polling = False
            threading.Thread(target=task, daemon=True).start()
        self.root.after(600, self.poll_panel)

    def check_server(self):
        port = self.config['port']
        # Status polls use their own callback queue so they do not alter busy state.
        def poll():
            value = self.service.health(port)
            self.root_status.put(value)
        if not hasattr(self, 'root_status'):
            self.root_status = queue.Queue()
        try:
            value = self.root_status.get_nowait()
            self.server_status.set('Running — ready for speech' if value and value.get('ready') else 'Stopped')
        except queue.Empty:
            pass
        threading.Thread(target=poll, daemon=True).start()
        self.root.after(2000, self.check_server)

    def build_overview(self):
        page = self.pages['Overview']
        if not self.config['voices']:
            self.starter_card = self.card(page, 'Get started with speech')
            ttk.Label(self.starter_card, text='Download the reviewed English LJSpeech starter voice once (about 64 MB), or choose another voice in Voice library. Downloads stay installed between upgrades. Voice input can be used independently.',
                      style='Card.TLabel', wraplength=780).pack(anchor='w', pady=8)
            ttk.Button(self.starter_card, text='Download starter voice (64 MB)', style='Accent.TButton',
                       command=self.download_starter).pack(side='left', padx=3)
            ttk.Button(self.starter_card, text='Choose another voice', command=lambda: self.show('Voice library')).pack(side='left', padx=3)
            return
        frame = self.card(page, 'Speech service')
        ttk.Label(frame, textvariable=self.server_status, style='Card.TLabel').pack(side='left')
        ttk.Button(frame, text='Start server', style='Accent.TButton', command=self.start_server).pack(side='right', padx=4)
        ttk.Button(frame, text='Stop server', command=self.stop_server).pack(side='right', padx=4)
        frame = self.card(page, 'Default voice & preview')
        self.default_label = ttk.Label(frame, text='', style='Card.TLabel', wraplength=790)
        self.default_label.pack(anchor='w', pady=(0, 12))
        ttk.Entry(frame, textvariable=self.preview).pack(fill='x', pady=8)
        ttk.Button(frame, text='▶  Play sample', style='Accent.TButton', command=self.play).pack(anchor='w', pady=8)
        for caption, variable, low, high in [('Default speed', self.speed, .5, 4), ('Volume', self.volume, 0, 100)]:
            row = ttk.Frame(frame, style='Card.TFrame')
            row.pack(fill='x', pady=8)
            ttk.Label(row, text=caption, width=18, style='Card.TLabel').pack(side='left')
            if variable is self.speed:
                self.speed_slider = tk.Scale(row, variable=variable, from_=low, to=high, resolution=.25,
                                             orient='horizontal', showvalue=False, highlightthickness=0,
                                             borderwidth=0, bg='white')
                self.speed_slider.pack(side='left', fill='x', expand=True)
                self.speed_spin = ttk.Spinbox(row, textvariable=variable, from_=low, to=high,
                                             increment=.25, format='%.2f', state='readonly', width=7)
                self.speed_spin.pack(side='right', padx=(12, 0))
            else:
                ttk.Scale(row, variable=variable, from_=low, to=high).pack(side='left', fill='x', expand=True)
                ttk.Spinbox(row, textvariable=variable, from_=low, to=high, increment=1,
                            width=7).pack(side='right', padx=(12, 0))
        ttk.Button(frame, text='Save playback preferences', command=self.save).pack(anchor='e', pady=8)
        ttk.Label(page, text='Preferences apply to new speech. Applications may need restarting after changing the default voice.',
                  wraplength=820).pack(anchor='w', padx=4)
        self.update_default()

    def update_default(self):
        voice = self.config['voices'].get(self.config['voice'])
        self.default_label.configure(text=f"{voice['name']} · {label(voice['language'])} · {voice['quality']}" if voice else 'Choose a voice in Voice library')

    def build_library(self):
        page = self.pages['Voice library']
        ttk.Label(page, text='Voice library', style='Section.TLabel').pack(anchor='w', pady=12)
        row = ttk.Frame(page)
        row.pack(fill='x', pady=8)
        self.search = tk.StringVar()
        self.search.trace_add('write', lambda *_: self.refresh_library())
        ttk.Entry(row, textvariable=self.search).pack(side='left', fill='x', expand=True)
        self.filter = tk.StringVar(value='All languages')
        languages = sorted({v['language']['code'] for v in self.library.values()})
        choices = ttk.Combobox(row, textvariable=self.filter, values=['All languages', *(label(code) for code in languages)], width=26, state='readonly')
        choices.pack(side='left', padx=8)
        choices.bind('<<ComboboxSelected>>', lambda *_: self.refresh_library())
        self.installed_only = tk.BooleanVar()
        ttk.Checkbutton(row, text='Installed only', variable=self.installed_only,
                        command=self.refresh_library).pack(side='right')
        table = ttk.Frame(page, height=100); table.pack(fill='both', expand=True, pady=8)
        table.grid_propagate(False)  # Reserve room for actions on small screens.
        table.rowconfigure(0, weight=1); table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=('language', 'quality', 'size', 'status'), show='tree headings', height=12)
        self.tree.heading('#0', text='Voice')
        self.tree.column('#0', width=160)
        for name, width in [('language', 190), ('quality', 80), ('size', 80), ('status', 230)]:
            self.tree.heading(name, text=name.title())
            self.tree.column(name, width=width)
        self.tree.grid(row=0, column=0, sticky='nsew')
        self.library_scrollbar = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        self.library_scrollbar.grid(row=0, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(table, orient='horizontal', command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        self.tree.configure(yscrollcommand=self.library_scrollbar.set, xscrollcommand=horizontal.set)
        row = ttk.Frame(page)
        row.pack(fill='x', pady=8)
        ttk.Button(row, text='Review licence & download', command=self.download).pack(side='left', padx=3)
        ttk.Button(row, text='Make default', style='Accent.TButton', command=self.make_default).pack(side='left', padx=3)
        ttk.Button(row, text='Import local model', command=self.import_model).pack(side='left', padx=3)
        delete_row = ttk.Frame(page); delete_row.pack(fill='x', pady=(0, 4))
        self.delete_voice_button = ttk.Button(delete_row, text='Delete voice…', command=self.delete_voice, state='disabled')
        self.delete_voice_button.pack(side='left', padx=3)
        self.tree.bind('<<TreeviewSelect>>', self.update_delete_voice)
        ttk.Label(page, text='Catalogue: Piper voices, pinned revision. Licences vary by voice; LJSpeech has reviewed provenance; models download separately. Other downloads require your licence review.',
                  wraplength=820).pack(anchor='w', pady=10)

    def refresh_library(self):
        if not hasattr(self, 'tree'):
            return
        self.tree.delete(*self.tree.get_children())
        needle = self.search.get().casefold()
        for key, entry in sorted(self.library.items()):
            installed = key in self.config['voices']
            if self.installed_only.get() and not installed:
                continue
            if self.filter.get() != 'All languages' and label(entry['language']['code']) != self.filter.get():
                continue
            fields = f"{key} {entry['language']['name_english']} {entry['language']['name_native']}".casefold()
            if needle and needle not in fields:
                continue
            size = sum(f['size_bytes'] for p, f in entry['files'].items() if p.endswith('.onnx')) / 1000000
            status = ('Installed' if installed else 'Language resources unavailable'
                      if entry['language'].get('family') in catalogue.UNSUPPORTED_AUXILIARY
                      else 'Reviewed free-use' if key in catalogue.APPROVED else 'Licence review required')
            self.tree.insert('', 'end', iid=key, text=entry['name'], values=(label(entry['language']['code']),
                             entry['quality'], f'{size:.0f} MB', status))

    def update_delete_voice(self, event=None):
        selected = self.tree.selection()
        self.delete_voice_button.configure(state='normal' if selected and selected[0] in self.config['voices'] else 'disabled')

    def delete_voice(self):
        if self.busy:
            self.status.set('Please wait for the current operation to finish.')
            return
        try:
            key = self.selected()
            if key not in self.config['voices']:
                raise ValueError('Select an installed voice')
        except ValueError as error:
            messagebox.showinfo('Delete voice', str(error)); return
        text = (f'Delete {self.config["voices"][key]["name"]} from the AKS voice library?\n\n'
                'Downloaded files in the AKS voice cache will be deleted. Imported original files are kept. '
                'Current AKS speech will stop. If this is the default voice, another installed voice will be selected. '
                'Deleting the last voice leaves speech unavailable until you install another. '
                'Apply voice registration in Settings afterwards and restart applications that cache voices.')
        if not messagebox.askyesno('Delete installed voice', text, parent=self.root):
            return
        def remove():
            runtime.call(self.path, {'command': 'stop'}, launch=False)
            return resources.remove_voice(self.path, key)
        def removed(config):
            self.config = config
            if not self.library[key]['files']:
                self.library.pop(key)
            self.refresh_library(); self.refresh_languages()
            self.update_delete_voice()
            for child in self.pages['Overview'].winfo_children():
                child.destroy()
            if hasattr(self, 'starter_card'):
                del self.starter_card
            self.build_overview()
            self.status.set('Voice deleted. Apply voice registration in Settings; restart applications if needed.')
        self.worker(remove, removed)

    def selected(self):
        selected = self.tree.selection()
        if not selected:
            raise ValueError('Select a voice first')
        return selected[0]

    def download(self):
        try:
            key = self.selected()
            if key in self.config['voices']:
                raise ValueError('That voice is already installed')
        except ValueError as error:
            messagebox.showinfo('Voice library', str(error)); return
        def review(text):
            window = tk.Toplevel(self.root)
            window.title(f'Voice licence — {key}')
            box = tk.Text(window, width=90, height=24, wrap='word')
            box.pack(fill='both', expand=True, padx=14, pady=14)
            box.insert('1.0', 'Repository declaration: MIT. The per-voice model card below may add restrictions.\n\n' + text)
            box.configure(state='disabled')
            accepted = tk.BooleanVar(value=key in catalogue.APPROVED)
            ttk.Checkbutton(window, text='I have reviewed the model/dataset terms and can use this voice',
                            variable=accepted).pack(anchor='w', padx=14)
            def begin():
                if not accepted.get():
                    return
                window.destroy()
                self.status.set('Downloading voice…')
                self.worker(lambda: catalogue.install(self.library[key], settings.data_path() / 'voices', True),
                            lambda voice: self.voice_downloaded(key, voice))
            ttk.Button(window, text='Download voice', command=begin, style='Accent.TButton').pack(pady=12)
        self.worker(lambda: catalogue.card(self.library[key]), review)

    def voice_downloaded(self, key, voice):
        self.config = resources.register_voice(self.path, key, voice)
        self.refresh_library()
        self.refresh_languages()
        if hasattr(self, 'starter_card'):
            self.starter_card.destroy()
            del self.starter_card
            self.build_overview()
        self.update_default()
        self.status.set('Voice installed and retained for future upgrades. Apply voice registration in Settings when needed.')
        if os.name != 'nt' and self.config.get('speechd_setup_pending'):
            def finish_setup():
                from .speech_dispatcher import complete_pending_setup
                complete_pending_setup(self.path)
                return settings.load(self.path)
            def finished(config):
                self.config = config
                self.status.set(config.get('speechd_setup_warning') or 'Voice installed. Akousousin is now the Speech Dispatcher default; other engines remain available.')
            self.worker(finish_setup, finished)

    def download_starter(self):
        key = resources.STARTER
        if self.busy:
            return
        self.status.set('Downloading starter voice…')
        self.worker(lambda: resources.download_starter(self.path),
                    lambda config: self.voice_downloaded(key, config['voices'][key]))

    def make_default(self):
        try:
            key = self.selected()
            if key not in self.config['voices']:
                raise ValueError('Download this voice first')
            self.worker(lambda: runtime.call(self.path, {'command': 'voice', 'voice': key}),
                        lambda result: self.status.set('Default saved. Restart applications if needed; apply registration for newly added voices.'))
            self.config['voice'] = key
            self.config['language_voices'][self.config['voices'][key]['language']] = key
            self.update_default()
            self.refresh_languages()
            self.status.set('Default saved. Apply to your prefix/Windows registration in Settings.')
        except ValueError as error:
            messagebox.showinfo('Default voice', str(error))

    def import_model(self):
        model = filedialog.askopenfilename(title='Select a Piper ONNX model', filetypes=[('Piper model', '*.onnx')])
        if not model:
            return
        try:
            config = json.loads(Path(model + '.json').read_text(encoding='utf-8'))
            key = re.sub('[^A-Za-z0-9_-]', '_', Path(model).stem)[:110]
            if key in self.config['voices'] and self.config['voices'][key]['path'] != model:
                import uuid
                key += '_' + uuid.uuid4().hex[:8]
            language = config.get('language', {}).get('code')
            if not language:
                language = simpledialog.askstring('Model language', 'Language code, for example en_US or de_DE:', parent=self.root)
                if not language:
                    return
            if language.split('_')[0] in catalogue.UNSUPPORTED_AUXILIARY:
                raise ValueError('This language needs optional preprocessing resources not distributed in this beta')
            voice = {'path': model, 'sample_rate': config['audio']['sample_rate'],
                                          'language': language, 'name': key, 'quality': 'local'}
            # Imported models may not occur in the online catalogue; add a local row.
            self.library.setdefault(key, {'key': key, 'name': key, 'quality': 'local', 'files': {},
                                         'language': {'code': language, 'name_english': language, 'name_native': language}})
            self.voice_downloaded(key, voice)
        except Exception as error:
            show_error(self.root, error, 'Import voice')

    def build_languages(self):
        page = self.pages['Languages']
        frame = self.card(page, 'Reading languages')
        ttk.Label(frame, text='Language override (all applications)', style='Card.TLabel').pack(anchor='w')
        languages = sorted({v['language'] for v in self.config['voices'].values()})
        self.language_combo = ttk.Combobox(frame, textvariable=self.language,
                                           values=['Follow application', *(label(code) for code in languages)], state='readonly')
        self.language_combo.pack(fill='x', pady=10)
        ttk.Label(frame, text='Shared by SAPI and Speech Dispatcher. Follow application uses the requested language; selecting a language here overrides it for all applications.',
                  wraplength=780, style='Card.TLabel').pack(anchor='w', pady=12)
        ttk.Label(frame, text='Preferred voices by language', style='Card.TLabel').pack(anchor='w')
        self.language_rows = ttk.Treeview(frame, columns=('voice',), show='tree headings', height=7)
        self.language_rows.heading('#0', text='Language')
        self.language_rows.heading('voice', text='Preferred voice')
        self.language_rows.pack(fill='x', pady=10)
        for language, voice in sorted(self.config['language_voices'].items()):
            self.language_rows.insert('', 'end', text=label(language), values=(voice,))
        ttk.Label(frame, text='Make default in Voice library also sets that language’s preferred voice. Unavailable language preferences fall back to the requested/default voice. Latin appears only if you import or obtain a suitable model.',
                  wraplength=780, style='Card.TLabel').pack(anchor='w', pady=12)
        ttk.Button(frame, text='Save language preference', command=self.save).pack(anchor='e')

    def refresh_languages(self):
        languages = sorted({v['language'] for v in self.config['voices'].values()})
        self.language_combo.configure(values=['Follow application', *(label(code) for code in languages)])
        self.language_rows.delete(*self.language_rows.get_children())
        for language, voice in sorted(self.config['language_voices'].items()):
            self.language_rows.insert('', 'end', text=label(language), values=(voice,))

    def build_settings(self):
        from .scrolling import ScrollArea
        self.settings_scroll = ScrollArea(self.pages['Settings'])
        self.settings_scroll.pack(fill='both', expand=True)
        page = self.settings_scroll.inner
        if updates.is_appimage():
            frame = self.card(page, 'AppImage installation')
            from .appimage_install import recommended_path
            ttk.Label(frame, text=str(recommended_path()), style='Card.TLabel', wraplength=780).pack(anchor='w', pady=8)
            ttk.Button(frame, text='Move AppImage and add menu shortcut…', command=lambda: self.offer_appimage_install(manual=True)).pack(anchor='w')
        frame = self.card(page, 'Install into a Wine prefix or Windows')
        if os.name != 'nt':
            ttk.Label(frame, text='Wine prefix', style='Card.TLabel').pack(anchor='w')
            row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=6)
            ttk.Entry(row, textvariable=self.prefix).pack(side='left', fill='x', expand=True)
            ttk.Button(row, text='Choose…', command=lambda: self.prefix.set(filedialog.askdirectory())).pack(side='right')
            ttk.Label(frame, text='Wine executable / AppImage', style='Card.TLabel').pack(anchor='w')
            row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=6)
            ttk.Entry(row, textvariable=self.wine).pack(side='left', fill='x', expand=True)
            ttk.Button(row, text='Choose…', command=lambda: self.wine.set(filedialog.askopenfilename())).pack(side='right')
        ttk.Label(frame, text='Close applications before installation. Original speech registry settings are backed up. Wine compatibility DLLs stay in the Akousousin folder; system SAPI DLLs are untouched. Windows voice installation requires administrator rights.',
                  wraplength=780, style='Card.TLabel').pack(anchor='w', pady=12)
        ttk.Button(frame, text='Install / apply voice registration', style='Accent.TButton', command=self.install).pack(side='left', padx=4)
        ttk.Button(frame, text='Uninstall & restore', command=self.uninstall).pack(side='left', padx=4)
        if os.name != 'nt':
            frame = self.card(page, 'Native Linux speech — Speech Dispatcher')
            ttk.Label(frame, text='Install your distribution’s Speech Dispatcher first. Installation selects Akousousin as the default engine and keeps eSpeak available; removal restores the previous default. Installing or removing support restarts your user Speech Dispatcher and interrupts current speech. Then choose your voice in Orca.',
                      wraplength=780, style='Card.TLabel').pack(anchor='w', pady=8)
            ttk.Button(frame, text='Install Speech Dispatcher support', command=lambda: self.dispatcher_install(False)).pack(side='left', padx=4)
            ttk.Button(frame, text='Remove Speech Dispatcher support', command=lambda: self.dispatcher_install(True)).pack(side='left', padx=4)
        frame = self.card(page, 'Advanced synthesis')
        for text, variable in [('Generator variation (noise scale)', self.noise), ('Phoneme variation (noise width)', self.noise_w)]:
            row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=8)
            ttk.Label(row, text=text, style='Card.TLabel').pack(side='left')
            ttk.Spinbox(row, textvariable=variable, from_=0, to=2, increment=.05, width=8).pack(side='right')
        row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=8)
        ttk.Label(row, text='Loopback port', style='Card.TLabel').pack(side='left')
        ttk.Spinbox(row, textvariable=self.port, from_=1024, to=65535, width=8).pack(side='right')
        row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=8)
        ttk.Label(row, text='Unload Piper after idle seconds (0 = never)', style='Card.TLabel').pack(side='left')
        ttk.Spinbox(row, textvariable=self.idle_timeout, from_=0, to=86400, increment=60, width=8).pack(side='right')
        ttk.Label(frame, text='Piper has no general pitch slider. Speed and synthesis variation are supported. A port change requires server restart and reapplying voice registration.',
                  wraplength=780, style='Card.TLabel').pack(anchor='w', pady=12)
        ttk.Button(frame, text='Save settings', command=self.save).pack(anchor='e')
        ttk.Button(page, text='Open service log', command=lambda: webbrowser.open(self.service.log.as_uri())).pack(anchor='w')

    def offer_appimage_install(self, manual=False):
        from . import appimage_install
        if not updates.is_appimage() or self.busy or self.updating:
            return
        if not appimage_install.needs_move():
            if manual:
                self.worker(appimage_install.create_menu_entry,
                            lambda _: self.status.set('Application-menu shortcut installed.'))
            return
        target = appimage_install.recommended_path()
        replace_existing = target.exists()
        replacement = '\nAn AppImage already exists there and will be replaced.' if replace_existing else ''
        text = (f'Move Akousousin to its recommended location?\n\n{target}\n\n'
                'This also adds an application-menu shortcut with the AKS icon. '
                'AKS will restart; voices, models and preferences are retained. '
                'Close applications using AKS speech first.' + replacement +
                '\n\nChoose No to keep running from the current location.')
        if not messagebox.askyesno('Install Akousousin AppImage', text, parent=self.root):
            return
        if self.save():
            self.updating = True
            self.status.set('Installing AppImage… Please keep this window open.')
            self.worker(lambda: appimage_install.install(self.path, replace=replace_existing),
                        lambda _: self.root.after_idle(self.root.destroy), parallel=True)

    def build_updates(self):
        frame = self.card(self.pages['Updates'], 'Application updates')
        ttk.Label(frame, text=f'Installed version: {__version__}', style='Card.TLabel').pack(anchor='w')
        self.update_status = tk.StringVar(value='Check for a newer release.')
        if not updates.is_appimage():
            ttk.Label(frame, text='Updates are available from the download page. Install a new tar bundle with its installer, or use your package manager. This installation cannot replace itself.',
                      style='Card.TLabel', wraplength=760).pack(anchor='w', pady=12)
        self.weekly_updates = tk.BooleanVar(value=self.config['update_weekly'])
        self.beta_updates = tk.BooleanVar(value=self.config['update_betas'])
        ttk.Checkbutton(frame, text='Check for updates weekly', variable=self.weekly_updates,
                        command=self.save_update_preferences).pack(anchor='w', pady=(12, 4))
        ttk.Checkbutton(frame, text='Show beta testing updates', variable=self.beta_updates,
                        command=self.save_update_preferences).pack(anchor='w', pady=4)
        ttk.Label(frame, text='Checks notify you; updates are installed only when you choose. Turning off betas never downgrades your installation.',
                  style='Card.TLabel', wraplength=760).pack(anchor='w', pady=8)
        ttk.Label(frame, textvariable=self.update_status, wraplength=760, style='Card.TLabel').pack(anchor='w', pady=12)
        ttk.Button(frame, text='Check for updates', command=self.check_updates).pack(anchor='w')
        self.install_update_button = ttk.Button(frame, text='Install available update…' if updates.is_appimage() else 'Open update download page…', command=self.install_available_update, state='disabled')
        self.install_update_button.pack(anchor='w', pady=8)
        success = updates.completed_update(self.path)
        warnings = updates.registration_warnings(self.path)
        if warnings:
            ttk.Label(frame, text='Registration warnings:\n' + '\n'.join(warnings),
                      style='Card.TLabel', wraplength=760).pack(anchor='w', pady=8)
        if success:
            self.status.set(success)
            if not warnings:
                self.root.after(15000, lambda: self.status.set('Ready') if self.status.get() == success else None)
        self.root.after(500, self.poll_updates)

    def save_update_preferences(self):
        config = settings.load(self.path)
        config.update(update_weekly=self.weekly_updates.get(), update_betas=self.beta_updates.get())
        settings.save(self.path, config)
        self.config.update(update_weekly=config['update_weekly'], update_betas=config['update_betas'])
        self.status.set('Update preferences saved.')

    def poll_updates(self):
        if not self.updating:
            candidate = updates.available_update(self.path)
            self.install_update_button.configure(state='normal' if candidate else 'disabled')
            if candidate:
                self.update_status.set('Update available: ' + candidate['version'])
        self.root.after(1500, self.poll_updates)

    def install_available_update(self):
        candidate = updates.available_update(self.path)
        if candidate:
            self.confirm_update(candidate)

    def build_selection(self):
        from .scrolling import ScrollArea
        self.reading_scroll = ScrollArea(self.pages['Read selection'])
        self.reading_scroll.pack(fill='both', expand=True)
        frame = self.card(self.reading_scroll.inner, 'Read selected text / Stop')
        ttk.Label(frame, text='Highlight text in an application, then press the global shortcut to read it. Press it again to stop only this reading. Enabling shortcuts sets up Speech Dispatcher support and selects Akousousin first. Download or import a voice before enabling. Setup may briefly interrupt current speech.',
                  style='Card.TLabel', wraplength=760).pack(anchor='w', pady=8)
        ttk.Label(frame, text='Enable the reading shortcuts below and approve them in KDE. Suggested keys: Ctrl+Alt+R for selected text and Ctrl+Alt+Shift+R for copied text. KDE lets you change them or resolve conflicts. No microphone or keyboard-injection permission is needed.',
                  style='Card.TLabel', wraplength=760).pack(anchor='w', pady=8)
        self.reading_shortcuts = tk.StringVar(value='Reading shortcuts are disabled')
        self.reading_state = tk.StringVar(value='Ready to read selected text')
        def command(name, **options):
            self.worker(lambda: runtime.call(self.path, {'command': name, **options}),
                        lambda result: self.reading_state.set(result['state']))
        row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=8)
        ttk.Button(row, text='Enable global reading shortcuts', command=self.enable_reading_shortcuts).pack(side='left', padx=3)
        ttk.Button(row, text='Disable shortcuts', command=lambda: command('selection-shortcuts-disable')).pack(side='left', padx=3)
        ttk.Label(frame, textvariable=self.reading_shortcuts, style='Card.TLabel', wraplength=760).pack(anchor='w', pady=8)
        row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=8)
        ttk.Button(row, text='Read selected text / Stop', command=lambda: command('selection-toggle')).pack(side='left', padx=3)
        ttk.Button(row, text='Read copied text / Stop', command=lambda: command('selection-toggle', clipboard=True)).pack(side='left', padx=3)
        ttk.Button(row, text='Stop reading', command=lambda: command('selection-stop')).pack(side='left', padx=3)
        ttk.Label(frame, textvariable=self.reading_state, style='Card.TLabel', wraplength=760).pack(anchor='w', pady=8)
        ttk.Label(frame, text='The Linux AppImage bundles clipboard readers for Wayland and X11. Some Wine applications do not publish selected text: copy it and use Read copied text explicitly. AKS does not silently read a stale clipboard.',
                  style='Card.TLabel', wraplength=760).pack(anchor='w', pady=8)
        def install_action():
            from .selection import install_action
            self.worker(lambda: install_action(self.path), lambda _: self.status.set('Desktop action installed. Assign its shortcut in Plasma Keyboard settings.'))
        ttk.Button(frame, text='Install optional desktop shortcut action', command=install_action).pack(anchor='w', pady=8)

    def enable_reading_shortcuts(self):
        from .speech_dispatcher import prepare_reading
        if self.busy or not self.save():
            return
        self.reading_state.set('Preparing Akousousin speech support…')
        def enable():
            # Local preparation preserves copyable RestartError recovery details.
            # The controller also checks prerequisites for non-panel callers.
            prepare_reading(self.path)
            return runtime.call(self.path, {'command': 'selection-shortcuts-enable'})
        self.worker(enable, lambda result: self.reading_state.set(result['state']))

    def check_updates(self):
        if self.busy:
            return
        self.update_status.set('Checking for updates…')
        def checked(update):
            if update is None:
                self.update_status.set('No newer compatible release is available.')
                return
            self.update_status.set(f'Update available: {update["version"]}')
            self.confirm_update(update)
        self.worker(lambda: updates.perform_check(self.path), checked)

    def confirm_update(self, update):
        if self.busy or self.updating:
            return
        if not updates.is_appimage():
            if messagebox.askyesno('Akousousin update available',
                    f'Akousousin {update["version"]} is available. Open its download page?\n\n'
                    'Install the new tar bundle using its installer, or update through your package manager.', parent=self.root):
                webbrowser.open(updates.download_page(update))
            return
        text = (f'Update from {__version__} to {update["version"]}?\n\n'
                'Close Wine applications first. Speech will stop and the control panel will restart. '
                'Your voices and preferences will be kept.')
        if not messagebox.askyesno('Akousousin update', text, parent=self.root):
            return
        if self.save():
            self.updating = True
            self.update_status.set('Updating… Progress is shown below. Please keep this window open.')
            self.worker(lambda: updates.install(update, self.path), lambda _: self.root.after_idle(self.root.destroy), parallel=True)

    def save(self):
        try:
            self.config.update(speed=round(float(self.speed.get()) * 4) / 4, volume=float(self.volume.get()) / 100,
                               noise_scale=float(self.noise.get()), noise_w_scale=float(self.noise_w.get()),
                               idle_timeout=int(self.idle_timeout.get()), port=int(self.port.get()), wine_prefix=self.prefix.get(), wine=self.wine.get(),
                               book_language=next((code for code in {v['language'] for v in self.config['voices'].values()}
                                                   if label(code) == self.language.get()), ''))
            settings.save(self.path, self.config)
            self.status.set('Preferences saved. They apply to new speech.')
            return True
        except (ValueError, tk.TclError) as error:
            show_error(self.root, error, 'Preferences')
            return False

    def dispatcher_install(self, remove):
        from .speech_dispatcher import configure
        if not self.save():
            return
        def completed(_):
            self.config = settings.load(self.path)
            if remove:
                self.status.set('Speech Dispatcher support removed; the previous default was restored.')
            elif self.config.get('speechd_setup_pending'):
                self.status.set('Speech Dispatcher support registered. Download or import a voice to make AKS the default; the existing default is unchanged until then.')
            else:
                self.status.set('Akousousin is the Speech Dispatcher default. Other engines remain available.')
        self.worker(lambda: configure(self.path, remove=remove), completed)

    def install(self):
        if not self.save():
            return
        prefix, wine = self.config['wine_prefix'] or None, self.config['wine'] or None
        def installed(_):
            settings.register(self.path, prefix, wine)
            self.status.set('Installed. Restart the Windows application to use the new default.')
        self.worker(lambda: Installer(resources.root(), prefix, wine).install(self.config, self.path), installed)

    def uninstall(self):
        if not messagebox.askyesno('Uninstall Akousousin', 'Remove Akousousin’s private DLLs and restore speech registration in this installation?'):
            return
        prefix, wine = self.config['wine_prefix'] or None, self.config['wine'] or None
        self.worker(lambda: Installer(resources.root(), prefix, wine).uninstall(),
                    lambda _: self.status.set('Uninstalled; original registration restored. Voice downloads were retained.'))

    def start_server(self):
        if not self.config['voices']:
            messagebox.showinfo('Speech service', 'Import or download a voice in Voice library first.')
            return
        if not self.save():
            return
        def begin():
            return runtime.call(self.path, {'command': 'start'})
        self.worker(begin, lambda _: self.status.set('Server ready. It can keep running when this panel closes.'))

    def stop_server(self):
        self.worker(lambda: runtime.call(self.path, {'command': 'stop'}, launch=False),
                    lambda stopped: self.status.set('Server stopping.' if stopped else 'No server owned by this profile was stopped.'),
                    parallel=True)

    def play(self):
        if not self.config['voices']:
            messagebox.showinfo('Preview', 'Import or download a voice in Voice library first.')
            return
        if not self.save():
            return
        text = self.preview.get()
        def preview():
            from . import speech_gate
            gate = speech_gate.snapshot(self.path)
            if gate[0]:
                return 'Preview muted while dictation is active.'
            runtime.call(self.path, {'command': 'start'})
            request = urllib.request.Request(f'http://127.0.0.1:{self.config["port"]}/synthesize',
                        json.dumps({'text': text, 'voice': self.config['voice']}).encode(),
                        {'Content-Type': 'application/json'})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=65) as response:
                data = response.read()
            path = settings.data_path() / 'preview.wav'
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            if speech_gate.suppressed(self.path, gate):
                return 'Preview muted while dictation is active.'
            if os.name == 'nt':
                import winsound
                import io
                import time
                import wave
                with wave.open(io.BytesIO(data), 'rb') as sound:
                    duration = sound.getnframes() / sound.getframerate()
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                deadline = time.monotonic() + duration
                try:
                    while time.monotonic() < deadline:
                        if speech_gate.suppressed(self.path, gate):
                            return 'Preview muted while dictation is active.'
                        time.sleep(.025)
                finally:
                    winsound.PlaySound(None, 0)
            else:
                from .playback import play_wav
                if not play_wav(path, cancelled=lambda: speech_gate.suppressed(self.path, gate)):
                    return 'Preview muted while dictation is active.'
            return 'Preview complete.'
        self.worker(preview, self.status.set)

    def close(self):
        if self.updating:
            messagebox.showinfo('Akousousin update', 'Please wait for the update to finish before closing the panel.')
            return
        if self.busy and not messagebox.askyesno('Akousousin', 'An operation is still running. Close the panel?'):
            return
        self.root.destroy()

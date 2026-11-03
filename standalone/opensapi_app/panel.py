"""Desktop control panel. All downloads, Wine calls and synthesis run off the UI thread."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import urllib.request
import webbrowser

from . import catalogue, resources, settings
from .install import Installer
from .service import Service


class Panel:
    def __init__(self, path):
        self.path = Path(path)
        self.config = resources.bootstrap(path)
        self.library = catalogue.catalogue(resources.root())
        self.service = Service(path)
        self.events = queue.Queue()
        self.busy = 0
        self.root = tk.Tk()
        self.root.title('OpenSAPI — Speech for your applications')
        self.root.geometry('1160x820')
        self.root.minsize(940, 700)
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
        ttk.Label(header, text='▥  OpenSAPI', style='Title.TLabel').pack(side='left')
        ttk.Label(header, text='Speech for your applications', padding=(18, 8)).pack(side='left')
        ttk.Label(header, text='Standalone beta').pack(side='right')
        body = ttk.Frame(self.root)
        body.pack(fill='both', expand=True, padx=20)
        nav = ttk.Frame(body, width=165, padding=(0, 10, 16, 0))
        nav.pack(side='left', fill='y')
        self.content = ttk.Frame(body)
        self.content.pack(side='left', fill='both', expand=True)
        self.pages = {}
        for name in ('Overview', 'Voice library', 'Languages', 'Settings'):
            ttk.Button(nav, text=name, command=lambda name=name: self.show(name)).pack(fill='x', pady=4)
            self.pages[name] = ttk.Frame(self.content)
        self.status = tk.StringVar(value='Ready')
        self.server_status = tk.StringVar(value='Checking service…')
        self.prefix = tk.StringVar(value=self.config['wine_prefix'])
        self.wine = tk.StringVar(value=self.config['wine'])
        self.preview = tk.StringVar(value='The quick brown fox jumps over the lazy dog.')
        self.speed = tk.DoubleVar(value=self.config['speed'])
        self.volume = tk.DoubleVar(value=self.config['volume'] * 100)
        self.noise = tk.DoubleVar(value=self.config['noise_scale'])
        self.noise_w = tk.DoubleVar(value=self.config['noise_w_scale'])
        self.language = tk.StringVar(value=self.config['book_language'] or 'Follow application')
        self.port = tk.IntVar(value=self.config['port'])
        self.build_overview()
        self.build_library()
        self.build_languages()
        self.build_settings()
        footer = ttk.Frame(self.root, padding=(22, 12))
        footer.pack(fill='x')
        ttk.Label(footer, textvariable=self.status, wraplength=760).pack(side='left')
        self.progress = ttk.Progressbar(footer, mode='indeterminate', length=110)
        self.progress.pack(side='right')
        self.show('Overview')
        self.refresh_library()
        self.root.after(100, self.poll)
        self.root.after(200, self.check_server)

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
                self.events.put(('error', None, str(error)))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, callback, result = self.events.get_nowait()
                self.busy = max(0, self.busy - 1)
                if kind == 'error':
                    self.status.set(result)
                    messagebox.showerror('OpenSAPI', result, parent=self.root)
                elif callback:
                    callback(result)
        except queue.Empty:
            pass
        if not self.busy:
            self.progress.stop()
        self.root.after(100, self.poll)

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
        frame = self.card(page, 'Speech service')
        ttk.Label(frame, textvariable=self.server_status, style='Card.TLabel').pack(side='left')
        ttk.Button(frame, text='Start server', style='Accent.TButton', command=self.start_server).pack(side='right', padx=4)
        ttk.Button(frame, text='Stop server', command=self.stop_server).pack(side='right', padx=4)
        frame = self.card(page, 'Default voice & preview')
        self.default_label = ttk.Label(frame, text='', style='Card.TLabel', wraplength=790)
        self.default_label.pack(anchor='w', pady=(0, 12))
        ttk.Entry(frame, textvariable=self.preview).pack(fill='x', pady=8)
        ttk.Button(frame, text='▶  Play sample', style='Accent.TButton', command=self.play).pack(anchor='w', pady=8)
        for label, variable, low, high in [('Default speed', self.speed, .5, 2), ('Volume', self.volume, 0, 100)]:
            row = ttk.Frame(frame, style='Card.TFrame')
            row.pack(fill='x', pady=8)
            ttk.Label(row, text=label, width=18, style='Card.TLabel').pack(side='left')
            ttk.Scale(row, variable=variable, from_=low, to=high).pack(side='left', fill='x', expand=True)
            ttk.Spinbox(row, textvariable=variable, from_=low, to=high, increment=.1 if high == 2 else 1,
                        width=7).pack(side='right', padx=(12, 0))
        ttk.Button(frame, text='Save playback preferences', command=self.save).pack(anchor='e', pady=8)
        ttk.Label(page, text='Preferences apply to new speech. Applications may need restarting after changing the default voice.',
                  wraplength=820).pack(anchor='w', padx=4)
        self.update_default()

    def update_default(self):
        voice = self.config['voices'].get(self.config['voice'])
        self.default_label.configure(text=f"{voice['name']} · {voice['language']} · {voice['quality']}" if voice else 'Choose a voice in Voice library')

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
        choices = ttk.Combobox(row, textvariable=self.filter, values=['All languages', *languages], width=16, state='readonly')
        choices.pack(side='left', padx=8)
        choices.bind('<<ComboboxSelected>>', lambda *_: self.refresh_library())
        self.installed_only = tk.BooleanVar()
        ttk.Checkbutton(row, text='Installed only', variable=self.installed_only,
                        command=self.refresh_library).pack(side='right')
        self.tree = ttk.Treeview(page, columns=('language', 'quality', 'size', 'status'), show='tree headings', height=12)
        self.tree.heading('#0', text='Voice')
        self.tree.column('#0', width=160)
        for name, width in [('language', 140), ('quality', 80), ('size', 80), ('status', 230)]:
            self.tree.heading(name, text=name.title())
            self.tree.column(name, width=width)
        self.tree.pack(fill='both', expand=True, pady=8)
        row = ttk.Frame(page)
        row.pack(fill='x', pady=8)
        ttk.Button(row, text='Review licence & download', command=self.download).pack(side='left', padx=3)
        ttk.Button(row, text='Make default', style='Accent.TButton', command=self.make_default).pack(side='left', padx=3)
        ttk.Button(row, text='Import local model', command=self.import_model).pack(side='left', padx=3)
        ttk.Label(page, text='Catalogue: Piper voices, pinned revision. Licences vary by voice; the bundled LJSpeech voice has reviewed provenance. Other downloads require your licence review.',
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
            if self.filter.get() != 'All languages' and entry['language']['code'] != self.filter.get():
                continue
            fields = f"{key} {entry['language']['name_english']} {entry['language']['name_native']}".casefold()
            if needle and needle not in fields:
                continue
            size = sum(f['size_bytes'] for p, f in entry['files'].items() if p.endswith('.onnx')) / 1000000
            status = ('Installed' if installed else 'Language resources unavailable'
                      if entry['language'].get('family') in catalogue.UNSUPPORTED_AUXILIARY
                      else 'Reviewed free-use' if key in catalogue.APPROVED else 'Licence review required')
            self.tree.insert('', 'end', iid=key, text=entry['name'], values=(entry['language']['code'],
                             entry['quality'], f'{size:.0f} MB', status))

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
                def downloaded(voice):
                    self.config['voices'][key] = voice
                    settings.save(self.path, self.config)
                    self.refresh_library()
                    self.refresh_languages()
                    self.status.set('Voice installed. Select Make default to use it.')
                self.worker(lambda: catalogue.install(self.library[key], settings.data_path() / 'voices', True), downloaded)
            ttk.Button(window, text='Download voice', command=begin, style='Accent.TButton').pack(pady=12)
        self.worker(lambda: catalogue.card(self.library[key]), review)

    def make_default(self):
        try:
            key = self.selected()
            if key not in self.config['voices']:
                raise ValueError('Download this voice first')
            self.config['voice'] = key
            language = self.config['voices'][key]['language']
            self.config['language_voices'][language] = key
            settings.save(self.path, self.config)
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
            config = json.loads(Path(model + '.json').read_text())
            key = Path(model).stem
            language = config.get('language', {}).get('code', 'en_US')
            self.config['voices'][key] = {'path': model, 'sample_rate': config['audio']['sample_rate'],
                                          'language': language, 'name': key, 'quality': 'local'}
            settings.save(self.path, self.config)
            # Imported models may not occur in the online catalogue; add a local row.
            self.library.setdefault(key, {'key': key, 'name': key, 'quality': 'local', 'files': {},
                                         'language': {'code': language, 'name_english': language, 'name_native': language}})
            self.refresh_library()
            self.refresh_languages()
        except Exception as error:
            messagebox.showerror('Import voice', str(error))

    def build_languages(self):
        page = self.pages['Languages']
        frame = self.card(page, 'Reading languages')
        ttk.Label(frame, text='Book language', style='Card.TLabel').pack(anchor='w')
        languages = sorted({v['language'] for v in self.config['voices'].values()})
        self.language_combo = ttk.Combobox(frame, textvariable=self.language,
                                           values=['Follow application', *languages], state='readonly')
        self.language_combo.pack(fill='x', pady=10)
        ttk.Label(frame, text='Follow application uses language IDs supplied through SAPI. It does not guess the language of individual words. Select a language manually for an entire book.',
                  wraplength=780, style='Card.TLabel').pack(anchor='w', pady=12)
        ttk.Label(frame, text='Preferred voices by language', style='Card.TLabel').pack(anchor='w')
        self.language_rows = ttk.Treeview(frame, columns=('voice',), show='tree headings', height=7)
        self.language_rows.heading('#0', text='Language')
        self.language_rows.heading('voice', text='Preferred voice')
        self.language_rows.pack(fill='x', pady=10)
        for language, voice in sorted(self.config['language_voices'].items()):
            self.language_rows.insert('', 'end', text=language, values=(voice,))
        ttk.Label(frame, text='Make default in Voice library also sets that language’s preferred voice. Unavailable language preferences fall back to the requested/default voice. Latin appears only if you import or obtain a suitable model.',
                  wraplength=780, style='Card.TLabel').pack(anchor='w', pady=12)
        ttk.Button(frame, text='Save language preference', command=self.save).pack(anchor='e')

    def refresh_languages(self):
        languages = sorted({v['language'] for v in self.config['voices'].values()})
        self.language_combo.configure(values=['Follow application', *languages])
        self.language_rows.delete(*self.language_rows.get_children())
        for language, voice in sorted(self.config['language_voices'].items()):
            self.language_rows.insert('', 'end', text=language, values=(voice,))

    def build_settings(self):
        page = self.pages['Settings']
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
        ttk.Label(frame, text='Close applications before installation. Original speech registry settings and replaced DLLs are backed up. Native Windows SAPI is never replaced; Windows voice installation requires administrator rights.',
                  wraplength=780, style='Card.TLabel').pack(anchor='w', pady=12)
        ttk.Button(frame, text='Install / apply voice registration', style='Accent.TButton', command=self.install).pack(side='left', padx=4)
        ttk.Button(frame, text='Uninstall & restore', command=self.uninstall).pack(side='left', padx=4)
        frame = self.card(page, 'Advanced synthesis')
        for text, variable in [('Generator variation (noise scale)', self.noise), ('Phoneme variation (noise width)', self.noise_w)]:
            row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=8)
            ttk.Label(row, text=text, style='Card.TLabel').pack(side='left')
            ttk.Spinbox(row, textvariable=variable, from_=0, to=2, increment=.05, width=8).pack(side='right')
        row = ttk.Frame(frame, style='Card.TFrame'); row.pack(fill='x', pady=8)
        ttk.Label(row, text='Loopback port', style='Card.TLabel').pack(side='left')
        ttk.Spinbox(row, textvariable=self.port, from_=1024, to=65535, width=8).pack(side='right')
        ttk.Label(frame, text='Piper has no general pitch slider. Speed and synthesis variation are supported. A port change requires server restart and reapplying voice registration.',
                  wraplength=780, style='Card.TLabel').pack(anchor='w', pady=12)
        ttk.Button(frame, text='Save settings', command=self.save).pack(anchor='e')
        ttk.Button(page, text='Open service log', command=lambda: webbrowser.open(self.service.log.as_uri())).pack(anchor='w')

    def save(self):
        try:
            self.config.update(speed=float(self.speed.get()), volume=float(self.volume.get()) / 100,
                               noise_scale=float(self.noise.get()), noise_w_scale=float(self.noise_w.get()),
                               port=int(self.port.get()), wine_prefix=self.prefix.get(), wine=self.wine.get(),
                               book_language='' if self.language.get() == 'Follow application' else self.language.get())
            settings.save(self.path, self.config)
            self.status.set('Preferences saved. They apply to new speech.')
            return True
        except (ValueError, tk.TclError) as error:
            messagebox.showerror('Preferences', str(error))
            return False

    def install(self):
        if not self.save():
            return
        prefix, wine = self.config['wine_prefix'] or None, self.config['wine'] or None
        self.worker(lambda: Installer(resources.root(), prefix, wine).install(self.config),
                    lambda _: self.status.set('Installed. Restart the Windows application to use the new default.'))

    def uninstall(self):
        if not messagebox.askyesno('Uninstall OpenSAPI', 'Restore original DLLs and speech registration in this installation?'):
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
            resources.persistent_runtime(self.path)
            return self.service.start(self.config['port'])
        self.worker(begin, lambda _: self.status.set('Server ready. It can keep running when this panel closes.'))

    def stop_server(self):
        self.worker(lambda: self.service.stop(self.config['port']),
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
            resources.persistent_runtime(self.path)
            self.service.start(self.config['port'])
            request = urllib.request.Request(f'http://127.0.0.1:{self.config["port"]}/synthesize',
                        json.dumps({'text': text, 'voice': self.config['voice']}).encode(),
                        {'Content-Type': 'application/json'})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=65) as response:
                data = response.read()
            path = settings.data_path() / 'preview.wav'
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            if os.name == 'nt':
                import winsound
                winsound.PlaySound(str(path), winsound.SND_FILENAME)
            else:
                player = next((shutil.which(name) for name in ('pw-play', 'paplay', 'aplay') if shutil.which(name)), None)
                if player:
                    subprocess.run([player, str(path)], check=True, timeout=120)
                else:
                    return f'Preview saved to {path}; no pw-play, paplay or aplay audio player was found.'
            return 'Preview complete.'
        self.worker(preview, self.status.set)

    def close(self):
        if self.busy and not messagebox.askyesno('OpenSAPI', 'An operation is still running. Close the panel?'):
            return
        self.root.destroy()

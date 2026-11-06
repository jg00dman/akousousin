# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Selectable errors with copyable recovery commands and separate diagnostics."""
import tkinter as tk
from tkinter import ttk


def show_error(parent, error, title='Akousousin'):
    message = getattr(error, 'message', str(error))
    command = getattr(error, 'command', '')
    details = getattr(error, 'details', '')
    window = tk.Toplevel(parent)
    window.title(getattr(error, 'title', title))
    window.transient(parent)
    window.geometry(f'{min(760, parent.winfo_screenwidth() - 60)}x{340 if command else 260}')
    window.minsize(420, 230)
    body = ttk.Frame(window, padding=16); body.pack(fill='both', expand=True)
    text = tk.Text(body, height=4, wrap='word', relief='flat', font='TkDefaultFont')
    text.pack(fill='both', expand=True)
    text.insert('1.0', message); text.configure(state='disabled')

    def copy(value):
        parent.clipboard_clear()
        parent.clipboard_append(value)

    if command:
        row = ttk.Frame(body); row.pack(fill='x', pady=10)
        field = ttk.Entry(row)
        field.insert(0, command); field.configure(state='readonly')
        field.pack(side='left', fill='x', expand=True)
        def select_command(event):
            field.selection_range(0, 'end')
            return 'break'
        field.bind('<Control-a>', select_command)
        ttk.Button(row, text='Copy command', command=lambda: copy(command)).pack(side='right', padx=(8, 0))
    buttons = ttk.Frame(body); buttons.pack(fill='x', pady=(8, 0))
    if details:
        diagnostic = ttk.Frame(body)
        diagnostic.columnconfigure(0, weight=1); diagnostic.rowconfigure(0, weight=1)
        box = tk.Text(diagnostic, height=7, wrap='word')
        scroll = ttk.Scrollbar(diagnostic, command=box.yview)
        box.configure(yscrollcommand=scroll.set)
        box.grid(row=0, column=0, sticky='nsew'); scroll.grid(row=0, column=1, sticky='ns')
        box.insert('1.0', details); box.configure(state='disabled')
        def reveal():
            if diagnostic.winfo_manager():
                diagnostic.pack_forget()
                toggle.configure(text='Show technical details')
            else:
                diagnostic.pack(fill='both', expand=True, before=buttons, pady=8)
                toggle.configure(text='Hide technical details')
                window.geometry(f'{window.winfo_width()}x{min(560, parent.winfo_screenheight() - 80)}')
        toggle = ttk.Button(buttons, text='Show technical details', command=reveal)
        toggle.pack(side='left')
    full = message + ('\n\n' + command if command else '') + ('\n\n' + details if details else '')
    ttk.Button(buttons, text='Copy details' if details else 'Copy message', command=lambda: copy(full)).pack(side='left', padx=8)
    ttk.Button(buttons, text='OK', command=window.destroy).pack(side='right')
    text.focus_set()
    return window

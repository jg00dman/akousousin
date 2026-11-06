# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Scrollable form with wheel routing confined to its own visible page."""
import tkinter as tk
from tkinter import ttk


class ScrollArea(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg='#f4f5f3')
        self.scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.scrollbar.pack(side='right', fill='y')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.inner = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.inner.bind('<Configure>', lambda event: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', self.resize)
        self.root = self.winfo_toplevel()
        self.bindings = [(event, self.root.bind(event, self.wheel, add='+'))
                         for event in ('<MouseWheel>', '<Button-4>', '<Button-5>')]
        self.bind('<Destroy>', self.destroyed, add='+')

    def resize(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        def wrap(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Label) and self.canvas.winfo_pixels(str(child.cget('wraplength') or 0)):
                    child.configure(wraplength=max(200, event.width - 60))
                wrap(child)
        wrap(self.inner)

    def wheel(self, event):
        widget = event.widget
        current = widget
        while current is not None and current is not self:
            current = getattr(current, 'master', None)
        if current is None or not self.winfo_viewable():
            return
        # Native scrolling controls retain their own wheel behavior.
        if isinstance(widget, (ttk.Treeview, ttk.Combobox, ttk.Spinbox, tk.Listbox)):
            return
        if isinstance(widget, tk.Text) and widget.yview() != (0.0, 1.0):
            return
        if self.canvas.yview() == (0.0, 1.0):
            return
        if getattr(event, 'num', None) in (4, 5):
            steps = -1 if event.num == 4 else 1
        else:
            delta = getattr(event, 'delta', 0)
            if not delta:
                return
            steps = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        self.canvas.yview_scroll(steps * 3, 'units')
        return 'break'

    def destroyed(self, event):
        if event.widget is self:
            for sequence, identifier in self.bindings:
                try:
                    self.root.unbind(sequence, identifier)
                except tk.TclError:
                    pass

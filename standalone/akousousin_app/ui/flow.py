# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Columns of cards that sit side by side when there is room and stack when not."""
from PySide6.QtWidgets import QGridLayout, QVBoxLayout, QWidget


class Columns(QWidget):
    def __init__(self, groups, spacing=18, minimum=420, weights=None):
        super().__init__()
        self.minimum = minimum
        self.weights = weights or [1] * len(groups)
        self.columns = []
        for group in groups:
            column = QWidget()
            layout = QVBoxLayout(column)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(spacing)
            for item in group:
                layout.addWidget(item)
            layout.addStretch(1)
            self.columns.append(column)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(spacing)
        self.wide = None
        self._place(True)

    def _place(self, wide):
        if wide == self.wide:
            return
        self.wide = wide
        for column in self.columns:
            self.grid.removeWidget(column)
        for index, column in enumerate(self.columns):
            if wide:
                self.grid.addWidget(column, 0, index)
                self.grid.setColumnStretch(index, self.weights[index])
            else:
                self.grid.addWidget(column, index, 0)
        if not wide:
            for index in range(1, len(self.columns)):
                self.grid.setColumnStretch(index, 0)

    def resizeEvent(self, event):
        self._place(event.size().width() >= self.minimum * len(self.columns))
        super().resizeEvent(event)

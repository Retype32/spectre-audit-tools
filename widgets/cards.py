"""
widgets/cards.py — small reusable card-style widgets.

Card         — titled surface for grouping content
StatCard     — clickable stat tile with big number + label
FieldLabel   — small uppercase label for form fields
StatusPill   — compact coloured status text
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
)

import theme as _theme
from theme import Theme


class Card(QFrame):
    """Surface card with subtle border. Use for grouping content."""
    def __init__(self, title="", subtitle="", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)
        if title or subtitle:
            head = QHBoxLayout(); head.setSpacing(10)
            if title:
                t = QLabel(title); t.setObjectName("cardTitle")
                head.addWidget(t)
            if subtitle:
                s = QLabel(subtitle); s.setObjectName("cardSubtitle")
                head.addWidget(s)
            head.addStretch()
            outer.addLayout(head)
            div = QFrame(); div.setFixedHeight(1)
            div.setStyleSheet(f"background: {Theme.BORDER_S};")
            outer.addWidget(div)
        # body container
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        outer.addLayout(self.body)


class StatCard(QFrame):
    """Compact stat tile with label, big number, optional icon and click action."""
    clicked = Signal()

    def __init__(self, label, value="0", color=None, icon="", clickable=False, parent=None):
        super().__init__(parent)
        self.setObjectName("cardElevated")
        self._color = color or Theme.ACCENT
        self._clickable = clickable
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if clickable:
            self.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)

        top = QHBoxLayout(); top.setSpacing(8)
        if icon:
            ic = QLabel(icon); ic.setStyleSheet(f"color:{self._color}; font-size:13px;")
            top.addWidget(ic)
        lbl = QLabel(label); lbl.setObjectName("sectionLabel")
        top.addWidget(lbl); top.addStretch()
        lay.addLayout(top)

        self.value_lbl = QLabel(str(value))
        self._refresh_value_style()
        lay.addWidget(self.value_lbl)

    def _refresh_value_style(self):
        fm = _theme.FONT_MONO()
        self.value_lbl.setStyleSheet(
            f"color: {self._color}; font-size: 26px; font-weight: 700; "
            f"font-family: '{fm}', Consolas, monospace; letter-spacing: -0.5px;"
        )

    def set_value(self, v):
        self.value_lbl.setText(str(v))

    def mouseReleaseEvent(self, e):
        if self._clickable and e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class FieldLabel(QLabel):
    """Form field label."""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("fieldLabel")


class StatusPill(QLabel):
    """Compact coloured status text."""
    LEVELS = {
        "info":    Theme.INFO,
        "success": Theme.OK,
        "warning": Theme.WARN,
        "danger":  Theme.DANGER,
        "muted":   Theme.TXT_3,
    }

    def __init__(self, text="", level="info", parent=None):
        super().__init__(parent)
        self.set(text, level)

    def set(self, text, level="info"):
        c = self.LEVELS.get(level, Theme.TXT_2)
        self.setStyleSheet(
            f"color: {c}; font-size: 11px; font-weight: 600; letter-spacing: 0.5px;"
        )
        self.setText(text)

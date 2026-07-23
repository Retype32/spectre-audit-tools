"""
pages/settings.py — Settings page (appearance only, no functional code).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QApplication, QScrollArea
)

import theme as _theme
from theme import Theme, FONT_PRESETS, set_font_preset, build_qss


# =============================================================================
# Helpers
# =============================================================================

def _section_label(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{Theme.TXT_DIM}; font-size:9.5px; font-weight:700; letter-spacing:2px;"
    )
    return lbl


def _divider():
    d = QFrame()
    d.setFixedHeight(1)
    d.setStyleSheet(f"background:{Theme.BORDER_S};")
    return d


# =============================================================================
# Settings page
# =============================================================================

class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        # Scrollable root so nothing gets clipped on small screens
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        root = QVBoxLayout(inner)
        root.setContentsMargins(40, 36, 40, 36)
        root.setSpacing(28)
        root.setAlignment(Qt.AlignTop)

        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # ── Page heading ─────────────────────────────────────────────
        heading = QLabel("Settings")
        heading.setStyleSheet(
            f"color:{Theme.TXT}; font-size:22px; font-weight:700; letter-spacing:0.2px;"
        )
        root.addWidget(heading)

        sub = QLabel("Appearance & display preferences")
        sub.setStyleSheet(f"color:{Theme.TXT_3}; font-size:13px; margin-top:-16px;")
        root.addWidget(sub)

        # ── Section: Typography ──────────────────────────────────────
        root.addWidget(_section_label("TYPOGRAPHY"))
        root.addWidget(self._build_font_card())

        # ── Section: Theme ───────────────────────────────────────────
        root.addWidget(_section_label("COLOR THEME"))
        root.addWidget(self._build_theme_card())

        root.addStretch()

    # ------------------------------------------------------------------
    def _build_font_card(self):
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            f"QFrame#card_font {{"
            f"  background:{Theme.SURFACE}; border:1px solid {Theme.BORDER_S}; border-radius:8px;"
            f"}}"
        )
        card.setObjectName("card_font")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(16)

        title = QLabel("Interface Font")
        title.setStyleSheet(f"color:{Theme.TXT}; font-size:14px; font-weight:600;")
        lay.addWidget(title)

        desc = QLabel(
            "Selects the typeface used across all UI elements. "
            "Table cells and numeric data automatically use the paired monospace variant."
        )
        desc.setStyleSheet(f"color:{Theme.TXT_3}; font-size:12px;")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        lay.addWidget(_divider())

        # Font preset tiles
        grid = QHBoxLayout()
        grid.setSpacing(10)
        grid.setAlignment(Qt.AlignLeft)
        self._font_btns = []

        for i, preset in enumerate(FONT_PRESETS):
            tile = self._make_font_tile(i, preset)
            grid.addWidget(tile)
            self._font_btns.append(tile)

        hint = QLabel(
            "Tip: install missing fonts from fonts.google.com for the best result. "
            "Fallback system fonts are used automatically if not installed."
        )
        hint.setStyleSheet(f"color:{Theme.TXT_DIM}; font-size:11px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        grid.addStretch()
        lay.addLayout(grid)

        # Info strip — active font details
        self._font_info = QLabel()
        self._refresh_font_info()
        self._font_info.setStyleSheet(
            f"color:{Theme.TXT_3}; font-size:11px; font-family: monospace; "
            f"background:{Theme.ELEVATED}; border-radius:5px; padding:8px 14px;"
        )
        lay.addWidget(self._font_info)

        return card

    def _make_font_tile(self, idx, preset):
        active = (idx == _theme._active_preset_idx)
        fallback = preset.get("fallback", "").split(",")[0].strip()
        subtitle = preset["display"] if preset["display"] != preset["name"] else fallback
        btn = QPushButton(f"{preset['name']}\n{subtitle}")
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setFixedSize(112, 68)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(self._font_tile_style(active))
        btn.clicked.connect(lambda _=False, i=idx: self._apply_font(i))
        return btn

    def _font_tile_style(self, active):
        if active:
            return (
                f"QPushButton {{"
                f"  background:{Theme.SELECTED}; color:{Theme.ACCENT};"
                f"  border:1.5px solid {Theme.ACCENT}; border-radius:7px;"
                f"  font-size:12px; font-weight:700; padding:6px 10px; text-align:left;"
                f"}}"
                f"QPushButton:hover {{ background:{Theme.SELECTED}; }}"
            )
        return (
            f"QPushButton {{"
            f"  background:{Theme.ELEVATED}; color:{Theme.TXT_2};"
            f"  border:1px solid {Theme.BORDER}; border-radius:7px;"
            f"  font-size:12px; font-weight:500; padding:6px 10px; text-align:left;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{Theme.HOVER}; color:{Theme.TXT}; border-color:{Theme.TXT_3};"
            f"}}"
        )

    def _apply_font(self, idx):
        set_font_preset(idx)
        QApplication.instance().setStyleSheet(build_qss())
        for i, btn in enumerate(self._font_btns):
            btn.setStyleSheet(self._font_tile_style(i == idx))
            btn.setChecked(i == idx)
        self._refresh_font_info()

    def _refresh_font_info(self):
        fp = _theme.get_font_preset()
        self._font_info.setText(
            f"Active: {fp['display']}   ·   Mono: {fp['mono'].split(',')[0].strip()}   ·   Fallback: {fp['fallback'].split(',')[0].strip()}"
        )

    # ------------------------------------------------------------------
    def _build_theme_card(self):
        card = QFrame()
        card.setObjectName("card_theme")
        card.setStyleSheet(
            f"QFrame#card_theme {{"
            f"  background:{Theme.SURFACE}; border:1px solid {Theme.BORDER_S}; border-radius:8px;"
            f"}}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(16)

        title = QLabel("Color Theme")
        title.setStyleSheet(f"color:{Theme.TXT}; font-size:14px; font-weight:600;")
        lay.addWidget(title)

        desc = QLabel(
            "Full color themes coming in a future update. "
            "Currently using: Deep Obsidian (default)."
        )
        desc.setStyleSheet(f"color:{Theme.TXT_3}; font-size:12px;")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        lay.addWidget(_divider())

        # Theme tiles row — placeholder for future themes
        tiles_row = QHBoxLayout()
        tiles_row.setSpacing(10)
        tiles_row.setAlignment(Qt.AlignLeft)

        themes = [
            ("Deep Obsidian", Theme.ACCENT,  True),
            ("Slate",         "#94a3b8",      False),
            ("Ember",         "#f97316",      False),
            ("Forest",        "#22c55e",      False),
        ]
        for name, color, active in themes:
            tile = self._make_theme_tile(name, color, active)
            tiles_row.addWidget(tile)

        tiles_row.addStretch()
        lay.addLayout(tiles_row)

        note = QLabel("⚠  Non-default themes are placeholders — they will be configurable in v2.1.")
        note.setStyleSheet(f"color:{Theme.TXT_DIM}; font-size:11px;")
        lay.addWidget(note)

        return card

    def _make_theme_tile(self, name, accent_color, active):
        btn = QPushButton(name)
        btn.setFixedSize(120, 52)
        btn.setCursor(Qt.PointingHandCursor if active else Qt.ArrowCursor)
        if active:
            style = (
                f"QPushButton {{"
                f"  background:{Theme.SELECTED}; color:{accent_color};"
                f"  border:1.5px solid {accent_color}; border-radius:7px;"
                f"  font-size:12px; font-weight:700; padding:6px 10px;"
                f"}}"
                f"QPushButton:hover {{ background:{Theme.SELECTED}; }}"
            )
        else:
            style = (
                f"QPushButton {{"
                f"  background:{Theme.ELEVATED}; color:{Theme.TXT_DIM};"
                f"  border:1px solid {Theme.BORDER_S}; border-radius:7px;"
                f"  font-size:12px; font-weight:400; padding:6px 10px;"
                f"}}"
            )
        btn.setStyleSheet(style)
        btn.setEnabled(active)
        return btn

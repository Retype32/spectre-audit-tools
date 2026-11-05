"""
pages/settings.py — Settings page: appearance and team targets.
"""
import datetime
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QApplication, QScrollArea, QGridLayout, QLineEdit
)

import theme as _theme
from theme import Theme, FONT_PRESETS, set_font_preset, build_qss
from config import TARGETS_FILE
from engine.targets import GROUPS, TARGETS, TargetError, read_targets_file, save_targets


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

def _fmt_target(value):
    """Show 10000.0 as "10,000" and 2.5 as "2.5" (no scientific notation)."""
    return f"{int(value):,}" if float(value).is_integer() else f"{value}"


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._targets_dirty = False
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

        sub = QLabel("Appearance, display preferences and team targets")
        sub.setStyleSheet(f"color:{Theme.TXT_3}; font-size:13px; margin-top:-16px;")
        root.addWidget(sub)

        # ── Section: Typography ──────────────────────────────────────
        root.addWidget(_section_label("TYPOGRAPHY"))
        root.addWidget(self._build_font_card())

        # ── Section: Theme ───────────────────────────────────────────
        root.addWidget(_section_label("COLOR THEME"))
        root.addWidget(self._build_theme_card())

        # ── Section: Team targets ────────────────────────────────────
        root.addWidget(_section_label("TEAM TARGETS"))
        root.addWidget(self._build_targets_card())

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

    # ------------------------------------------------------------------
    # Team targets
    # ------------------------------------------------------------------
    def _build_targets_card(self):
        card = QFrame()
        card.setObjectName("card_targets")
        card.setStyleSheet(
            f"QFrame#card_targets {{"
            f"  background:{Theme.SURFACE}; border:1px solid {Theme.BORDER_S}; border-radius:8px;"
            f"}}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(14)

        title = QLabel("Team Targets")
        title.setStyleSheet(f"color:{Theme.TXT}; font-size:14px; font-weight:600;")
        lay.addWidget(title)

        desc = QLabel(
            "Targets and rules the team works to. They are saved in one shared file, so "
            "everyone using this Spectre folder sees the same numbers. Leave a box empty to "
            "use the default shown in it. Slips per hour, bags carried over and the 360 rules "
            "change how cashier scores are calculated."
        )
        desc.setStyleSheet(f"color:{Theme.TXT_3}; font-size:12px;")
        desc.setWordWrap(True)
        lay.addWidget(desc)
        lay.addWidget(_divider())

        self._target_edits = {}
        for group in GROUPS:
            lay.addWidget(_section_label(group.upper()))
            grid = QGridLayout()
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(6)
            grid.setColumnStretch(3, 1)
            for row, t in enumerate(x for x in TARGETS if x.group == group):
                name = QLabel(t.label)
                name.setStyleSheet(f"color:{Theme.TXT_2}; font-size:12px;")
                name.setFixedWidth(230)

                edit = QLineEdit()
                edit.setFixedWidth(120)
                if t.default is not None:
                    edit.setPlaceholderText(f"{_fmt_target(t.default)} if empty")
                else:
                    edit.setPlaceholderText("No target")
                edit.setToolTip(t.description)
                edit.textEdited.connect(self._on_target_edited)
                self._target_edits[t.key] = edit

                unit = QLabel(f"{'at least' if t.better == 'higher' else 'at most'}  ·  {t.unit}")
                if t.kind == "rule":
                    unit.setText(f"rule  ·  {t.unit}")
                unit.setStyleSheet(f"color:{Theme.TXT_3}; font-size:11px;")
                unit.setFixedWidth(130)

                hint = QLabel(t.description)
                hint.setStyleSheet(f"color:{Theme.TXT_DIM}; font-size:11px;")
                hint.setWordWrap(True)

                grid.addWidget(name, row, 0)
                grid.addWidget(edit, row, 1)
                grid.addWidget(unit, row, 2)
                grid.addWidget(hint, row, 3)
            lay.addLayout(grid)

        lay.addWidget(_divider())
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        save_btn = QPushButton("Save Targets")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save_targets)
        reload_btn = QPushButton("Reload")
        reload_btn.setToolTip("Discard unsaved changes and show the targets in the shared file")
        reload_btn.clicked.connect(self._load_targets)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(reload_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._targets_status = QLabel()
        self._targets_status.setWordWrap(True)
        self._targets_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self._targets_status)

        self._load_targets()
        return card

    def _set_targets_status(self, text, level="info"):
        color = {"ok": Theme.OK, "warn": Theme.WARN, "error": Theme.DANGER}.get(level, Theme.TXT_3)
        self._targets_status.setStyleSheet(f"color:{color}; font-size:11px;")
        self._targets_status.setText(text)

    def _on_target_edited(self, _text):
        self._targets_dirty = True
        self._set_targets_status("Unsaved changes.", "warn")

    def _load_targets(self):
        targets, problem = read_targets_file(TARGETS_FILE)
        for key, edit in self._target_edits.items():
            edit.setText(_fmt_target(targets[key]) if key in targets else "")
        self._targets_dirty = False
        if problem:
            self._set_targets_status(f"Some saved targets could not be used: {problem}", "warn")
        elif targets:
            self._set_targets_status(f"{len(targets)} target(s) set.  Shared file: {TARGETS_FILE}")
        else:
            self._set_targets_status(f"No targets set yet.  Shared file: {TARGETS_FILE}")

    def _save_targets(self):
        values = {key: edit.text() for key, edit in self._target_edits.items()}
        try:
            saved = save_targets(values, TARGETS_FILE)
        except TargetError as e:
            self._set_targets_status("Not saved:\n" + "\n".join(e.errors), "error")
            return
        except Exception as e:
            logging.exception("Saving team targets")
            self._set_targets_status(f"Not saved: could not write {TARGETS_FILE}: {e}", "error")
            return
        for key, edit in self._target_edits.items():
            edit.setText(_fmt_target(saved[key]) if key in saved else "")
        self._targets_dirty = False
        self._set_targets_status(
            f"Saved {datetime.datetime.now():%H:%M}: {len(saved)} target(s).  "
            f"Shared file: {TARGETS_FILE}", "ok")
        logging.info(f"Team targets saved: {saved}")

    def showEvent(self, e):
        super().showEvent(e)
        # Pick up targets someone else saved, unless there are unsaved edits here
        if not self._targets_dirty:
            self._load_targets()

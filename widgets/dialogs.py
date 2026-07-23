"""
widgets/dialogs.py — application-wide dialogs.

DetailDialog        — stackable, multi-row detail dialog. One shared instance
                      per MainWindow; subsequent clicks add rows below the
                      previous ones. Cells whose values match across 2+
                      stacked rows get the accent tint.
FilteredRowsDialog  — modal dialog showing a filtered subset of rows in a
                      DataTable; double-click forwards to the shared
                      DetailDialog.
"""
from collections import Counter

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QScrollBar, QToolButton, QVBoxLayout, QWidget
)

from theme import Theme, FONT_MONO
from config import COL_DISC, AMOUNT
from utils import open_file_in_default_app
from widgets.data_table import DataTable


# =============================================================================
# DETAIL DIALOG — stackable, multi-row version
# =============================================================================
class DetailDialog(QDialog):
    """Stackable multi-row detail dialog.

    Use the class helper `DetailDialog.show_row(app, title, row_data)` from
    page click handlers — it manages a single shared instance per MainWindow
    and stacks rows on subsequent calls.
    """

    # ----- styling -----
    HEADER_CELL_CSS = (
        "background:{ELEVATED}; color:{TXT_2}; "
        "padding:7px 10px; border:1px solid {BORDER_S}; "
        "font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;"
    )
    VALUE_CELL_CSS = (
        "background:{BG}; color:{FG}; "
        "padding:9px 10px; border:1px solid {BORDER_S}; "
        "font-family:{MONO}; font-size:12px;"
    )
    # Tint applied when a value is shared across 2+ open rows.
    SHARED_CELL_CSS = (
        "background:#3a1f24; color:{FG}; "
        "padding:9px 10px; border:1px solid {ACCENT}; "
        "font-family:{MONO}; font-size:12px; font-weight:600;"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Row Details")
        self.setMinimumWidth(720)
        self.setMinimumHeight(320)
        self.resize(960, 480)

        # entries: list of dicts {"title": str, "data": dict}
        self._entries = []
        # Track the inner horizontal scrollbars of each stacked row so we
        # can drive them all from one master bar at the bottom.
        self._row_hbars = []
        # Re-entrancy guard for the two-way sync between row hbars and the
        # master hbar — when one side is updating the other, we don't want
        # the second side's valueChanged signal to bounce back.
        self._syncing_scroll = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        # Header
        head = QHBoxLayout()
        self._title_lbl = QLabel("Row Details")
        self._title_lbl.setObjectName("cardTitle")
        self._title_lbl.setStyleSheet(f"font-size: 16px; color: {Theme.TXT};")
        head.addWidget(self._title_lbl)
        head.addStretch()
        self._count_lbl = QLabel("")
        self._count_lbl.setObjectName("cardSubtitle")
        head.addWidget(self._count_lbl)
        outer.addLayout(head)

        # Hint about shared values
        self._hint = QLabel(
            "Click more result rows to stack them here. Cells with values "
            "shared across rows are highlighted."
        )
        self._hint.setStyleSheet(f"color:{Theme.TXT_3}; font-size:11px;")
        outer.addWidget(self._hint)

        # Scroll area containing the stack of rows
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(
            f"background:{Theme.SURFACE}; border:1px solid {Theme.BORDER_S}; border-radius:4px;"
        )
        self._scroll_inner = QWidget()
        self._stack_layout = QVBoxLayout(self._scroll_inner)
        self._stack_layout.setContentsMargins(8, 8, 8, 8)
        self._stack_layout.setSpacing(10)
        self._stack_layout.addStretch(1)
        self._scroll.setWidget(self._scroll_inner)
        outer.addWidget(self._scroll, 1)

        # Master horizontal scrollbar — drives every stacked row's inner
        # horizontal scroll at once so you can line up the same columns
        # across multiple transactions to eyeball matching quantities.
        self._master_hbar = QScrollBar(Qt.Horizontal)
        self._master_hbar.setObjectName("rowMasterScroll")
        self._master_hbar.setRange(0, 0)
        self._master_hbar.setVisible(False)
        self._master_hbar.setStyleSheet(
            f"QScrollBar:horizontal {{ background:{Theme.ELEVATED}; "
            f"border:1px solid {Theme.BORDER_S}; border-radius:4px; height:14px; margin:0; }}"
            f"QScrollBar::handle:horizontal {{ background:{Theme.ACCENT}; "
            f"border-radius:3px; min-width:40px; margin:2px; }}"
            f"QScrollBar::handle:horizontal:hover {{ background:{Theme.ACCENT_H}; }}"
            f"QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}"
            f"QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background:transparent; }}"
        )
        self._master_hbar.valueChanged.connect(self._on_master_scroll)
        self._master_hint = QLabel("Drag to scroll all transactions together")
        self._master_hint.setStyleSheet(f"color:{Theme.TXT_3}; font-size:10px;")
        self._master_hint.setVisible(False)
        outer.addWidget(self._master_hint)
        outer.addWidget(self._master_hbar)

        # Footer
        foot = QHBoxLayout()
        foot.addStretch()
        clear_btn = QPushButton("Clear All")
        clear_btn.setObjectName("ghost")
        clear_btn.clicked.connect(self._clear_all)
        foot.addWidget(clear_btn)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("primary")
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn)
        outer.addLayout(foot)

    # ------------------------------------------------------------------ helpers
    @classmethod
    def show_row(cls, app, title, row_data):
        """Add `row_data` to the app-wide shared dialog and ensure it's visible."""
        dlg = app.get_detail_dialog()
        dlg.add_row(title, row_data)
        if not dlg.isVisible():
            dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def add_row(self, title, row_data):
        """Append a new row and re-render."""
        if row_data is None:
            return
        self._entries.append({"title": str(title or "Row"), "data": dict(row_data)})
        self._rebuild()

    def _clear_all(self):
        """Remove every entry (does NOT close the window)."""
        self._entries.clear()
        self._rebuild()

    # Qt overrides --------------------------------------------------------------
    def accept(self):
        # Close button => wipe so the next click starts fresh.
        self._entries.clear()
        self._rebuild()
        super().accept()

    def reject(self):
        # Same behavior if user closes via Esc / window X.
        self._entries.clear()
        self._rebuild()
        super().reject()

    closeEvent = None  # use default close behavior; reject() handles state

    # ------------------------------------------------------------ value helpers
    @staticmethod
    def _normalize_value(v):
        """Return a canonical string form for cross-row equality checks.
        Empty/NA values do NOT count as shared (so blank cells aren't
        falsely tinted). Numbers are compared in their numeric form so
        100 == 100.0 == '100.00'."""
        if v is None:
            return None
        try:
            if pd.isna(v) and not isinstance(v, (list, dict)):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(v, str) and v.strip() == "":
            return None
        # Numeric canonicalization
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            try:
                f = float(v)
                if f.is_integer():
                    return f"#NUM:{int(f)}"
                return f"#NUM:{f:.10g}"
            except Exception:
                pass
        # String form — strip, casefold for case-insensitive equality
        s = str(v).strip()
        # Try to coerce numeric-looking strings (e.g. "€1,234.50") so they
        # match the underlying number form too.
        cleaned = (s.replace("\u20ac", "").replace("$", "").replace("\u00a3", "")
                    .replace(",", "").replace(" ", ""))
        try:
            f = float(cleaned)
            if f.is_integer():
                return f"#NUM:{int(f)}"
            return f"#NUM:{f:.10g}"
        except (ValueError, TypeError):
            return s.casefold()

    def _shared_value_set(self):
        """Return the set of normalized values that appear in 2+ entries."""
        if len(self._entries) < 2:
            return set()
        per_entry_values = []
        for e in self._entries:
            seen = set()
            for k, v in e["data"].items():
                if isinstance(k, str) and k.startswith("_"):
                    continue
                n = self._normalize_value(v)
                if n is not None:
                    seen.add(n)
            per_entry_values.append(seen)
        # A value is "shared" if it appears in at least 2 entries.
        counts = Counter()
        for sv in per_entry_values:
            for v in sv:
                counts[v] += 1
        return {v for v, c in counts.items() if c >= 2}

    # ------------------------------------------------------------ rendering
    def _rebuild(self):
        """Wipe the stacked rows and redraw from self._entries."""
        # Reset tracked per-row horizontal scrollbars before we rebuild.
        self._row_hbars = []
        # Remove existing widgets (keep the trailing stretch at the end)
        while self._stack_layout.count() > 1:
            item = self._stack_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        n = len(self._entries)
        self._count_lbl.setText(
            "" if n == 0 else (f"{n} row" if n == 1 else f"{n} rows stacked")
        )

        if n == 0:
            empty = QLabel("No rows. Click a result row in any page to add it here.")
            empty.setStyleSheet(f"color:{Theme.TXT_3}; padding:30px; font-size:12px;")
            empty.setAlignment(Qt.AlignCenter)
            self._stack_layout.insertWidget(self._stack_layout.count() - 1, empty)
            # Empty state — make absolutely sure the master scrollbar isn't
            # still showing from a previous set of rows.
            self._master_hbar.setVisible(False)
            self._master_hint.setVisible(False)
            return

        shared = self._shared_value_set()

        for idx, entry in enumerate(self._entries):
            self._stack_layout.insertWidget(
                self._stack_layout.count() - 1,
                self._build_row_widget(idx, entry, shared)
            )

        # Once all rows exist, hook the master bar up to them.
        self._sync_master_scrollbar()

    def _build_row_widget(self, idx, entry, shared):
        """One row strip: title bar + ✕ button + grid of header/value cells."""
        wrap = QFrame()
        wrap.setObjectName("cardElevated")
        wrap_lay = QVBoxLayout(wrap)
        wrap_lay.setContentsMargins(10, 8, 10, 10)
        wrap_lay.setSpacing(6)

        # Title bar
        bar = QHBoxLayout()
        bar.setSpacing(8)
        t = QLabel(entry["title"])
        t.setStyleSheet(f"color:{Theme.TXT}; font-size:13px; font-weight:600;")
        bar.addWidget(t)

        line = entry["data"].get("_line")
        if line:
            sub = QLabel(f"Excel row {line}")
            sub.setStyleSheet(f"color:{Theme.TXT_3}; font-size:11px;")
            bar.addWidget(sub)
        bar.addStretch()

        # Open File button if the row has a path
        fp = entry["data"].get("Full Path") or entry["data"].get("Report Folder Path")
        if fp:
            open_btn = QPushButton("Open File")
            open_btn.setObjectName("ghost")
            open_btn.setCursor(Qt.PointingHandCursor)
            open_btn.clicked.connect(lambda _=False, p=fp: open_file_in_default_app(p))
            bar.addWidget(open_btn)

        # Per-row ✕
        x_btn = QToolButton()
        x_btn.setText("✕")
        x_btn.setToolTip("Remove this row")
        x_btn.setCursor(Qt.PointingHandCursor)
        x_btn.setStyleSheet(
            f"QToolButton {{ background:transparent; color:{Theme.TXT_3}; "
            f"border:none; font-size:14px; padding:2px 8px; }}"
            f"QToolButton:hover {{ color:{Theme.DANGER}; }}"
        )
        x_btn.clicked.connect(lambda _=False, i=idx: self._remove_row(i))
        bar.addWidget(x_btn)
        wrap_lay.addLayout(bar)

        # Cells in a grid (one column per data field)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(1)
        grid.setVerticalSpacing(1)

        cols = [k for k in entry["data"].keys()
                if not (isinstance(k, str) and k.startswith("_"))]
        for ci, col_name in enumerate(cols):
            v = entry["data"][col_name]
            try:
                isna = pd.isna(v) and not isinstance(v, (list, dict))
            except Exception:
                isna = False
            val_str = "—" if (v is None or isna or v == "") else str(v)

            # Header
            h = QLabel(str(col_name))
            h.setStyleSheet(self.HEADER_CELL_CSS.format(
                ELEVATED=Theme.ELEVATED, TXT_2=Theme.TXT_2, BORDER_S=Theme.BORDER_S))
            h.setAlignment(Qt.AlignCenter)
            h.setMinimumWidth(110)
            grid.addWidget(h, 0, ci)

            # Value foreground color (special columns get specific colors)
            fg = Theme.TXT
            if col_name == COL_DISC:
                try:
                    fg = Theme.NEG if float(v) != 0 else Theme.POS
                except Exception:
                    pass
            elif col_name == AMOUNT:
                fg = Theme.MONEY

            normalized = self._normalize_value(v)
            is_shared = normalized is not None and normalized in shared

            vcell = QLabel(val_str)
            if is_shared:
                vcell.setStyleSheet(self.SHARED_CELL_CSS.format(
                    FG=Theme.ACCENT, BORDER_S=Theme.BORDER_S,
                    ACCENT=Theme.ACCENT, MONO=FONT_MONO))
                vcell.setToolTip("Shared with another open row")
            else:
                vcell.setStyleSheet(self.VALUE_CELL_CSS.format(
                    BG=Theme.SURFACE, FG=fg, BORDER_S=Theme.BORDER_S, MONO=FONT_MONO))
            vcell.setAlignment(Qt.AlignCenter)
            vcell.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(vcell, 1, ci)

        # Wrap the grid in a horizontal scroll so wide rows don't bust layout.
        h_scroll = QScrollArea()
        h_scroll.setWidgetResizable(True)
        h_scroll.setFrameShape(QFrame.NoFrame)
        h_scroll.setStyleSheet("background:transparent;")
        h_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # The per-row horizontal scrollbar is hidden — the master bar at
        # the bottom of the dialog drives every row in lockstep.
        h_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        h_scroll.setMinimumHeight(82)
        h_scroll.setWidget(grid_widget)
        wrap_lay.addWidget(h_scroll)

        # Track this row's inner hbar so the master can drive it.
        self._row_hbars.append(h_scroll.horizontalScrollBar())
        # Also listen for changes from the row's side. This catches inputs
        # we don't go through the master for — e.g. Shift+wheel scrolling
        # while hovering a row, or trackpad horizontal swipes — and pushes
        # the same ratio back to the master so all rows stay in lockstep.
        h_scroll.horizontalScrollBar().valueChanged.connect(
            self._on_row_scroll
        )

        return wrap

    def _remove_row(self, idx):
        if 0 <= idx < len(self._entries):
            del self._entries[idx]
            self._rebuild()

    # ------------------------------------------------------------ master scroll
    def _sync_master_scrollbar(self):
        """Match the master hbar's range/page-step to the widest row.

        Defers one event-loop tick because the inner scroll areas only know
        their content extent after Qt has laid them out.
        """
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._apply_master_range)

    def _apply_master_range(self):
        """Pick the largest inner-row scroll extent and mirror it on the master."""
        if not self._row_hbars:
            self._master_hbar.setVisible(False)
            self._master_hint.setVisible(False)
            return

        max_val = max((bar.maximum() for bar in self._row_hbars), default=0)
        # Use the widest row's page step so the handle width feels right.
        page_step = max(
            (bar.pageStep() for bar in self._row_hbars if bar.maximum() > 0),
            default=self._master_hbar.pageStep()
        )

        if max_val <= 0:
            # Nothing overflows — no need for the master bar.
            self._master_hbar.setVisible(False)
            self._master_hint.setVisible(False)
            return

        # Block signals so setting the range doesn't fire a scroll update.
        self._master_hbar.blockSignals(True)
        self._master_hbar.setRange(0, max_val)
        self._master_hbar.setPageStep(page_step)
        # Reset to the left edge whenever the row set changes.
        self._master_hbar.setValue(0)
        self._master_hbar.blockSignals(False)
        self._master_hbar.setVisible(True)
        self._master_hint.setVisible(True)
        # Push the rows back to 0 too so they start aligned. Guard the
        # sync flag because _on_row_scroll is connected to these bars.
        self._syncing_scroll = True
        try:
            for bar in self._row_hbars:
                bar.setValue(0)
        finally:
            self._syncing_scroll = False

    def _on_master_scroll(self, value):
        """Move every row's inner hbar in proportion to the master's position.

        Rows can have different content widths (some columns may be wider
        than others), so we scale by each row's own maximum instead of
        copying the value verbatim. Result: the rightmost edges line up
        when the master is fully right, and the left edges line up at 0.
        """
        if self._syncing_scroll:
            return
        master_max = self._master_hbar.maximum()
        if master_max <= 0:
            return
        ratio = value / master_max
        self._syncing_scroll = True
        try:
            for bar in self._row_hbars:
                bar.setValue(int(round(bar.maximum() * ratio)))
        finally:
            self._syncing_scroll = False

    def _on_row_scroll(self, _value):
        """A row's inner hbar moved on its own (mouse wheel, trackpad, etc.).

        Sender — the QScrollBar that just emitted valueChanged — tells us
        which row owned the gesture. We compute its ratio of progress and
        nudge the master + every other row to the same ratio so the whole
        stack stays aligned.
        """
        if self._syncing_scroll:
            return
        sender = self.sender()
        if sender is None or sender.maximum() <= 0:
            return
        ratio = sender.value() / sender.maximum()
        self._syncing_scroll = True
        try:
            # Update the master first (without triggering its own handler).
            master_max = self._master_hbar.maximum()
            if master_max > 0:
                self._master_hbar.setValue(int(round(master_max * ratio)))
            # Propagate to siblings so they don't drift from the gesture row.
            for bar in self._row_hbars:
                if bar is sender:
                    continue
                if bar.maximum() > 0:
                    bar.setValue(int(round(bar.maximum() * ratio)))
        finally:
            self._syncing_scroll = False


# =============================================================================
# FILTERED ROWS DIALOG
# =============================================================================
class FilteredRowsDialog(QDialog):
    """Modal dialog showing a filtered subset of rows in a DataTable."""
    def __init__(self, parent=None, title="", rows=None, columns=None, app=None):
        super().__init__(parent)
        # Allow callers to pass either `app=...` or rely on parent.app
        self._app = app if app is not None else getattr(parent, "app", None)
        self.setWindowTitle(title)
        self.resize(1100, 540)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        head = QLabel(title)
        head.setStyleSheet(f"color:{Theme.TXT}; font-size:15px; font-weight:600;")
        outer.addWidget(head)

        cols = columns or (list(rows[0].keys()) if rows else [])
        # Drop _ prefixed
        cols = [c for c in cols if not c.startswith('_')]
        self.table = DataTable(cols)
        if rows:
            df = pd.DataFrame([{c: r.get(c, "") for c in cols} for r in rows])
            self.table.set_dataframe(df)
            self.table.rowDoubleClicked.connect(self._show_detail)
        outer.addWidget(self.table, 1)

        foot = QHBoxLayout(); foot.addStretch()
        close_btn = QPushButton("Close"); close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn)
        outer.addLayout(foot)

        self._rows = rows or []

    def _show_detail(self, rd):
        title = rd.get('Cashier Name') or rd.get('Location Name') or 'Row'
        if self._app is not None:
            DetailDialog.show_row(self._app, title, rd)
        else:
            # Fallback if no app reference: build a one-shot dialog
            d = DetailDialog(self); d.add_row(title, rd); d.exec()

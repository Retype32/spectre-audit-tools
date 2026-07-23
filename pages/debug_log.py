"""
pages/debug_log.py — In-app Debug Log Viewer.

Displays the current session's log file content in a scrollable, filterable
panel.  Accessible via the Debug button at the bottom of the sidebar.

Log levels are colour-coded:
  ERROR / CRITICAL  →  red
  WARNING           →  amber
  INFO              →  normal text
  DEBUG             →  dimmed

The viewer also captures any unhandled Python exceptions that reach the
top-level exception hook and writes them to the log, so they appear here
immediately even if the app didn't show a dialog.
"""
import logging
import os
import sys
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QTextEdit, QLineEdit, QScrollArea, QSizePolicy,
    QComboBox,
)

from config import BASE_PATH
from theme import Theme


# ── In-memory log handler ─────────────────────────────────────────────────────
class _MemoryHandler(logging.Handler):
    """Stores log records in a list so the viewer can read them without
    touching the file system."""
    def __init__(self, maxlen: int = 2000):
        super().__init__()
        self._records: list[logging.LogRecord] = []
        self._maxlen = maxlen
        self._callbacks: list = []

    def emit(self, record: logging.LogRecord):
        self._records.append(record)
        if len(self._records) > self._maxlen:
            self._records = self._records[-self._maxlen:]
        for cb in self._callbacks:
            try:
                cb(record)
            except Exception:
                pass

    def get_records(self) -> list[logging.LogRecord]:
        return list(self._records)

    def add_callback(self, fn):
        self._callbacks.append(fn)

    def clear(self):
        self._records.clear()


# Module-level singleton — installed once at startup
_memory_handler: _MemoryHandler | None = None


def install_memory_handler() -> _MemoryHandler:
    """Install the in-memory handler on the root logger (idempotent)."""
    global _memory_handler
    if _memory_handler is not None:
        return _memory_handler

    _memory_handler = _MemoryHandler(maxlen=2000)
    _memory_handler.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                            datefmt="%H:%M:%S")
    _memory_handler.setFormatter(fmt)
    logging.getLogger().addHandler(_memory_handler)

    # Also hook unhandled Python exceptions so they show up in the viewer
    _orig_hook = sys.excepthook
    def _exc_hook(exc_type, exc_value, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.critical(f"UNHANDLED EXCEPTION:\n{msg}")
        _orig_hook(exc_type, exc_value, exc_tb)
    sys.excepthook = _exc_hook

    logging.info("Debug log viewer initialised — memory handler active")
    return _memory_handler


# ── Log level colours ─────────────────────────────────────────────────────────
_LEVEL_COLOR = {
    "CRITICAL": "#ff4444",
    "ERROR":    "#ff6b6b",
    "WARNING":  "#ffc857",
    "INFO":     "#c8ccd4",
    "DEBUG":    "#555e6e",
}


def _level_color(levelname: str) -> str:
    return _LEVEL_COLOR.get(levelname.upper(), "#c8ccd4")


# =============================================================================
class DebugLogPage(QWidget):
    """Full-page log viewer with live tail, filter, and clear."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auto_scroll = True
        self._filter_text = ""
        self._filter_level = "ALL"
        self._build()

        # Wire up live append when the page is visible
        handler = install_memory_handler()
        handler.add_callback(self._on_new_record)

        # Initial populate
        QTimer.singleShot(100, self._repopulate)

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        root = QVBoxLayout(inner)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        root.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # ── Header ────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(10)
        title = QLabel("Debug Log")
        title.setStyleSheet(f"color:{Theme.TXT};font-size:18px;font-weight:700;")
        hdr.addWidget(title)
        hdr.addStretch()

        # Level filter
        self._level_combo = QComboBox()
        for lvl in ["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            self._level_combo.addItem(lvl)
        self._level_combo.setFixedWidth(110)
        self._level_combo.currentTextChanged.connect(self._on_level_changed)
        hdr.addWidget(QLabel("Level:").also(
            lambda l: l.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")))
        hdr.addWidget(self._level_combo)

        # Text filter
        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Filter…")
        self._filter_input.setFixedWidth(200)
        self._filter_input.textChanged.connect(self._on_filter_changed)
        hdr.addWidget(self._filter_input)

        # Auto-scroll toggle
        self._autoscroll_btn = QPushButton("⬇  Auto-scroll ON")
        self._autoscroll_btn.setCheckable(True)
        self._autoscroll_btn.setChecked(True)
        self._autoscroll_btn.setFixedHeight(30)
        self._autoscroll_btn.clicked.connect(self._toggle_autoscroll)
        hdr.addWidget(self._autoscroll_btn)

        # Refresh
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("primary")
        refresh_btn.setFixedHeight(30)
        refresh_btn.clicked.connect(self._repopulate)
        hdr.addWidget(refresh_btn)

        # Clear
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._clear)
        hdr.addWidget(clear_btn)

        root.addLayout(hdr)

        # ── Sub-header: log file path ─────────────────────────────────
        import datetime
        log_dir  = os.path.join(BASE_PATH, "logs")
        log_file = os.path.join(log_dir, f"spectre_{datetime.date.today().strftime('%Y%m')}.log")
        path_lbl = QLabel(f"Log file:  {log_file}")
        path_lbl.setStyleSheet(
            f"color:{Theme.TXT_3};font-size:11px;font-family:Consolas,monospace;"
        )
        path_lbl.setWordWrap(True)
        root.addWidget(path_lbl)

        # Open log folder button
        open_btn = QPushButton("📂  Open Log Folder")
        open_btn.setFixedHeight(28)
        open_btn.setFixedWidth(160)
        open_btn.clicked.connect(lambda: self._open_log_folder(log_dir))
        root.addWidget(open_btn)

        # ── Log viewer (QTextEdit, read-only) ─────────────────────────
        log_card = QFrame()
        log_card.setStyleSheet(
            f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};"
            f"border-radius:8px;}}"
        )
        lc_lay = QVBoxLayout(log_card)
        lc_lay.setContentsMargins(0, 0, 0, 0)

        self._viewer = QTextEdit()
        self._viewer.setReadOnly(True)
        self._viewer.setStyleSheet(
            f"QTextEdit{{background:{Theme.BG};color:{Theme.TXT};"
            f"font-family:Consolas,'Courier New',monospace;font-size:11px;"
            f"border:none;padding:12px;}}"
        )
        self._viewer.setMinimumHeight(500)
        self._viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lc_lay.addWidget(self._viewer)
        root.addWidget(log_card)

        # ── Stats row ─────────────────────────────────────────────────
        self._stats_lbl = QLabel("")
        self._stats_lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
        root.addWidget(self._stats_lbl)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _open_log_folder(self, folder: str):
        from utils import open_file_in_default_app
        os.makedirs(folder, exist_ok=True)
        open_file_in_default_app(folder)

    def _toggle_autoscroll(self, checked: bool):
        self._auto_scroll = checked
        self._autoscroll_btn.setText(
            "⬇  Auto-scroll ON" if checked else "⬇  Auto-scroll OFF"
        )

    def _on_filter_changed(self, text: str):
        self._filter_text = text.lower()
        self._repopulate()

    def _on_level_changed(self, text: str):
        self._filter_level = text
        self._repopulate()

    def _clear(self):
        handler = install_memory_handler()
        handler.clear()
        self._viewer.clear()
        self._update_stats([])

    def _record_passes_filter(self, record: logging.LogRecord) -> bool:
        if self._filter_level != "ALL":
            min_level = getattr(logging, self._filter_level, 0)
            if record.levelno < min_level:
                return False
        if self._filter_text:
            formatted = (install_memory_handler().format(record) or "").lower()
            if self._filter_text not in formatted:
                return False
        return True

    def _repopulate(self):
        handler = install_memory_handler()
        records = [r for r in handler.get_records() if self._record_passes_filter(r)]
        self._viewer.clear()
        cursor = self._viewer.textCursor()
        for record in records:
            self._append_record(cursor, record)
        self._update_stats(handler.get_records())
        if self._auto_scroll:
            self._viewer.moveCursor(QTextCursor.End)

    def _append_record(self, cursor: QTextCursor, record: logging.LogRecord):
        fmt = QTextCharFormat()
        color = _level_color(record.levelname)
        fmt.setForeground(QColor(color))
        if record.levelno >= logging.ERROR:
            fmt.setFontWeight(700)
        else:
            fmt.setFontWeight(400)
        handler = install_memory_handler()
        text = handler.format(record)
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text + "\n", fmt)

    def _on_new_record(self, record: logging.LogRecord):
        """Called from the memory handler whenever a new record arrives."""
        if not self.isVisible():
            return
        if not self._record_passes_filter(record):
            return
        cursor = self._viewer.textCursor()
        self._append_record(cursor, record)
        self._update_stats(install_memory_handler().get_records())
        if self._auto_scroll:
            self._viewer.moveCursor(QTextCursor.End)

    def _update_stats(self, all_records: list):
        counts = {"ERROR": 0, "CRITICAL": 0, "WARNING": 0, "INFO": 0, "DEBUG": 0}
        for r in all_records:
            lvl = r.levelname.upper()
            if lvl in counts:
                counts[lvl] += 1
        total = len(all_records)
        errors = counts["ERROR"] + counts["CRITICAL"]
        self._stats_lbl.setText(
            f"Total: {total}  ·  "
            f"Errors: {errors}  ·  "
            f"Warnings: {counts['WARNING']}  ·  "
            f"Info: {counts['INFO']}  ·  "
            f"Debug: {counts['DEBUG']}"
        )

    def showEvent(self, e):
        super().showEvent(e)
        self._repopulate()


# Monkey-patch .also() on QLabel if not already present
def _also(self, fn):
    fn(self); return self
try:
    QLabel.also
except AttributeError:
    QLabel.also = _also

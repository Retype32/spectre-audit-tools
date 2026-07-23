"""
main_window.py — application's top-level window.

MainWindow holds the sidebar nav, the QStackedWidget of pages, the top bar
(page title + global status pill), the bottom status bar, and the shared
DetailDialog instance used for stacking row inspections.
"""
import os

from PySide6.QtCore import Qt, QEvent, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QScrollArea, QStackedWidget, QStatusBar, QToolButton,
    QVBoxLayout, QWidget
)
from PySide6.QtGui import QCursor, QPixmap

from config import APP_VERSION, BASE_PATH, VERSION_MODE

# ── Nav icon resources ────────────────────────────────────────────────────────
_ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "assets", "icons")

_ICON_MAP = {
    "Integrity Check":  "integrity_check.png",
    "Targeted Search":  "targeted_search.png",
    "Universal Search": "universal_search.png",
    "Slip Audit":       "slip_audit.png",
    "Bag Counter":      "bag_counter.png",
    "Dashboard":        "dashboard.png",
    "Risk Scoring":     "risk_scoring.png",
    "Trend Analysis":   "trend_analysis.png",
    "Export Report":    "export_report.png",
    "Data Quality":     "data_quality.png",
    "Correlation":      "correlation.png",
    "Visual Reports":   "visual_reports.png",
    "Discrepancies":    "discrepancies.png",
    "NON-VMS Reports":  "non_vms_reports.png",
    "Amount Discovery": "amount_discovery.png",
    "No.3 Account":     "no3_account.png",
}

_ICON_SIZE = 22   # px — square display size inside the nav button

import theme as _theme
from theme import Theme, build_qss
from widgets import StatusPill, DetailDialog
from pages import (
    IntegrityPage, SearchPage, UniversalSearchPage, SlipAuditPage,
    BagCounterPage, HistoryPage, CashierDbPage, NonVmsPage,
    AmountDiscoveryPage, No3Page, SettingsPage,
    DashboardPage, RiskScoringPage, TrendAnalysisPage, ExportReportPage,
    DataQualityPage, CorrelationPage, VisualReportPage, CashierPerformancePage,
    DiscrepanciesPage,
    DebugLogPage, install_memory_handler
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        install_memory_handler()   # start capturing logs for the debug viewer
        self.setWindowTitle(f"{APP_VERSION} — Audit Intelligence")
        self.resize(1480, 900)
        self.setMinimumSize(1180, 700)

        # Frameless window so we can render our own title bar that matches
        # the rest of the app's dark theme. The custom bar lives at the top
        # of the central widget and provides drag-to-move + min/max/close.
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        # Mouse tracking lets us update the cursor on hover (resize edges)
        # without requiring a button press first.
        self.setMouseTracking(True)
        # Edge-resize state. _resize_edge is one of None / "left" / "right"
        # / "top" / "bottom" / "topleft" / "topright" / "bottomleft" /
        # "bottomright" while the user is dragging an edge. _resize_start_*
        # captures the geometry at the moment the drag began so we can
        # compute deltas consistently.
        self._resize_edge = None
        self._resize_start_geom = None
        self._resize_start_pos = None
        # Thickness of the invisible hit-zone around the window edges that
        # the user can grab to resize.
        self._resize_margin = 8

        # Shared state used across pages (replaces v1.6 self.* attrs)
        self.active_df = None
        self.slip_entries = {}
        self.last_saved_audit = None
        self.nonvms_results = []
        self.nonvms_disc_results = []
        self._exact_dup_rows = []
        self._sus_rows = []
        self._shared_wallet_rows = []

        # Central widget: vertical layout — custom title bar on top, then
        # the original horizontal split (sidebar | content) below it.
        central = QWidget(); self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # Custom title bar (replaces the OS chrome we just hid)
        self.title_bar = self._build_title_bar()
        outer.addWidget(self.title_bar)

        # Body: sidebar | content
        body = QWidget()
        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        outer.addWidget(body, 1)

        # Sidebar
        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)

        # Content area
        content_wrap = QWidget()
        cwl = QVBoxLayout(content_wrap)
        cwl.setContentsMargins(0, 0, 0, 0); cwl.setSpacing(0)

        # Top bar — page title + global status
        self.top_bar = self._build_top_bar()
        cwl.addWidget(self.top_bar)

        # Stacked pages
        self.stack = QStackedWidget()
        cwl.addWidget(self.stack, 1)

        root.addWidget(content_wrap, 1)

        # Status bar at the bottom
        sb = QStatusBar(); self.setStatusBar(sb)
        self.global_status = QLabel(f"{APP_VERSION}  ·  ready")
        self.global_status.setStyleSheet(f"color:{Theme.TXT_3}; padding:0 8px;")
        sb.addWidget(self.global_status)
        sb.addPermanentWidget(QLabel(f"Base: {BASE_PATH}  "))

        # Pages
        self.pages = {}
        self._build_pages()

        # Default page
        self._activate_nav(0)

        # Install an application-level event filter so we can detect edge
        # hovers + clicks anywhere inside the window (the children grab
        # most mouse events, so MainWindow's own handlers would never see
        # them). The filter only acts on events whose top-level window is
        # this MainWindow — events for other windows pass through.
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)

    # ------------------------------------------------------------------
    def _build_sidebar(self):
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(224)

        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Logo (pinned — never scrolls) ─────────────────────────────
        logo = QLabel("◈  SPECTRE"); logo.setObjectName("sidebarLogo")
        lay.addWidget(logo)
        ver = QLabel(f"v2.0  ·  {VERSION_MODE}"); ver.setObjectName("sidebarVersion")
        lay.addWidget(ver)

        # Accent hairline under the logo block
        logo_div = QFrame(); logo_div.setFixedHeight(1)
        logo_div.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {Theme.ACCENT}, stop:0.5 {Theme.BORDER}, stop:1 {Theme.BORDER_S});"
        )
        lay.addWidget(logo_div)

        self.nav_buttons = []   # (btn, label) — only leaf nav items

        # ── Scrollable nav area ───────────────────────────────────────
        # All three collapsible groups live inside a QScrollArea so the
        # sidebar stays usable on smaller screens even when all groups
        # are fully expanded.
        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        nav_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical {"
            f"  background: transparent; width: 4px; margin: 0; }}"
            "QScrollBar::handle:vertical {"
            f"  background: {Theme.BORDER}; border-radius: 2px; min-height: 24px; margin: 1px; }}"
            "QScrollBar::handle:vertical:hover {"
            f"  background: {Theme.TXT_3}; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )

        nav_inner = QWidget()
        nav_inner.setStyleSheet("background: transparent;")
        nav_lay = QVBoxLayout(nav_inner)
        nav_lay.setContentsMargins(0, 0, 0, 0)
        nav_lay.setSpacing(0)

        # ── AUDIT group ───────────────────────────────────────────────
        self._audit_group = self._add_group(nav_lay, "AUDIT")
        self._add_nav(self._audit_group, "Integrity Check",  "▣")
        self._add_nav(self._audit_group, "Targeted Search",  "◎")
        self._add_nav(self._audit_group, "Universal Search", "⌕")
        self._add_nav(self._audit_group, "Slip Audit",       "▤")
        self._add_nav(self._audit_group, "Bag Counter",      "▥")
        self._add_nav(self._audit_group, "History",          "◷")

        # ── ANALYTICS group ───────────────────────────────────────────
        self._analytics_group = self._add_group(nav_lay, "ANALYTICS", expanded=True)
        self._add_nav(self._analytics_group, "Dashboard",        "◈")
        self._add_nav(self._analytics_group, "Risk Scoring",    "◉")
        self._add_nav(self._analytics_group, "Performance",     "◎")
        self._add_nav(self._analytics_group, "Discrepancies",   "◬")
        self._add_nav(self._analytics_group, "Trend Analysis",  "◷")
        self._add_nav(self._analytics_group, "Export Report",   "▤")
        self._add_nav(self._analytics_group, "Data Quality",    "◧")
        self._add_nav(self._analytics_group, "Correlation",     "⊕")
        self._add_nav(self._analytics_group, "Visual Reports",  "◑")

        # ── AUTOMATION group ──────────────────────────────────────────
        self._automation_group = self._add_group(nav_lay, "AUTOMATION", expanded=False)
        self._add_nav(self._automation_group, "NON-VMS Reports",  "◫")
        self._add_nav(self._automation_group, "Amount Discovery", "◉")
        self._add_nav(self._automation_group, "No.3 Account",     "₠")

        nav_lay.addStretch(1)
        nav_scroll.setWidget(nav_inner)
        lay.addWidget(nav_scroll, 1)   # takes all remaining vertical space

        # ── Pinned bottom section ─────────────────────────────────────
        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER};")
        lay.addWidget(div)

        self._db_btn = QPushButton("  ▦   Database")
        self._db_btn.setObjectName("navBtn")
        self._db_btn.setCheckable(True)
        self._db_btn.setCursor(Qt.PointingHandCursor)
        self._db_btn.setFixedHeight(36)
        self._db_btn.clicked.connect(self._open_database)
        lay.addWidget(self._db_btn)

        div2 = QFrame(); div2.setFixedHeight(1)
        div2.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div2)

        self._settings_btn = QPushButton("  ⚙   Settings")
        self._settings_btn.setObjectName("navBtn")
        self._settings_btn.setCheckable(True)
        self._settings_btn.setCursor(Qt.PointingHandCursor)
        self._settings_btn.setFixedHeight(36)
        self._settings_btn.clicked.connect(self._open_settings)
        lay.addWidget(self._settings_btn)

        self._debug_btn = QPushButton("  ▣   Debug Log")
        self._debug_btn.setObjectName("navBtn")
        self._debug_btn.setCheckable(True)
        self._debug_btn.setCursor(Qt.PointingHandCursor)
        self._debug_btn.setFixedHeight(36)
        self._debug_btn.clicked.connect(self._open_debug)
        lay.addWidget(self._debug_btn)

        return side

    def _add_group(self, parent_lay, label, expanded=True):
        """Creates a collapsible group header + container widget with slide animation."""
        # Thin separator line above each group to visually anchor the header
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{Theme.BORDER_S};")
        parent_lay.addWidget(sep)

        # Collapsible group header — minimal label style matching modern sidebars
        arrow = "▾" if expanded else "▸"
        header = QPushButton(f" {arrow}  {label}")
        header.setStyleSheet(
            f"QPushButton{{"
            f"  background:transparent;"
            f"  color:{Theme.TXT_3};"
            f"  border:none;"
            f"  text-align:left;"
            f"  padding:12px 14px 6px 16px;"
            f"  font-size:9.5px; font-weight:700; letter-spacing:2.5px;"
            f"}}"
            f"QPushButton:hover{{"
            f"  color:{Theme.TXT_2};"
            f"  background:transparent;"
            f"}}"
        )
        header.setCheckable(False)
        parent_lay.addWidget(header)

        # Container for nav items
        container = QWidget()
        container.setStyleSheet("QWidget{background:transparent;}")
        container_lay = QVBoxLayout(container)
        container_lay.setContentsMargins(0, 0, 0, 0)
        container_lay.setSpacing(0)
        parent_lay.addWidget(container)

        if not expanded:
            container.setMaximumHeight(0)
            container.setVisible(False)

        anim_state = {"is_open": expanded, "anim": None}

        def _content_height():
            h = container.sizeHint().height()
            if h <= 0:
                lay = container.layout()
                h = sum(
                    lay.itemAt(i).widget().sizeHint().height()
                    for i in range(lay.count())
                    if lay.itemAt(i) and lay.itemAt(i).widget()
                )
            return max(h, 32)

        def _nudge():
            container.updateGeometry()
            p = container.parentWidget()
            while p:
                p.updateGeometry()
                p = p.parentWidget()

        def _toggle():
            if anim_state["anim"] is not None:
                anim_state["anim"].stop()

            going_open = not anim_state["is_open"]
            anim_state["is_open"] = going_open
            header.setText(f"  {'▾' if going_open else '▸'}  {label}")

            anim = QPropertyAnimation(container, b"maximumHeight")
            anim.setDuration(220)
            anim.setEasingCurve(QEasingCurve.OutCubic)

            if going_open:
                container.setVisible(True)
                target = _content_height()
                anim.setStartValue(0)
                anim.setEndValue(target)

                def _done_open():
                    container.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
                    _nudge()
                anim.finished.connect(_done_open)
            else:
                anim.setStartValue(container.height())
                anim.setEndValue(0)

                def _done_close():
                    container.setVisible(False)
                    _nudge()
                anim.finished.connect(_done_close)

            anim_state["anim"] = anim
            anim.start()
            _nudge()

        header.clicked.connect(_toggle)
        return container_lay

    def _add_nav(self, parent_lay, label, icon):
        btn = QPushButton()
        btn.setObjectName("navBtn")
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(36)

        inner = QHBoxLayout(btn)
        inner.setContentsMargins(10, 0, 12, 0)
        inner.setSpacing(8)

        icon_lbl = QLabel()
        icon_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        icon_lbl.setAlignment(Qt.AlignCenter)

        # Try PNG icon first; fall back to text glyph
        png_file = _ICON_MAP.get(label, "")
        png_path = os.path.join(_ICONS_DIR, png_file) if png_file else ""
        if png_path and os.path.isfile(png_path):
            pm = QPixmap(png_path).scaled(
                _ICON_SIZE, _ICON_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            icon_lbl.setPixmap(pm)
            icon_lbl.setFixedSize(_ICON_SIZE + 4, _ICON_SIZE + 4)
            eff = QGraphicsOpacityEffect(icon_lbl)
            eff.setOpacity(0.45)
            icon_lbl.setGraphicsEffect(eff)
            btn._icon_effect = eff
        else:
            icon_lbl.setText(icon)
            icon_lbl.setFixedSize(_ICON_SIZE + 4, _ICON_SIZE + 4)
            btn._icon_effect = None

        text_lbl = QLabel(label)
        text_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        inner.addWidget(icon_lbl)
        inner.addWidget(text_lbl, 1)

        idx = len(self.nav_buttons)
        btn.clicked.connect(lambda _checked=False, i=idx: self._activate_nav(i))
        self.nav_buttons.append((btn, label))
        btn._icon_lbl = icon_lbl
        btn._text_lbl = text_lbl
        parent_lay.addWidget(btn)
        self._apply_nav_style(btn, False)

    def _apply_nav_style(self, btn, active):
        color  = Theme.ACCENT_H if active else Theme.TXT_3
        weight = "font-weight:600;" if active else "font-weight:400;"
        lbl_style = (
            f"color:{color};background:transparent;{weight}"
            f"font-size:13px;letter-spacing:0.1px;"
        )

        if hasattr(btn, '_icon_lbl'):
            eff = getattr(btn, '_icon_effect', None)
            if eff is not None:
                eff.setOpacity(1.0 if active else 0.38)
            else:
                btn._icon_lbl.setStyleSheet(lbl_style)

        if hasattr(btn, '_text_lbl'):
            btn._text_lbl.setStyleSheet(lbl_style)

    def _set_page_title(self, text):
        self.page_title.setText(text)
        if not hasattr(self, '_title_fx'):
            self._title_fx = QGraphicsOpacityEffect(self.page_title)
            self.page_title.setGraphicsEffect(self._title_fx)
        self._title_fx.setOpacity(0.0)
        if getattr(self, '_title_anim', None):
            self._title_anim.stop()
        self._title_anim = QPropertyAnimation(self._title_fx, b"opacity")
        self._title_anim.setDuration(220)
        self._title_anim.setStartValue(0.0)
        self._title_anim.setEndValue(1.0)
        self._title_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._title_anim.start()

    def _activate_nav(self, idx):
        for i, (btn, _) in enumerate(self.nav_buttons):
            active = (i == idx)
            btn.setChecked(active)
            self._apply_nav_style(btn, active)
        if hasattr(self, "_settings_btn"):
            self._settings_btn.setChecked(False)
        if hasattr(self, "_db_btn"):
            self._db_btn.setChecked(False)
        if hasattr(self, "_debug_btn"):
            self._debug_btn.setChecked(False)
        self.stack.setCurrentIndex(idx)
        self._set_page_title(self.nav_buttons[idx][1])

    def _open_database(self):
        for btn, _ in self.nav_buttons:
            btn.setChecked(False)
        if hasattr(self, "_settings_btn"):
            self._settings_btn.setChecked(False)
        if hasattr(self, "_debug_btn"):
            self._debug_btn.setChecked(False)
        self._db_btn.setChecked(True)
        self.stack.setCurrentIndex(self._db_page_idx)
        self._set_page_title("Database")

    def _open_settings(self):
        for btn, _ in self.nav_buttons:
            btn.setChecked(False)
        if hasattr(self, "_db_btn"):
            self._db_btn.setChecked(False)
        self._settings_btn.setChecked(True)
        self.stack.setCurrentIndex(self._settings_page_idx)
        self._set_page_title("Settings")

    def _open_debug(self):
        for btn, _ in self.nav_buttons:
            btn.setChecked(False)
        if hasattr(self, "_db_btn"):
            self._db_btn.setChecked(False)
        if hasattr(self, "_settings_btn"):
            self._settings_btn.setChecked(False)
        self._debug_btn.setChecked(True)
        self.stack.setCurrentIndex(self._debug_page_idx)
        self._set_page_title("Debug Log")

    def _build_top_bar(self):
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setStyleSheet(
            f"QFrame#topBar {{ background: {Theme.BG}; "
            f"border-bottom: 1px solid {Theme.BORDER_S}; }}"
        )
        bar.setFixedHeight(58)
        l = QHBoxLayout(bar); l.setContentsMargins(28, 0, 20, 0); l.setSpacing(10)

        self.page_title = QLabel("Integrity Check")
        self.page_title.setStyleSheet(
            f"color:{Theme.TXT}; font-size:17px; font-weight:700; letter-spacing:-0.2px;"
        )
        l.addWidget(self.page_title)
        l.addStretch()

        self.top_status = StatusPill("Ready", "muted")
        l.addWidget(self.top_status)
        return bar



    # ------------------------------------------------------------------
    # Custom title bar — replaces the OS window chrome (which we hide via
    # FramelessWindowHint). Contains the app title and our own minimize /
    # maximize-restore / close buttons. The bar is draggable to move the
    # window, and double-clicking it toggles maximize.
    # ------------------------------------------------------------------
    def _build_title_bar(self):
        bar = TitleBar(self)
        bar.setFixedHeight(36)
        bar.setStyleSheet(
            f"TitleBar {{ background: {Theme.SURFACE}; "
            f"border-bottom: 1px solid {Theme.BORDER_S}; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 0, 4, 0); lay.setSpacing(6)

        # Left: app title
        title = QLabel("SPECTRE  ·  AUDIT INTELLIGENCE")
        title.setStyleSheet(
            f"color:{Theme.TXT_3}; font-size:9px; font-weight:700; letter-spacing:2.5px;"
        )
        lay.addWidget(title)
        lay.addStretch(1)

        # Right: three window-control buttons — traffic-light hover colours
        _base = (
            f"QToolButton {{ background:transparent; border:none; border-radius:0; "
            f"min-width:46px; min-height:36px; font-size:12px; }}"
        )
        min_style = (
            _base
            + f"QToolButton {{ color:{Theme.TXT_3}; }}"
            + f"QToolButton:hover {{ background:rgba(240,160,48,0.15); color:#f0a030; }}"
        )
        max_style = (
            _base
            + f"QToolButton {{ color:{Theme.TXT_3}; }}"
            + f"QToolButton:hover {{ background:rgba(54,201,138,0.15); color:#36c98a; }}"
        )
        close_style = (
            _base
            + f"QToolButton {{ color:{Theme.TXT_3}; }}"
            + f"QToolButton:hover {{ background:rgba(239,79,68,0.18); color:#ef4f44; }}"
        )

        self._btn_min = QToolButton(); self._btn_min.setText("─")
        self._btn_min.setToolTip("Minimize")
        self._btn_min.setCursor(Qt.PointingHandCursor)
        self._btn_min.setStyleSheet(min_style)
        self._btn_min.clicked.connect(self.showMinimized)

        self._btn_max = QToolButton(); self._btn_max.setText("☐")
        self._btn_max.setToolTip("Maximize")
        self._btn_max.setCursor(Qt.PointingHandCursor)
        self._btn_max.setStyleSheet(max_style)
        self._btn_max.clicked.connect(self._toggle_max_restore)

        self._btn_close = QToolButton(); self._btn_close.setText("✕")
        self._btn_close.setToolTip("Close")
        self._btn_close.setCursor(Qt.PointingHandCursor)
        self._btn_close.setStyleSheet(close_style)
        self._btn_close.clicked.connect(self.close)

        lay.addWidget(self._btn_min)
        lay.addWidget(self._btn_max)
        lay.addWidget(self._btn_close)
        return bar

    def _toggle_max_restore(self):
        if self.isMaximized():
            self.showNormal()
            self._btn_max.setText("☐")
            self._btn_max.setToolTip("Maximize")
        else:
            self.showMaximized()
            self._btn_max.setText("❐")
            self._btn_max.setToolTip("Restore")

    # ------------------------------------------------------------------
    # Edge resize for the frameless window. We listen to mouse events on
    # ANY descendant widget via an application-level event filter, because
    # the children (sidebar, top bar, tables, etc.) consume mouse events
    # before MainWindow ever sees them. The hit zone is `_resize_margin`
    # pixels wide along every edge, measured in global screen coords.
    # ------------------------------------------------------------------
    _RESIZE_CURSORS = {
        "left":        Qt.SizeHorCursor,
        "right":       Qt.SizeHorCursor,
        "top":         Qt.SizeVerCursor,
        "bottom":      Qt.SizeVerCursor,
        "topleft":     Qt.SizeFDiagCursor,
        "bottomright": Qt.SizeFDiagCursor,
        "topright":    Qt.SizeBDiagCursor,
        "bottomleft":  Qt.SizeBDiagCursor,
    }

    def _edge_at(self, global_pos):
        """Return the edge name the cursor is over, or None if it's interior.

        Measured against the window's frame geometry on screen. Returns one
        of: left, right, top, bottom, topleft, topright, bottomleft,
        bottomright. Maximized windows are never resizable from edges.
        """
        if self.isMaximized() or self.isFullScreen():
            return None
        g = self.frameGeometry()
        m = self._resize_margin
        x, y = global_pos.x(), global_pos.y()
        on_left   = g.left()   <= x <= g.left()   + m
        on_right  = g.right()  - m <= x <= g.right()
        on_top    = g.top()    <= y <= g.top()    + m
        on_bottom = g.bottom() - m <= y <= g.bottom()
        # Cursor must be within the window vertically/horizontally to count.
        in_x = g.left() <= x <= g.right()
        in_y = g.top()  <= y <= g.bottom()
        if not (in_x and in_y):
            return None
        if on_top and on_left:     return "topleft"
        if on_top and on_right:    return "topright"
        if on_bottom and on_left:  return "bottomleft"
        if on_bottom and on_right: return "bottomright"
        if on_left:                return "left"
        if on_right:               return "right"
        if on_top:                 return "top"
        if on_bottom:              return "bottom"
        return None

    def eventFilter(self, obj, ev):
        """Catch mouse events anywhere in the window for edge-resize.

        Only acts on events whose top-level window is this MainWindow, so
        we don't interfere with dialogs (DetailDialog, FilteredRowsDialog)
        which are separate top-level widgets.
        """
        et = ev.type()
        # Only mouse-related events are interesting.
        if et not in (QEvent.MouseMove, QEvent.MouseButtonPress,
                      QEvent.MouseButtonRelease, QEvent.HoverMove):
            return super().eventFilter(obj, ev)

        # Resolve the top-level window of the event target. If the event
        # is for a non-widget QObject (timer, action, etc.) or for a
        # different top-level (e.g. a dialog), ignore it entirely.
        if not isinstance(obj, QWidget):
            return super().eventFilter(obj, ev)
        top = obj.window()
        if top is not self:
            return super().eventFilter(obj, ev)

        # Use global position for hit-testing. globalPosition() returns a
        # QPointF; toPoint() rounds it to a QPoint.
        global_pos = (
            ev.globalPosition().toPoint() if hasattr(ev, "globalPosition")
            else QCursor.pos()
        )

        if et in (QEvent.MouseMove, QEvent.HoverMove):
            if self._resize_edge is not None and (
                ev.buttons() & Qt.LeftButton if hasattr(ev, "buttons") else False
            ):
                self._perform_resize(global_pos)
                return True
            # Not currently resizing — update the cursor based on hover.
            self._update_resize_cursor(global_pos)
            # Fall through so children still see the move (text selection,
            # hover effects, etc. keep working).
            return super().eventFilter(obj, ev)

        if et == QEvent.MouseButtonPress:
            if (hasattr(ev, "button") and ev.button() == Qt.LeftButton):
                edge = self._edge_at(global_pos)
                if edge is not None and not self._press_over_titlebar_button(global_pos):
                    # Start a resize drag. Capture the starting geometry so
                    # we can compute deltas in _perform_resize. Grab the
                    # mouse so we keep getting move/release events even if
                    # the cursor leaves the window during the drag.
                    self._resize_edge = edge
                    self._resize_start_geom = self.geometry()
                    self._resize_start_pos = global_pos
                    self.grabMouse()
                    return True  # Don't let children see this press.
            return super().eventFilter(obj, ev)

        if et == QEvent.MouseButtonRelease:
            if self._resize_edge is not None:
                self._resize_edge = None
                self._resize_start_geom = None
                self._resize_start_pos = None
                self.releaseMouse()
                # Restore the cursor — _update_resize_cursor will pick the
                # right one based on the current hover position.
                self._update_resize_cursor(global_pos)
                return True
            return super().eventFilter(obj, ev)

        return super().eventFilter(obj, ev)

    def _update_resize_cursor(self, global_pos):
        """Show the matching resize cursor when hovering an edge, else reset."""
        edge = self._edge_at(global_pos)
        # Don't trample the title-bar buttons' own cursors with a resize cursor.
        if edge is None or self._press_over_titlebar_button(global_pos):
            # Only unset if we previously set it for an edge; don't trample
            # cursors that children deliberately set (text fields, etc.).
            if self.cursor().shape() in self._RESIZE_CURSORS.values():
                self.unsetCursor()
            return
        self.setCursor(self._RESIZE_CURSORS[edge])

    def _press_over_titlebar_button(self, global_pos):
        """True if the given global point is inside any title bar control
        button (minimize, maximize, close). Used to keep those buttons
        clickable at the very top of the window, where they overlap the
        top resize-edge hit zone.
        """
        for btn in (
            getattr(self, "_btn_min", None),
            getattr(self, "_btn_max", None),
            getattr(self, "_btn_close", None),
        ):
            if btn is None:
                continue
            r = btn.rect()
            # mapToGlobal returns the top-left corner; build the global rect.
            tl = btn.mapToGlobal(r.topLeft())
            br = btn.mapToGlobal(r.bottomRight())
            if tl.x() <= global_pos.x() <= br.x() and tl.y() <= global_pos.y() <= br.y():
                return True
        return False

    def _perform_resize(self, global_pos):
        """Recompute the window geometry while dragging an edge."""
        if self._resize_start_geom is None or self._resize_start_pos is None:
            return
        g0 = self._resize_start_geom
        dx = global_pos.x() - self._resize_start_pos.x()
        dy = global_pos.y() - self._resize_start_pos.y()
        min_w = self.minimumWidth()
        min_h = self.minimumHeight()

        # Default to starting geometry — only the edges being dragged change.
        left, top, right, bottom = g0.left(), g0.top(), g0.right(), g0.bottom()
        edge = self._resize_edge

        if "left" in edge:
            new_left = g0.left() + dx
            # Don't let the left edge cross the right edge minus the min width.
            new_left = min(new_left, g0.right() - min_w + 1)
            left = new_left
        if "right" in edge:
            new_right = g0.right() + dx
            new_right = max(new_right, g0.left() + min_w - 1)
            right = new_right
        if "top" in edge:
            new_top = g0.top() + dy
            new_top = min(new_top, g0.bottom() - min_h + 1)
            top = new_top
        if "bottom" in edge:
            new_bottom = g0.bottom() + dy
            new_bottom = max(new_bottom, g0.top() + min_h - 1)
            bottom = new_bottom

        # Apply atomically as a single setGeometry to avoid flicker.
        self.setGeometry(left, top, right - left + 1, bottom - top + 1)

    def _build_pages(self):
        # Order MUST match nav_buttons order (leaf items only, in sidebar order)
        # AUDIT group
        self.pages['integrity'] = IntegrityPage(self);        self.stack.addWidget(self.pages['integrity'])
        self.pages['search']    = SearchPage(self);           self.stack.addWidget(self.pages['search'])
        self.pages['universal'] = UniversalSearchPage(self);  self.stack.addWidget(self.pages['universal'])
        self.pages['slip']      = SlipAuditPage(self);        self.stack.addWidget(self.pages['slip'])
        self.pages['bags']      = BagCounterPage(self);       self.stack.addWidget(self.pages['bags'])
        self.pages['history']   = HistoryPage(self);          self.stack.addWidget(self.pages['history'])
        # ANALYTICS group
        self.pages['dashboard'] = DashboardPage(self);           self.stack.addWidget(self.pages['dashboard'])
        self.pages['risk']      = RiskScoringPage(self);         self.stack.addWidget(self.pages['risk'])
        self.pages['perf']      = CashierPerformancePage(self);  self.stack.addWidget(self.pages['perf'])
        self.pages['discrep']   = DiscrepanciesPage(self);       self.stack.addWidget(self.pages['discrep'])
        self.pages['trend']     = TrendAnalysisPage(self);       self.stack.addWidget(self.pages['trend'])
        self.pages['export']    = ExportReportPage(self);     self.stack.addWidget(self.pages['export'])
        self.pages['quality']   = DataQualityPage(self);      self.stack.addWidget(self.pages['quality'])
        self.pages['corr']      = CorrelationPage(self);      self.stack.addWidget(self.pages['corr'])
        self.pages['visual']    = VisualReportPage(self);     self.stack.addWidget(self.pages['visual'])
        # AUTOMATION group
        self.pages['nonvms']    = NonVmsPage(self);           self.stack.addWidget(self.pages['nonvms'])
        self.pages['discovery'] = AmountDiscoveryPage(self);  self.stack.addWidget(self.pages['discovery'])
        self.pages['no3']       = No3Page(self);              self.stack.addWidget(self.pages['no3'])
        # Standalone pages (not in nav_buttons list)
        self.pages['db']        = CashierDbPage(self);        self.stack.addWidget(self.pages['db'])
        self.pages['settings']  = SettingsPage(self);         self.stack.addWidget(self.pages['settings'])
        self.pages['debug']     = DebugLogPage(self);          self.stack.addWidget(self.pages['debug'])
        self._db_page_idx       = self.stack.indexOf(self.pages['db'])
        self._settings_page_idx = self.stack.indexOf(self.pages['settings'])
        self._debug_page_idx    = self.stack.indexOf(self.pages['debug'])

    # ------------------------------------------------------------------
    # Shared multi-row detail dialog. Pages call this through
    # DetailDialog.show_row(self.app, title, row_data) so every click
    # stacks into the same window until the user presses Close.
    # ------------------------------------------------------------------
    def get_detail_dialog(self):
        dlg = getattr(self, "_detail_dialog", None)
        # Recreate if it was destroyed (Qt may delete a closed top-level
        # dialog if the user X-ed it; we can't rely on the same instance).
        if dlg is None:
            dlg = DetailDialog(self)
            self._detail_dialog = dlg
        return dlg


# =============================================================================
# CUSTOM TITLE BAR
# =============================================================================
class TitleBar(QFrame):
    """The bar at the very top of MainWindow.

    Behaviors:
      • mouse-press + mouse-move on empty bar space drags the window.
      • If the user starts a drag while maximized, the window restores to
        its previous normal size and follows the cursor — standard OS
        title-bar behavior. We re-center the restored window under the
        cursor proportionally to where they grabbed it.
      • double-click on empty bar space toggles maximize / restore.
    """
    def __init__(self, window):
        super().__init__(window)
        # Keep an explicit reference so we don't depend on parent() type-casting.
        self._win = window
        # _drag_offset is the vector from the window's top-left to the
        # cursor at press time; held for the duration of the drag.
        self._drag_offset = None
        # When a drag starts while maximized we need to defer the restore
        # to the first mouseMove (Qt can't reliably resize mid-press),
        # AND we need to remember how far along the title bar the press
        # was so the restored window appears under the cursor naturally.
        self._press_was_maximized = False
        self._press_global_pos = None

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            super().mousePressEvent(ev)
            return

        global_pos = ev.globalPosition().toPoint()

        if self._win.isMaximized():
            # Defer everything to the first mouseMove so a click that
            # doesn't turn into a drag (just a tap on the bar) doesn't
            # un-maximize the window.
            self._press_was_maximized = True
            self._press_global_pos = global_pos
            self._drag_offset = None
            ev.accept()
            return

        # Normal (non-maximized) press: capture the offset and we're set.
        self._drag_offset = global_pos - self._win.frameGeometry().topLeft()
        ev.accept()

    def mouseMoveEvent(self, ev):
        if not (ev.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(ev)
            return

        global_pos = ev.globalPosition().toPoint()

        # First-move after a press while maximized: restore now, then
        # reposition the restored window so the cursor stays over the
        # title bar at the same proportional X as before.
        if self._press_was_maximized and self._press_global_pos is not None:
            # Require a tiny minimum movement so a slightly-jittery click
            # doesn't trigger restore.
            if (global_pos - self._press_global_pos).manhattanLength() < 4:
                ev.accept()
                return
            self._restore_under_cursor(global_pos)
            self._press_was_maximized = False
            self._press_global_pos = None
            ev.accept()
            return

        if self._drag_offset is not None:
            self._win.move(global_pos - self._drag_offset)
            ev.accept()
            return

        super().mouseMoveEvent(ev)

    def _restore_under_cursor(self, global_pos):
        """Un-maximize the window and place it so the title bar stays at the
        cursor's current Y, with the cursor at roughly the same proportional
        X within the bar as before.
        """
        # The press position within the (maximized) bar in pixels.
        press_in_bar_x = global_pos.x() - self._win.frameGeometry().left()
        bar_w_max = self._win.width()
        ratio = press_in_bar_x / bar_w_max if bar_w_max > 0 else 0.5

        # Restore. Updates the max button label/tooltip too.
        self._win._toggle_max_restore()

        # After restoring, the window has its normal size. Move it so the
        # cursor lands at the same proportional X on the title bar, with Y
        # at the same offset within the title bar as the press.
        normal_w = self._win.width()
        new_left = global_pos.x() - int(round(normal_w * ratio))
        # Place the title bar so the cursor is on it, roughly mid-height.
        title_h = self._win.title_bar.height() if hasattr(self._win, "title_bar") else 32
        new_top = global_pos.y() - title_h // 2
        self._win.move(new_left, new_top)

        # Recompute the drag offset against the restored window.
        self._drag_offset = global_pos - self._win.frameGeometry().topLeft()

    def mouseReleaseEvent(self, ev):
        self._drag_offset = None
        # If the press happened while maximized but no drag ever started,
        # treat it as a no-op release (don't restore).
        self._press_was_maximized = False
        self._press_global_pos = None
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._win._toggle_max_restore()
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)

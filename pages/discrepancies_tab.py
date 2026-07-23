"""
pages/discrepancies_tab.py — Discrepancies tab.

Displays a volume histogram (bucketed by absolute discrepancy amount) and a
per-cashier net-discrepancy table, both filterable by date range and type
(All / Discrepancies / Blind Counts).  Launches the discrepancy report dialog.
"""
import datetime
import logging
import os

import pandas as pd

from PySide6.QtCore import Qt, QRectF, QTimer, QDate
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QScrollArea, QSizePolicy, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog,
    QCheckBox, QFileDialog, QButtonGroup, QAbstractItemView,
    QDateEdit,
)

from config import ALL_DISC_DB, AMOUNT, COL_DISC, OPERATOR, CUSTOMER_ID, CUSTOMER_LOC, EXPECTED_TOTAL
from theme import Theme

# ── Amount buckets for the histogram X-axis ──────────────────────────────────
BUCKETS = [
    (0,     10,     "0–10"),
    (10,    20,     "10–20"),
    (20,    50,     "20–50"),
    (50,    100,    "50–100"),
    (100,   500,    "100–500"),
    (500,   1_000,  "500–1k"),
    (1_000, 5_000,  "1k–5k"),
    (5_000, 10_000, "5k–10k"),
    (10_000,20_000, "10k–20k"),
    (20_000,None,   "20k+"),
]

CHART_GREEN  = "#3ecf8e"   # overage bars
CHART_RED    = "#e05c5c"   # shortage bars
CHART_BLUE   = "#4d9fff"   # mixed / blind count bars


def _section_label(text):
    l = QLabel(text)
    l.setStyleSheet(
        f"color:{Theme.TXT_DIM};font-size:9.5px;font-weight:700;letter-spacing:2px;"
    )
    return l


def _card(title=""):
    f = QFrame()
    f.setStyleSheet(
        f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
    )
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 14, 18, 16)
    lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:600;letter-spacing:0.2px;")
        lay.addWidget(t)
        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div)
    return f, lay


def _toggle_btn(label):
    b = QPushButton(label)
    b.setCheckable(True)
    b.setFixedHeight(26)
    b.setMinimumWidth(90)
    return b


def _apply_toggle_style(btn, active):
    btn.setStyleSheet(
        f"QPushButton{{background:{Theme.ACCENT if active else Theme.ELEVATED};"
        f"color:{'white' if active else Theme.TXT_3};"
        f"border:1px solid {Theme.ACCENT if active else Theme.BORDER};"
        f"border-radius:4px;font-size:10px;font-weight:600;padding:0 8px;}}"
        f"QPushButton:hover{{color:{'white' if active else Theme.TXT_2};}}"
    )


# ── Histogram widget ──────────────────────────────────────────────────────────
class DiscHistogram(QWidget):
    """
    Stacked bar histogram.  Each bucket may have overage (pos) and shortage
    (neg) counts stacked, or a single colour for blind counts.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._buckets = []  # list of (label, pos_count, neg_count, blind_count)
        self._t = 1.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, buckets):
        self._buckets = buckets
        self._t = 0.0
        self._timer.start()
        self.update()

    def _tick(self):
        self._t = min(1.0, self._t + 0.07)
        self.update()
        if self._t >= 1.0:
            self._timer.stop()

    def paintEvent(self, e):
        if not self._buckets:
            p = QPainter(self)
            p.setPen(QColor(Theme.TXT_3))
            p.drawText(self.rect(), Qt.AlignCenter, "No discrepancy data for the selected range")
            p.end()
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 10, 10, 16, 44
        chart_w = W - pad_l - pad_r
        chart_h = H - pad_t - pad_b
        ease = self._t * self._t * (3 - 2 * self._t)

        n = len(self._buckets)
        max_total = max((pc + nc + bc) for _, pc, nc, bc in self._buckets) or 1
        bar_w = max(6, int(chart_w / n * 0.65))
        gap   = max(2, int(chart_w / n * 0.35))

        font_lbl = QFont(); font_lbl.setPointSize(7)
        font_val = QFont(); font_val.setPointSize(7); font_val.setBold(True)

        for i, (label, pos_c, neg_c, blind_c) in enumerate(self._buckets):
            x = pad_l + i * (bar_w + gap)
            total = pos_c + neg_c + blind_c
            if total == 0:
                continue

            # draw stacked: blind (blue) bottom, shortage (red) middle, overage (green) top
            drawn_h = 0
            for count, color_hex in [(blind_c, CHART_BLUE), (neg_c, CHART_RED), (pos_c, CHART_GREEN)]:
                if count == 0:
                    continue
                seg_h = int(chart_h * count / max_total * ease)
                seg_y = pad_t + chart_h - drawn_h - seg_h
                color = QColor(color_hex); color.setAlpha(200)
                p.setBrush(QBrush(color)); p.setPen(Qt.NoPen)
                path = QPainterPath()
                path.addRoundedRect(QRectF(x, seg_y, bar_w, max(1, seg_h)), 2, 2)
                p.drawPath(path)
                drawn_h += seg_h

            # label below
            p.setPen(QPen(QColor(Theme.TXT_3)))
            p.setFont(font_lbl)
            p.drawText(x - 4, H - pad_b + 4, bar_w + 8, pad_b - 2,
                       Qt.AlignHCenter | Qt.AlignTop, label)

            # count on top
            if ease >= 0.85:
                p.setPen(QPen(QColor(Theme.TXT_2)))
                p.setFont(font_val)
                p.drawText(x - 4, pad_t + chart_h - drawn_h - 18, bar_w + 8, 16,
                           Qt.AlignHCenter | Qt.AlignBottom, str(total))

        # legend
        lx = W - pad_r - 160
        ly = pad_t
        for color_hex, lbl in [(CHART_GREEN, "Overage"), (CHART_RED, "Shortage"), (CHART_BLUE, "Blind Count")]:
            p.setBrush(QBrush(QColor(color_hex))); p.setPen(Qt.NoPen)
            p.drawRoundedRect(lx, ly, 10, 10, 2, 2)
            p.setPen(QPen(QColor(Theme.TXT_3)))
            p.setFont(font_lbl)
            p.drawText(lx + 14, ly - 1, 100, 12, Qt.AlignLeft | Qt.AlignVCenter, lbl)
            lx += 56

        p.end()


# ── Custom date range picker ──────────────────────────────────────────────────
class _DateRangeDialog(QDialog):
    def __init__(self, start=None, end=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Date Range")
        self.setMinimumWidth(340)
        self.setStyleSheet(
            f"QDialog{{background:{Theme.BG};border:1px solid {Theme.BORDER};}}"
        )
        today = QDate.currentDate()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(14)

        title = QLabel("Select Date Range")
        title.setStyleSheet(f"color:{Theme.TXT};font-size:14px;font-weight:700;")
        lay.addWidget(title)

        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div)

        def _qdate(py_date):
            if py_date:
                return QDate(py_date.year, py_date.month, py_date.day)
            return None

        row_from = QHBoxLayout(); row_from.setSpacing(8)
        lbl_from = QLabel("From:")
        lbl_from.setStyleSheet(f"color:{Theme.TXT_2};font-size:11px;"); lbl_from.setFixedWidth(36)
        self._from = QDateEdit()
        self._from.setCalendarPopup(True)
        self._from.setDisplayFormat("dd/MM/yyyy")
        self._from.setDate(_qdate(start) or today.addMonths(-1))
        self._from.setStyleSheet(
            f"QDateEdit{{background:{Theme.ELEVATED};color:{Theme.TXT};border:1px solid {Theme.BORDER};"
            f"border-radius:4px;padding:4px 8px;font-size:11px;}}"
        )
        row_from.addWidget(lbl_from); row_from.addWidget(self._from); row_from.addStretch()
        lay.addLayout(row_from)

        row_to = QHBoxLayout(); row_to.setSpacing(8)
        lbl_to = QLabel("To:")
        lbl_to.setStyleSheet(f"color:{Theme.TXT_2};font-size:11px;"); lbl_to.setFixedWidth(36)
        self._to = QDateEdit()
        self._to.setCalendarPopup(True)
        self._to.setDisplayFormat("dd/MM/yyyy")
        self._to.setDate(_qdate(end) or today)
        self._to.setStyleSheet(
            f"QDateEdit{{background:{Theme.ELEVATED};color:{Theme.TXT};border:1px solid {Theme.BORDER};"
            f"border-radius:4px;padding:4px 8px;font-size:11px;}}"
        )
        row_to.addWidget(lbl_to); row_to.addWidget(self._to); row_to.addStretch()
        lay.addLayout(row_to)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        cancel = QPushButton("Cancel"); cancel.setFixedHeight(34); cancel.clicked.connect(self.reject)
        ok = QPushButton("Apply"); ok.setObjectName("primary")
        ok.setFixedHeight(34); ok.setMinimumWidth(90); ok.clicked.connect(self.accept)
        btn_row.addStretch(); btn_row.addWidget(cancel); btn_row.addWidget(ok)
        lay.addLayout(btn_row)

    @property
    def start_date(self) -> datetime.date:
        return self._from.date().toPython()

    @property
    def end_date(self) -> datetime.date:
        return self._to.date().toPython()


# ── Main page ─────────────────────────────────────────────────────────────────
class DiscrepanciesPage(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._build()

    # ── Date ranges ──────────────────────────────────────────────────────────
    DATE_RANGES = ["This Report", "Today", "This Week", "This Month", "This Year", "All Time", "Custom Range"]
    TYPE_FILTERS = ["All", "Discrepancies Only", "Blind Counts Only"]

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        root = QVBoxLayout(inner)
        root.setContentsMargins(24, 20, 24, 24); root.setSpacing(20)
        root.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # ── Volume histogram card ─────────────────────────────────────
        vol_card, vol_lay = _card()
        tr = QHBoxLayout(); tr.setSpacing(8)

        vol_title = QLabel("Discrepancy Volume  —  Amount Distribution")
        vol_title.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:600;")
        tr.addWidget(vol_title); tr.addStretch()

        # Date toggle group (histogram)
        self._hist_date_btns = {}
        self._hist_date_group = QButtonGroup(self)
        self._hist_date_group.setExclusive(True)
        for rng in self.DATE_RANGES:
            b = _toggle_btn(rng)
            self._hist_date_btns[rng] = b
            self._hist_date_group.addButton(b)
            tr.addWidget(b)
            b.clicked.connect(lambda _=False, r=rng: self._on_hist_date(r))

        vol_div = QFrame(); vol_div.setFixedHeight(1)
        vol_div.setStyleSheet(f"background:{Theme.BORDER_S};")
        vol_lay.addLayout(tr)
        vol_lay.addWidget(vol_div)

        # Type filter row (histogram)
        type_row = QHBoxLayout(); type_row.setSpacing(6)
        type_row.addWidget(QLabel("Show:"))
        self._hist_type_btns = {}
        self._hist_type_group = QButtonGroup(self)
        self._hist_type_group.setExclusive(True)
        for tf in self.TYPE_FILTERS:
            b = _toggle_btn(tf)
            self._hist_type_btns[tf] = b
            self._hist_type_group.addButton(b)
            type_row.addWidget(b)
            b.clicked.connect(lambda _=False, t=tf: self._on_hist_type(t))
        type_row.addStretch()
        vol_lay.addLayout(type_row)

        self._histogram = DiscHistogram()
        vol_lay.addWidget(self._histogram)
        root.addWidget(vol_card)

        # ── Cashier summary card ──────────────────────────────────────
        cash_card, cash_lay = _card()
        tr2 = QHBoxLayout(); tr2.setSpacing(8)

        cash_title = QLabel("Cashier Discrepancy Totals")
        cash_title.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:600;")
        tr2.addWidget(cash_title); tr2.addStretch()

        # Date toggle group (cashier)
        self._cash_date_btns = {}
        self._cash_date_group = QButtonGroup(self)
        self._cash_date_group.setExclusive(True)
        for rng in self.DATE_RANGES:
            b = _toggle_btn(rng)
            self._cash_date_btns[rng] = b
            self._cash_date_group.addButton(b)
            tr2.addWidget(b)
            b.clicked.connect(lambda _=False, r=rng: self._on_cash_date(r))

        cash_div = QFrame(); cash_div.setFixedHeight(1)
        cash_div.setStyleSheet(f"background:{Theme.BORDER_S};")
        cash_lay.addLayout(tr2)
        cash_lay.addWidget(cash_div)

        # Filter row (cashier)
        filt_row = QHBoxLayout(); filt_row.setSpacing(10)
        filt_row.addWidget(QLabel("Blind Counts:"))
        self._cash_type_btns = {}
        self._cash_type_group = QButtonGroup(self)
        self._cash_type_group.setExclusive(True)
        for tf in self.TYPE_FILTERS:
            b = _toggle_btn(tf)
            self._cash_type_btns[tf] = b
            self._cash_type_group.addButton(b)
            filt_row.addWidget(b)
            b.clicked.connect(lambda _=False, t=tf: self._on_cash_type(t))

        filt_row.addSpacing(16)
        filt_row.addWidget(QLabel("Cashier:"))
        self._cash_combo = QComboBox()
        self._cash_combo.setMinimumWidth(160)
        self._cash_combo.addItem("All Cashiers")
        self._cash_combo.currentIndexChanged.connect(self._refresh_cashier_table)
        filt_row.addWidget(self._cash_combo)
        filt_row.addStretch()
        cash_lay.addLayout(filt_row)

        # Cashier table
        self._cash_table = QTableWidget()
        self._cash_table.setColumnCount(5)
        self._cash_table.setHorizontalHeaderLabels(
            ["Cashier Name", "Discrepancies (net)", "Blind Count (net)", "Total Net", "# Records"]
        )
        self._cash_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._cash_table.setAlternatingRowColors(True)
        self._cash_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._cash_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._cash_table.verticalHeader().setVisible(False)
        self._cash_table.setMinimumHeight(200)
        cash_lay.addWidget(self._cash_table)
        root.addWidget(cash_card)

        # ── Generate report row ───────────────────────────────────────
        btn_row = QHBoxLayout()
        self._gen_btn = QPushButton("Generate Report")
        self._gen_btn.setObjectName("primary")
        self._gen_btn.setFixedHeight(38)
        self._gen_btn.setMinimumWidth(180)
        self._gen_btn.clicked.connect(self._open_report_dialog)
        btn_row.addStretch(); btn_row.addWidget(self._gen_btn); btn_row.addStretch()
        root.addLayout(btn_row)

        # ── State ─────────────────────────────────────────────────────
        self._hist_date = "This Report"
        self._hist_type = "All"
        self._cash_date = "This Report"
        self._cash_type = "All"
        self._hist_custom_start: datetime.date | None = None
        self._hist_custom_end:   datetime.date | None = None
        self._cash_custom_start: datetime.date | None = None
        self._cash_custom_end:   datetime.date | None = None

        self._set_active_toggle(self._hist_date_btns, "This Report")
        self._set_active_toggle(self._hist_type_btns, "All")
        self._set_active_toggle(self._cash_date_btns, "This Report")
        self._set_active_toggle(self._cash_type_btns, "All")

    # ── Toggle helpers ────────────────────────────────────────────────────────
    def _set_active_toggle(self, btn_dict, active_key):
        for k, b in btn_dict.items():
            b.setChecked(k == active_key)
            _apply_toggle_style(b, k == active_key)

    def _on_hist_date(self, rng):
        if rng == "Custom Range":
            dlg = _DateRangeDialog(self._hist_custom_start, self._hist_custom_end, self)
            if dlg.exec() != QDialog.Accepted:
                self._set_active_toggle(self._hist_date_btns, self._hist_date)
                return
            self._hist_custom_start = dlg.start_date
            self._hist_custom_end   = dlg.end_date
        self._hist_date = rng
        self._set_active_toggle(self._hist_date_btns, rng)
        self._refresh_histogram()

    def _on_hist_type(self, t):
        self._hist_type = t
        self._set_active_toggle(self._hist_type_btns, t)
        self._refresh_histogram()

    def _on_cash_date(self, rng):
        if rng == "Custom Range":
            dlg = _DateRangeDialog(self._cash_custom_start, self._cash_custom_end, self)
            if dlg.exec() != QDialog.Accepted:
                self._set_active_toggle(self._cash_date_btns, self._cash_date)
                return
            self._cash_custom_start = dlg.start_date
            self._cash_custom_end   = dlg.end_date
        self._cash_date = rng
        self._set_active_toggle(self._cash_date_btns, rng)
        self._refresh_cashier_table()

    def _on_cash_type(self, t):
        self._cash_type = t
        self._set_active_toggle(self._cash_type_btns, t)
        self._refresh_cashier_table()

    # ── Data loading ──────────────────────────────────────────────────────────
    def _load_db(self):
        if not os.path.exists(ALL_DISC_DB):
            return pd.DataFrame()
        try:
            df = pd.read_csv(ALL_DISC_DB, dtype=str)
            df["Discrepancy"]    = pd.to_numeric(df.get("Discrepancy", pd.Series(dtype=float)), errors='coerce').fillna(0)
            df["Expected Total"] = pd.to_numeric(df.get("Expected Total", pd.Series(dtype=float)), errors='coerce').fillna(0)
            df["Total Processed"]= pd.to_numeric(df.get("Total Processed", pd.Series(dtype=float)), errors='coerce').fillna(0)
            return df
        except Exception as e:
            logging.error(f"DiscTab load db: {e}")
            return pd.DataFrame()

    def _df_for_range(self, date_range, custom_start=None, custom_end=None):
        if date_range == "This Report":
            df = getattr(self.app, "active_df", None)
            if df is None or df.empty:
                return pd.DataFrame()
            if COL_DISC not in df.columns:
                return pd.DataFrame()
            sub = df.copy()
            sub["Discrepancy"] = pd.to_numeric(sub[COL_DISC], errors='coerce').fillna(0)
            sub = sub[sub["Discrepancy"] != 0].copy()

            exp_col = EXPECTED_TOTAL if EXPECTED_TOTAL in sub.columns else None
            def _get_type(row):
                ev = pd.to_numeric(row.get(exp_col, 0), errors='coerce') if exp_col else 0
                return "Blind Count" if (pd.isna(ev) or ev == 0) else "Discrepancy"
            sub["Type"] = sub.apply(_get_type, axis=1)
            sub["Cashier Name"] = sub.get("Cashier Name", sub.get(OPERATOR, ""))
            return sub

        db = self._load_db()
        if db.empty:
            return db

        today = datetime.date.today()
        if "Report Date" not in db.columns:
            return db

        def _parse_date(s):
            for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
                try:
                    return datetime.datetime.strptime(str(s).strip(), fmt).date()
                except Exception:
                    pass
            return None

        db["_date"] = db["Report Date"].apply(_parse_date)
        db = db[db["_date"].notna()].copy()

        if date_range == "Today":
            db = db[db["_date"] == today]
        elif date_range == "This Week":
            week_start = today - datetime.timedelta(days=today.weekday())
            db = db[db["_date"] >= week_start]
        elif date_range == "This Month":
            db = db[(db["_date"].apply(lambda d: d.month) == today.month) &
                    (db["_date"].apply(lambda d: d.year) == today.year)]
        elif date_range == "This Year":
            db = db[db["_date"].apply(lambda d: d.year) == today.year]
        elif date_range == "Custom Range":
            if custom_start and custom_end:
                db = db[(db["_date"] >= custom_start) & (db["_date"] <= custom_end)]
        # "All Time" — no filter

        return db

    def _apply_type_filter(self, df, type_filter):
        if "Type" not in df.columns:
            return df
        if type_filter == "Discrepancies Only":
            return df[df["Type"] == "Discrepancy"]
        if type_filter == "Blind Counts Only":
            return df[df["Type"] == "Blind Count"]
        return df

    # ── Histogram refresh ─────────────────────────────────────────────────────
    def _refresh_histogram(self):
        try:
            df = self._df_for_range(self._hist_date, self._hist_custom_start, self._hist_custom_end)
            df = self._apply_type_filter(df, self._hist_type)
            if df.empty:
                self._histogram.set_data([])
                return

            disc_vals = pd.to_numeric(df["Discrepancy"], errors='coerce').fillna(0)
            type_col  = df.get("Type", pd.Series(["Discrepancy"] * len(df), index=df.index))

            buckets = []
            for lo, hi, label in BUCKETS:
                mask_abs = disc_vals.abs() >= lo
                if hi is not None:
                    mask_abs = mask_abs & (disc_vals.abs() < hi)
                sub = df[mask_abs]
                disc_sub = disc_vals[mask_abs]
                type_sub = type_col[mask_abs] if hasattr(type_col, '__getitem__') else type_col.loc[mask_abs]
                pos_c   = int((disc_sub > 0).sum())
                neg_c   = int((disc_sub < 0).sum())
                blind_c = int((type_sub == "Blind Count").sum())
                # blind counts already counted in pos/neg — separate them out
                pos_c  -= int(((disc_sub > 0) & (type_sub == "Blind Count")).sum())
                neg_c  -= int(((disc_sub < 0) & (type_sub == "Blind Count")).sum())
                buckets.append((label, max(0, pos_c), max(0, neg_c), max(0, blind_c)))

            self._histogram.set_data(buckets)
        except Exception as e:
            logging.error(f"DiscTab histogram: {e}")

    # ── Cashier table refresh ─────────────────────────────────────────────────
    def _refresh_cashier_table(self):
        try:
            df = self._df_for_range(self._cash_date, self._cash_custom_start, self._cash_custom_end)
            df = self._apply_type_filter(df, self._cash_type)

            # Populate cashier combo from current data (all-time so options don't change)
            if self._cash_date == "This Report":
                all_df = df
            else:
                all_df = self._load_db()

            name_col = "Cashier Name" if "Cashier Name" in (all_df.columns if not all_df.empty else []) else None
            current_cashier = self._cash_combo.currentText()
            self._cash_combo.blockSignals(True)
            self._cash_combo.clear()
            self._cash_combo.addItem("All Cashiers")
            if name_col and not all_df.empty:
                for n in sorted(all_df[name_col].dropna().unique()):
                    self._cash_combo.addItem(str(n))
            idx = self._cash_combo.findText(current_cashier)
            self._cash_combo.setCurrentIndex(max(0, idx))
            self._cash_combo.blockSignals(False)

            if df.empty:
                self._cash_table.setRowCount(0)
                return

            name_col = "Cashier Name" if "Cashier Name" in df.columns else None
            if not name_col:
                self._cash_table.setRowCount(0)
                return

            selected = self._cash_combo.currentText()
            if selected != "All Cashiers":
                df = df[df[name_col] == selected]

            disc_vals = pd.to_numeric(df["Discrepancy"], errors='coerce').fillna(0)
            type_col  = df.get("Type", pd.Series(["Discrepancy"] * len(df), index=df.index))

            rows = []
            for name, grp in df.groupby(name_col):
                grp_disc = pd.to_numeric(grp["Discrepancy"], errors='coerce').fillna(0)
                grp_type = type_col.loc[grp.index] if hasattr(type_col, 'loc') else grp.get("Type", pd.Series())
                disc_net  = float(grp_disc[grp_type != "Blind Count"].sum())
                blind_net = float(grp_disc[grp_type == "Blind Count"].sum())
                total_net = float(grp_disc.sum())
                count     = len(grp)
                rows.append((str(name), disc_net, blind_net, total_net, count))

            rows.sort(key=lambda r: abs(r[3]), reverse=True)
            self._cash_table.setRowCount(len(rows))

            for ri, (name, disc_net, blind_net, total_net, count) in enumerate(rows):
                def _item(val, is_money=False, is_count=False):
                    if is_count:
                        text = str(val)
                    elif is_money:
                        text = f"€{val:+,.2f}" if val != 0 else "€0.00"
                    else:
                        text = str(val)
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    if is_money and val < 0:
                        item.setForeground(QColor(CHART_RED))
                    elif is_money and val > 0:
                        item.setForeground(QColor(CHART_GREEN))
                    return item

                self._cash_table.setItem(ri, 0, QTableWidgetItem(name))
                self._cash_table.setItem(ri, 1, _item(disc_net, is_money=True))
                self._cash_table.setItem(ri, 2, _item(blind_net, is_money=True))
                self._cash_table.setItem(ri, 3, _item(total_net, is_money=True))
                self._cash_table.setItem(ri, 4, _item(count, is_count=True))

        except Exception as e:
            logging.error(f"DiscTab cashier table: {e}")

    # ── Report dialog ─────────────────────────────────────────────────────────
    def _open_report_dialog(self):
        from pages.discrepancy_report import DiscrepancyReportDialog
        dlg = DiscrepancyReportDialog(
            self.app,
            hist_date=self._hist_date,
            hist_type=self._hist_type,
            cash_date=self._cash_date,
            cash_type=self._cash_type,
            custom_start=self._hist_custom_start,
            custom_end=self._hist_custom_end,
            parent=self,
        )
        dlg.exec()

    # ── Refresh on show ───────────────────────────────────────────────────────
    def showEvent(self, e):
        super().showEvent(e)
        self._refresh_histogram()
        self._refresh_cashier_table()

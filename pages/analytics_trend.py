"""
pages/analytics_trend.py — Trend Analysis tab (rebuilt).

Three views, unified date-range picker (DD.MM.YYYY), two data sources:

  Source A — Audit_Database.csv (SLIP_HISTORY_DB)
             Columns: Date, Name, Operator_Id, System Count, Total Value
             One row per cashier per report date.
             Written by integrity.py every time a report is run.

  Source B — Discrepancies Database /*.xlsx
             Columns: Cashier Name, Operator Id, Small_Discrepancies, Report_Date
             Written by integrity.py for every small discrepancy found.

Views:
  1. Transaction Volume   — daily total slips + total value from Source A
  2. Cashier Breakdown    — per-cashier bar chart for the selected window
  3. Anomaly Rate         — small-discrepancy events / 1000 txns (combined sources)

Plus:
  - Rising Cashiers alert (anomaly rate rising, not raw count)
  - Per-cashier table with month columns and trend arrows
  - Anomaly Heatmap
"""
import datetime
import glob
import logging
import os

import pandas as pd

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen
)
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from config import DISCREPANCY_DB_PATH, SLIP_HISTORY_DB
from theme import Theme
from pages.analytics_dashboard import CHART_BLUES


# ── helpers ───────────────────────────────────────────────────────────────────

def _card(title="", subtitle=""):
    f = QFrame()
    f.setStyleSheet(
        f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};"
        f"border-radius:8px;}}"
    )
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 14, 18, 16)
    lay.setSpacing(10)
    if title:
        hl = QHBoxLayout(); hl.setSpacing(10)
        t = QLabel(title)
        t.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:600;")
        hl.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
            hl.addWidget(s)
        hl.addStretch()
        lay.addLayout(hl)
        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div)
    return f, lay


def _parse_date(s: str):
    """Parse DD.MM.YYYY → datetime.date, or None."""
    try:
        return datetime.datetime.strptime(s.strip(), "%d.%m.%Y").date()
    except Exception:
        return None


def _fmt_date(d: datetime.date) -> str:
    return d.strftime("%d.%m.%Y")


def _month_key(d: datetime.date) -> str:
    return d.strftime("%b %y")


# ── Dual-series animated line chart ──────────────────────────────────────────

class DualLineChart(QWidget):
    """
    Draws up to two overlaid line series with animated crossfade on data change.
    series_a: list of (label, value)  — left Y axis (e.g. slip count)
    series_b: list of (label, value)  — right Y axis (e.g. total value)
    Colors: series_a = ACCENT (blue), series_b = GOLD (pale blue)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._a      = []
        self._b      = []
        self._prev_a = []
        self._prev_b = []
        self._t      = 1.0
        self._timer  = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, series_a, series_b=None):
        if series_a == self._a and (series_b or []) == self._b:
            return
        self._prev_a = list(self._a)
        self._prev_b = list(self._b)
        self._a = list(series_a)
        self._b = list(series_b or [])
        self._t = 0.0
        self._timer.start()

    def _tick(self):
        self._t = min(1.0, self._t + 0.06)
        self.update()
        if self._t >= 1.0:
            self._timer.stop()

    def _draw_line(self, p, data, W, H, pl, pr, pt_, pb,
                   color_hex, alpha, use_right_axis=False,
                   global_max=None):
        data = [(lbl, v) for lbl, v in data if v is not None and v == v]  # drop NaN
        if len(data) < 2:
            return
        n     = len(data)
        vals  = [v for _, v in data]
        max_v = global_max if global_max else (max(vals) or 1)

        def px(i, v):
            x = pl + int((W - pl - pr) * i / (n - 1))
            y = pt_ + int((H - pt_ - pb) * (1 - v / max_v))
            return x, y

        # fill
        path = QPainterPath()
        x0, y0 = px(0, data[0][1])
        path.moveTo(x0, H - pb)
        path.lineTo(x0, y0)
        for i, (_, v) in enumerate(data[1:], 1):
            xi, yi = px(i, v)
            path.lineTo(xi, yi)
        xl, _ = px(n - 1, data[-1][1])
        path.lineTo(xl, H - pb)
        path.closeSubpath()
        fill = QColor(color_hex)
        fill.setAlpha(int(18 * alpha))
        p.setBrush(QBrush(fill)); p.setPen(Qt.NoPen)
        p.drawPath(path)

        # line
        lc = QColor(color_hex); lc.setAlpha(int(220 * alpha))
        pen = QPen(lc); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        path2 = QPainterPath()
        x0, y0 = px(0, data[0][1])
        path2.moveTo(x0, y0)
        for i, (_, v) in enumerate(data[1:], 1):
            path2.lineTo(*px(i, v))
        p.drawPath(path2)

        # dots
        dc = QColor(color_hex); dc.setAlpha(int(255 * alpha))
        p.setBrush(QBrush(dc)); p.setPen(Qt.NoPen)
        for i, (_, v) in enumerate(data):
            xi, yi = px(i, v)
            p.drawEllipse(xi - 3, yi - 3, 6, 6)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        pl, pr, pt_, pb = 52, 52, 18, 32

        t = self._t
        ease = t * t * (3 - 2 * t)

        no_data = not self._a and not self._prev_a
        if no_data:
            p.setPen(QColor(Theme.TXT_3))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "No transaction history yet.\nRun Integrity Check to start building data.")
            p.end(); return

        # grid
        p.setPen(QPen(QColor(Theme.BORDER_S)))
        for i in range(5):
            gy = pt_ + int(i / 4 * (H - pt_ - pb))
            p.drawLine(pl, gy, W - pr, gy)

        # fade out previous
        if self._prev_a and ease < 1.0:
            self._draw_line(p, self._prev_a, W, H, pl, pr, pt_, pb,
                            Theme.ACCENT, 1.0 - ease)
            if self._prev_b:
                self._draw_line(p, self._prev_b, W, H, pl, pr, pt_, pb,
                                Theme.GOLD, 1.0 - ease, use_right_axis=True)

        # fade in current
        alpha_in = ease if self._prev_a else 1.0
        if self._a:
            self._draw_line(p, self._a, W, H, pl, pr, pt_, pb,
                            Theme.ACCENT, alpha_in)
        if self._b:
            self._draw_line(p, self._b, W, H, pl, pr, pt_, pb,
                            Theme.GOLD, alpha_in, use_right_axis=True)

        if ease < 1.0 and self._prev_a:
            p.end(); return

        # x-axis labels (only when settled)
        data = self._a or self._prev_a
        if not data:
            p.end(); return
        n = len(data)
        f = QFont(); f.setPointSize(7)
        p.setFont(f); p.setPen(QColor(Theme.TXT_3))
        step = max(1, n // 12)
        for i, (lbl, _) in enumerate(data):
            if i % step != 0 and i != n - 1:
                continue
            xi = pl + int((W - pl - pr) * i / max(n - 1, 1))
            p.drawText(xi - 22, H - pb + 4, 44, pb - 4,
                       Qt.AlignHCenter | Qt.AlignTop, lbl)

        # left Y axis ticks (slips)
        if self._a:
            max_a = max(v for _, v in self._a) or 1
            p.setPen(QColor(Theme.ACCENT))
            f2 = QFont(); f2.setPointSize(7)
            p.setFont(f2)
            for i in range(5):
                frac = i / 4
                val  = max_a * frac
                gy   = pt_ + int((1 - frac) * (H - pt_ - pb))
                label = f"{int(val):,}"
                p.drawText(0, gy - 8, pl - 4, 16,
                           Qt.AlignRight | Qt.AlignVCenter, label)

        # right Y axis ticks (value)
        if self._b:
            max_b = max(v for _, v in self._b) or 1
            p.setPen(QColor(Theme.GOLD))
            for i in range(5):
                frac = i / 4
                val  = max_b * frac
                gy   = pt_ + int((1 - frac) * (H - pt_ - pb))
                label = f"€{val:,.0f}" if max_b > 100 else f"€{val:.1f}"
                p.drawText(W - pr + 4, gy - 8, pr - 4, 16,
                           Qt.AlignLeft | Qt.AlignVCenter, label)

        p.end()


# ── Per-cashier bar chart ─────────────────────────────────────────────────────

class CashierBarChart(QWidget):
    """Horizontal bar chart: each row = one cashier, bar width = metric value."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data  = []   # list of (name, value)
        self._color = Theme.ACCENT
        self._fmt   = "{:,}"
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, data, color=None, fmt="{:,}"):
        self._data  = data[:20]
        self._color = color or Theme.ACCENT
        self._fmt   = fmt
        row_h = max(24, min(36, 400 // max(len(data), 1)))
        self.setMinimumHeight(max(180, len(self._data) * row_h + 20))
        self.update()

    def paintEvent(self, e):
        if not self._data:
            p = QPainter(self)
            p.setPen(QColor(Theme.TXT_3))
            p.drawText(self.rect(), Qt.AlignCenter, "No data")
            p.end(); return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H   = self.width(), self.height()
        lbl_w  = 130
        val_w  = 60
        bar_x  = lbl_w + 8
        bar_w  = W - bar_x - val_w - 8
        n      = len(self._data)
        row_h  = max(20, (H - 10) // n)
        max_v  = max(v for _, v in self._data) or 1

        f = QFont(); f.setPointSize(9)
        fv = QFont(); fv.setPointSize(8); fv.setBold(True)

        for i, (name, val) in enumerate(self._data):
            y    = 5 + i * row_h
            frac = val / max_v

            # alternating row bg
            bg = QColor(Theme.ELEVATED if i % 2 == 0 else Theme.SURFACE)
            bg.setAlpha(80)
            p.setBrush(QBrush(bg)); p.setPen(Qt.NoPen)
            p.drawRoundedRect(0, y, W, row_h - 2, 3, 3)

            # bar
            bw = max(2, int(bar_w * frac))
            bar_color = QColor(self._color)
            bar_color.setAlpha(180)
            p.setBrush(QBrush(bar_color)); p.setPen(Qt.NoPen)
            p.drawRoundedRect(bar_x, y + 4, bw, row_h - 10, 2, 2)

            # name
            p.setFont(f); p.setPen(QColor(Theme.TXT_2))
            p.drawText(4, y, lbl_w - 4, row_h,
                       Qt.AlignLeft | Qt.AlignVCenter,
                       str(name)[:18] + ("…" if len(str(name)) > 18 else ""))

            # value
            p.setFont(fv); p.setPen(QColor(self._color))
            try:
                val_str = self._fmt.format(val)
            except Exception:
                val_str = str(val)
            p.drawText(W - val_w, y, val_w - 4, row_h,
                       Qt.AlignRight | Qt.AlignVCenter, val_str)

        p.end()


# ── Anomaly Heatmap ───────────────────────────────────────────────────────────

class HeatmapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cells = {}
        self._rows  = []
        self._cols  = []
        self._max_v = 1
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, rows, cols, matrix):
        self._rows  = rows
        self._cols  = cols
        self._cells = matrix
        self._max_v = max(matrix.values(), default=1) or 1
        self.setMinimumHeight(max(180, len(rows) * 24 + 40))
        self.update()

    def paintEvent(self, e):
        from PySide6.QtCore import QRectF
        if not self._rows or not self._cols:
            p = QPainter(self)
            p.setPen(QColor(Theme.TXT_3))
            p.drawText(self.rect(), Qt.AlignCenter, "No data")
            p.end(); return

        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        W, H   = self.width(), self.height()
        lbl_w  = 130; hdr_h = 22
        cell_h = max(18, int((H - hdr_h) / max(len(self._rows), 1)))
        cell_w = max(28, int((W - lbl_w) / max(len(self._cols), 1)))

        f = QFont(); f.setPointSize(7); f.setBold(True)
        p.setFont(f); p.setPen(QColor(Theme.TXT_3))
        for ci, col in enumerate(self._cols):
            p.drawText(lbl_w + ci * cell_w, 0, cell_w, hdr_h,
                       Qt.AlignCenter, str(col)[:6])

        for ri, row in enumerate(self._rows):
            y = hdr_h + ri * cell_h
            lf = QFont(); lf.setPointSize(8); p.setFont(lf)
            p.setPen(QColor(Theme.TXT_2))
            lbl = str(row)[:16] + ("…" if len(str(row)) > 16 else "")
            p.drawText(0, y, lbl_w - 4, cell_h,
                       Qt.AlignRight | Qt.AlignVCenter, lbl)

            for ci in range(len(self._cols)):
                val = self._cells.get((ri, ci), 0)
                intensity = val / self._max_v
                r = int(0x05 + intensity * (0x4d - 0x05))
                g = int(0x07 + intensity * (0x9f - 0x07))
                b = int(0x0d + intensity * (0xff - 0x0d))
                color = QColor(r, g, b)
                color.setAlpha(220 if val else 60)
                x = lbl_w + ci * cell_w
                p.setBrush(color); p.setPen(QColor(Theme.BORDER_S))
                p.drawRoundedRect(QRectF(x+1, y+1, cell_w-2, cell_h-2), 2, 2)
                if val:
                    p.setPen(QColor("#ffffff" if intensity > 0.5 else Theme.TXT_3))
                    vf = QFont(); vf.setPointSize(7); p.setFont(vf)
                    p.drawText(x, y, cell_w, cell_h, Qt.AlignCenter, str(val))
        p.end()


# =============================================================================
# TrendAnalysisPage
# =============================================================================

class TrendAnalysisPage(QWidget):

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._first_show = True
        self._build()
        QTimer.singleShot(300, self.refresh)

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        self._root = QVBoxLayout(inner)
        self._root.setContentsMargins(24, 20, 24, 24)
        self._root.setSpacing(20)
        self._root.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # ── Header + controls ─────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(10)
        title = QLabel("Trend Analysis")
        title.setStyleSheet(
            f"color:{Theme.TXT};font-size:18px;font-weight:700;"
        )
        hdr.addWidget(title); hdr.addStretch()

        def _lbl(t):
            l = QLabel(t)
            l.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
            return l

        self._from_input = QLineEdit()
        self._from_input.setPlaceholderText("From  DD.MM.YYYY")
        self._from_input.setFixedWidth(148)

        self._to_input = QLineEdit()
        self._to_input.setPlaceholderText("To  DD.MM.YYYY")
        self._to_input.setFixedWidth(148)

        self._period_combo = QComboBox()
        self._period_combo.addItems([
            "This Report", "Today", "This Week", "This Month", "All Time"
        ])
        self._period_combo.setCurrentIndex(0)   # default: This Report
        self._period_combo.setFixedWidth(140)
        self._period_combo.currentIndexChanged.connect(self._on_period_changed)

        self._view_combo = QComboBox()
        self._view_combo.addItems([
            "Transaction Volume",
            "Cashier Breakdown",
            "Anomaly Rate",
        ])
        self._view_combo.setFixedWidth(185)
        self._view_combo.currentIndexChanged.connect(self._on_view_changed)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("primary")
        refresh_btn.setFixedHeight(32)
        refresh_btn.clicked.connect(self.refresh)

        for w in [_lbl("Period:"), self._period_combo,
                  _lbl("View:"), self._view_combo,
                  _lbl("From:"), self._from_input,
                  _lbl("To:"), self._to_input,
                  refresh_btn]:
            hdr.addWidget(w)
        self._root.addLayout(hdr)

        sub = QLabel(
            "Select a period preset or enter a custom date range (DD.MM.YYYY).  "
            "History is built automatically each time you run Integrity Check.  "
            "\u2018This Report\u2019 shows only the currently loaded report."
        )
        sub.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
        sub.setWordWrap(True)
        self._root.addWidget(sub)

        # ── Summary pills ─────────────────────────────────────────────
        pills_row = QHBoxLayout(); pills_row.setSpacing(10)
        self._pill_reports  = self._make_pill("Reports",         "—", Theme.ACCENT)
        self._pill_cashiers = self._make_pill("Cashiers",        "—", Theme.INFO)
        self._pill_slips    = self._make_pill("Total Slips",     "—", Theme.GOLD)
        self._pill_value    = self._make_pill("Total Value",     "—", Theme.OK)
        self._pill_anomaly  = self._make_pill("Anomaly Rate",    "—", Theme.WARN)
        self._pill_rising   = self._make_pill("Rising ▲",        "—", Theme.DANGER)
        for pf, _ in [self._pill_reports, self._pill_cashiers,
                      self._pill_slips, self._pill_value,
                      self._pill_anomaly, self._pill_rising]:
            pills_row.addWidget(pf)
        self._root.addLayout(pills_row)

        # ── View 1 — Transaction Volume ───────────────────────────────
        self._vol_card, vol_lay = _card(
            "Transaction Volume Over Time",
            "daily total slips (blue, left axis)  ·  total value €  (pale blue, right axis)"
        )
        self._vol_chart = DualLineChart()
        self._vol_chart.setMinimumHeight(240)
        vol_lay.addWidget(self._vol_chart)
        self._root.addWidget(self._vol_card)

        # ── View 2 — Cashier Breakdown ────────────────────────────────
        self._brk_card, brk_lay = _card(
            "Cashier Breakdown",
            "total slips per cashier for the selected period"
        )
        # metric toggle
        brk_ctrl = QHBoxLayout(); brk_ctrl.setSpacing(8)
        self._brk_metric = QComboBox()
        self._brk_metric.addItems(["Slip Count", "Total Value €"])
        self._brk_metric.currentIndexChanged.connect(self._redraw_breakdown)
        brk_ctrl.addWidget(QLabel("Metric:").also(
            lambda l: l.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")))
        brk_ctrl.addWidget(self._brk_metric)
        brk_ctrl.addStretch()
        brk_lay.addLayout(brk_ctrl)
        self._brk_chart = CashierBarChart()
        brk_lay.addWidget(self._brk_chart)
        self._root.addWidget(self._brk_card)

        # ── View 3 — Anomaly Rate ─────────────────────────────────────
        self._anom_card, anom_lay = _card(
            "Anomaly Rate Over Time",
            "small discrepancies per 1,000 transactions — spikes here are the real signal"
        )
        self._anom_chart = DualLineChart()
        self._anom_chart.setMinimumHeight(200)
        anom_lay.addWidget(self._anom_chart)
        self._root.addWidget(self._anom_card)

        # ── Rising cashiers ───────────────────────────────────────────
        self._rising_card, rising_lay = _card(
            "⚠  Rising Risk  —  Anomaly rate trending upward",
            "cashiers whose rate in the last 3 periods exceeds their prior 3-period average"
        )
        self._rising_list = QVBoxLayout(); self._rising_list.setSpacing(4)
        rising_lay.addLayout(self._rising_list)
        self._rising_card.setVisible(False)
        self._root.addWidget(self._rising_card)

        # ── Per-cashier table ─────────────────────────────────────────
        self._tbl_card, tbl_lay = _card(
            "Per-Cashier Breakdown",
            "slips per cashier per report date — most recent dates shown"
        )
        self._tbl_area = QWidget(); self._tbl_area.setStyleSheet("background:transparent;")
        self._tbl_lay  = QVBoxLayout(self._tbl_area)
        self._tbl_lay.setContentsMargins(0, 0, 0, 0); self._tbl_lay.setSpacing(3)
        tbl_lay.addWidget(self._tbl_area)
        self._root.addWidget(self._tbl_card)

        # ── Anomaly Heatmap ───────────────────────────────────────────
        hm_card = QFrame()
        hm_card.setStyleSheet(
            f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};"
            f"border-radius:8px;}}"
        )
        hl = QVBoxLayout(hm_card); hl.setContentsMargins(18, 14, 18, 16); hl.setSpacing(10)
        hmhdr = QHBoxLayout()
        hmhdr.addWidget(QLabel("Anomaly Heatmap").also(
            lambda l: l.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:600;")))
        hmhdr.addWidget(QLabel("discrepancy events per cashier × report date").also(
            lambda l: l.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")))
        hmhdr.addStretch()
        hl.addLayout(hmhdr)
        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};"); hl.addWidget(div)
        self._heatmap = HeatmapWidget()
        hm_scroll = QScrollArea()
        hm_scroll.setWidgetResizable(True); hm_scroll.setFrameShape(QFrame.NoFrame)
        hm_scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        hm_scroll.setWidget(self._heatmap); hm_scroll.setMinimumHeight(200)
        hl.addWidget(hm_scroll)
        leg = QHBoxLayout(); leg.setSpacing(6)
        leg.addWidget(QLabel("Low").also(lambda l: l.setStyleSheet(
            f"color:{Theme.TXT_3};font-size:10px;")))
        for intensity in [0.1, 0.3, 0.5, 0.7, 0.9]:
            sq = QFrame(); sq.setFixedSize(16, 12)
            r = int(0x05 + intensity * (0x4d - 0x05))
            g = int(0x07 + intensity * (0x9f - 0x07))
            b = int(0x0d + intensity * (0xff - 0x0d))
            sq.setStyleSheet(f"background:rgb({r},{g},{b});border-radius:2px;")
            leg.addWidget(sq)
        leg.addWidget(QLabel("High").also(lambda l: l.setStyleSheet(
            f"color:{Theme.TXT_3};font-size:10px;")))
        leg.addStretch()
        hl.addLayout(leg)
        self._root.addWidget(hm_card)

        # ── No data placeholder ───────────────────────────────────────
        self._no_data = QLabel(
            "No history found.  Run Integrity Check on a report to start building data."
        )
        self._no_data.setAlignment(Qt.AlignCenter)
        self._no_data.setStyleSheet(
            f"color:{Theme.TXT_3};font-size:13px;padding:60px;"
        )
        self._root.addWidget(self._no_data)

        # cached data for redraw
        self._cached_vol_data    = {}   # date_str -> {slips, value}
        self._cached_cashier_data= {}   # name -> {date_str: slips, ...}
        self._cached_anom_data   = {}   # date_str -> discrepancy_count

        self._on_view_changed(0)

    # ── Pills ──────────────────────────────────────────────────────────────────

    def _make_pill(self, label, value, color):
        sf = QFrame()
        sf.setStyleSheet(
            f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER};"
            f"border-radius:8px;}}"
        )
        sl = QVBoxLayout(sf); sl.setContentsMargins(16, 12, 16, 12); sl.setSpacing(4)
        v = QLabel(value)
        v.setStyleSheet(
            f"color:{color};font-size:20px;font-weight:700;"
            f"font-family:Consolas,monospace;"
        )
        k = QLabel(label)
        k.setStyleSheet(
            f"color:{Theme.TXT_3};font-size:9px;font-weight:700;letter-spacing:1.5px;"
        )
        sl.addWidget(v); sl.addWidget(k)
        return sf, v

    # ── View toggle ────────────────────────────────────────────────────────────

    def _on_view_changed(self, idx):
        cards = [self._vol_card, self._brk_card, self._anom_card]
        for i, card in enumerate(cards):
            if i == idx:
                card.setVisible(True)
                fx = getattr(card, '_fade_fx', None)
                if fx is None:
                    from PySide6.QtWidgets import QGraphicsOpacityEffect  # noqa: PLC0415
                    fx = QGraphicsOpacityEffect(card)
                    card.setGraphicsEffect(fx)
                    card._fade_fx = fx
                fx.setOpacity(0.0)
                anim = QPropertyAnimation(fx, b"opacity")
                anim.setDuration(200)
                anim.setStartValue(0.0)
                anim.setEndValue(1.0)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                anim.start()
                card._fade_anim = anim
            else:
                card.setVisible(False)

    # ── Data loading ───────────────────────────────────────────────────────────

    def _on_period_changed(self, idx):
        """Pre-fill the From/To inputs based on the selected preset."""
        import datetime as _dt
        period = self._period_combo.currentText()
        today  = _dt.date.today()

        if period == "This Report":
            # Use the active report's date for both From and To
            report_date = getattr(self.app, "_active_report_date", None)
            if report_date:
                self._from_input.setText(report_date)
                self._to_input.setText(report_date)
            else:
                self._from_input.clear()
                self._to_input.clear()
        elif period == "Today":
            ds = _fmt_date(today)
            self._from_input.setText(ds)
            self._to_input.setText(ds)
        elif period == "This Week":
            self._from_input.setText(_fmt_date(today - _dt.timedelta(days=7)))
            self._to_input.setText(_fmt_date(today))
        elif period == "This Month":
            self._from_input.setText(_fmt_date(_dt.date(today.year, today.month, 1)))
            self._to_input.setText(_fmt_date(today))
        elif period == "All Time":
            self._from_input.clear()
            self._to_input.clear()

        self.refresh()

    def refresh(self):
        try:
            from_date = _parse_date(self._from_input.text())
            to_date   = _parse_date(self._to_input.text())

            # ── Load Source A: Audit_Database.csv ─────────────────────
            vol_data    = {}   # date_str -> {"slips": int, "value": float}
            cashier_data= {}   # name -> {date_str: int (slips)}

            if os.path.exists(SLIP_HISTORY_DB):
                try:
                    hdf = pd.read_csv(SLIP_HISTORY_DB, dtype=str)
                    hdf["System Count"] = pd.to_numeric(
                        hdf.get("System Count", pd.Series()), errors="coerce"
                    ).fillna(0)
                    hdf["Total Value"] = pd.to_numeric(
                        hdf.get("Total Value", pd.Series()), errors="coerce"
                    ).fillna(0)
                    for _, row in hdf.iterrows():
                        date_str = str(row.get("Date", "")).strip()
                        name     = str(row.get("Name", "")).strip()
                        slips    = int(row.get("System Count", 0))
                        value    = float(row.get("Total Value", 0))
                        if not date_str or not name:
                            continue
                        d = _parse_date(date_str)
                        if d is None:
                            continue
                        if from_date and d < from_date:
                            continue
                        if to_date and d > to_date:
                            continue
                        if date_str not in vol_data:
                            vol_data[date_str] = {"slips": 0, "value": 0.0}
                        vol_data[date_str]["slips"] += slips
                        vol_data[date_str]["value"] += value
                        if name not in cashier_data:
                            cashier_data[name] = {}
                        cashier_data[name][date_str] = (
                            cashier_data[name].get(date_str, 0) + slips
                        )
                except Exception:
                    logging.exception("Trend: failed reading SLIP_HISTORY_DB")

            # ── Load Source B: Discrepancy archive ────────────────────
            anom_data = {}   # date_str -> int (discrepancy event count)
            anom_cashier = {}  # name -> {date_str: int}

            pattern = os.path.join(DISCREPANCY_DB_PATH, "**", "*.xlsx")
            for fp in glob.glob(pattern, recursive=True):
                try:
                    tmp = pd.read_excel(fp)
                    if "Cashier Name" not in tmp.columns:
                        continue
                    date_col = "Report_Date" if "Report_Date" in tmp.columns else None
                    for _, row in tmp.iterrows():
                        name   = str(row.get("Cashier Name", "Unknown")).strip()
                        events = int(row.get("Small_Discrepancies", 1))
                        date_str = ""
                        if date_col:
                            try:
                                dt = pd.to_datetime(
                                    str(row[date_col]), dayfirst=True
                                )
                                date_str = dt.strftime("%d.%m.%Y")
                            except Exception:
                                pass
                        else:
                            parts = fp.replace("\\", "/").split("/")
                            try:
                                yr = parts[-3]; mo = parts[-2]
                                date_str = f"01.{int(mo):02d}.{yr}"
                            except Exception:
                                pass
                        if not date_str:
                            continue
                        d = _parse_date(date_str)
                        if d is None:
                            continue
                        if from_date and d < from_date:
                            continue
                        if to_date and d > to_date:
                            continue
                        anom_data[date_str] = anom_data.get(date_str, 0) + events
                        if name not in anom_cashier:
                            anom_cashier[name] = {}
                        anom_cashier[name][date_str] = (
                            anom_cashier[name].get(date_str, 0) + events
                        )
                except Exception:
                    pass

            has_data = bool(vol_data or anom_data)
            self._no_data.setVisible(not has_data)
            if not has_data:
                self._vol_chart.set_data([])
                self._anom_chart.set_data([])
                self._brk_chart.set_data([])
                return

            # ── Cache for redraw ──────────────────────────────────────
            self._cached_vol_data     = vol_data
            self._cached_cashier_data = cashier_data
            self._cached_anom_data    = anom_data
            self._cached_anom_cashier = anom_cashier

            # ── Sort dates ────────────────────────────────────────────
            all_dates = sorted(
                set(vol_data.keys()) | set(anom_data.keys()),
                key=lambda s: _parse_date(s) or datetime.date.min
            )

            # ── Summary pills ─────────────────────────────────────────
            total_slips  = sum(v["slips"] for v in vol_data.values())
            total_value  = sum(v["value"] for v in vol_data.values())
            total_anoms  = sum(anom_data.values())
            rate = (total_anoms / total_slips * 1000) if total_slips else 0.0
            n_reports  = len(all_dates)
            n_cashiers = len(cashier_data)

            _, sv = self._pill_reports;  sv.setText(str(n_reports))
            _, cv = self._pill_cashiers; cv.setText(str(n_cashiers))
            _, slv = self._pill_slips;   slv.setText(f"{total_slips:,}")
            _, vav = self._pill_value;   vav.setText(f"€{total_value:,.0f}")
            _, av  = self._pill_anomaly; av.setText(f"{rate:.1f}‰")

            # ── View 1: Transaction Volume ────────────────────────────
            # Thin dates to at most 60 points for readability
            step = max(1, len(all_dates) // 60)
            thinned = all_dates[::step]
            slips_series = [
                (self._short_label(d), vol_data.get(d, {}).get("slips", 0))
                for d in thinned
            ]
            value_series = [
                (self._short_label(d), vol_data.get(d, {}).get("value", 0.0))
                for d in thinned
            ]
            self._vol_chart.set_data(slips_series, value_series)

            # ── View 2: Cashier Breakdown (initial render) ────────────
            self._redraw_breakdown()

            # ── View 3: Anomaly Rate ──────────────────────────────────
            rate_series = []
            for d in thinned:
                slips_d = vol_data.get(d, {}).get("slips", 0)
                anoms_d = anom_data.get(d, 0)
                r = (anoms_d / slips_d * 1000) if slips_d else 0.0
                rate_series.append((self._short_label(d), r))
            self._anom_chart.set_data(rate_series)

            # ── Rising cashiers (by anomaly rate, month-bucketed) ─────
            self._compute_rising(cashier_data, anom_cashier, all_dates)

            # ── Per-cashier table ─────────────────────────────────────
            self._build_table(cashier_data, all_dates)

            # ── Heatmap ───────────────────────────────────────────────
            self._build_heatmap(anom_cashier, all_dates)

        except Exception:
            logging.exception("Trend: refresh failed")

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _short_label(date_str: str) -> str:
        """DD.MM.YYYY → DD.MM or MMM YY depending on density."""
        try:
            d = _parse_date(date_str)
            return d.strftime("%d.%m")
        except Exception:
            return date_str[:5]

    def _redraw_breakdown(self):
        cashier_data = self._cached_cashier_data
        metric = self._brk_metric.currentText()

        if metric == "Total Value €":
            # aggregate value from vol data per cashier
            # we need per-cashier value — use cached anom_cashier as proxy
            # Actually value is not stored per-cashier in cashier_data (slips only)
            # We rebuild from SLIP_HISTORY_DB cache
            cashier_val = {}
            if os.path.exists(SLIP_HISTORY_DB):
                try:
                    hdf = pd.read_csv(SLIP_HISTORY_DB, dtype=str)
                    hdf["Total Value"] = pd.to_numeric(
                        hdf.get("Total Value", pd.Series()), errors="coerce"
                    ).fillna(0)
                    from_date = _parse_date(self._from_input.text())
                    to_date   = _parse_date(self._to_input.text())
                    for _, row in hdf.iterrows():
                        date_str = str(row.get("Date", "")).strip()
                        name     = str(row.get("Name", "")).strip()
                        value    = float(row.get("Total Value", 0))
                        if not date_str or not name:
                            continue
                        d = _parse_date(date_str)
                        if d is None:
                            continue
                        if from_date and d < from_date:
                            continue
                        if to_date and d > to_date:
                            continue
                        cashier_val[name] = cashier_val.get(name, 0.0) + value
                except Exception:
                    pass
            data = sorted(cashier_val.items(), key=lambda x: x[1], reverse=True)
            self._brk_chart.set_data(data, color=Theme.GOLD, fmt="€{:,.0f}")
        else:
            data = [
                (name, sum(d.values()))
                for name, d in cashier_data.items()
            ]
            data.sort(key=lambda x: x[1], reverse=True)
            self._brk_chart.set_data(data, color=Theme.ACCENT, fmt="{:,}")

    def _compute_rising(self, cashier_data, anom_cashier, all_dates):
        while self._rising_list.count():
            item = self._rising_list.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        # bucket dates into months
        def to_month(ds):
            d = _parse_date(ds)
            return d.strftime("%b %y") if d else "?"

        months_ordered = []
        seen = set()
        for ds in all_dates:
            m = to_month(ds)
            if m not in seen:
                months_ordered.append(m)
                seen.add(m)

        if len(months_ordered) < 6:
            self._rising_card.setVisible(False)
            _, rv = self._pill_rising; rv.setText("—")
            return

        last3  = months_ordered[-3:]
        prev3  = months_ordered[-6:-3]

        # monthly anom counts
        monthly_anom = {}   # name -> {month: count}
        for name, ddata in anom_cashier.items():
            monthly_anom[name] = {}
            for ds, cnt in ddata.items():
                m = to_month(ds)
                monthly_anom[name][m] = monthly_anom[name].get(m, 0) + cnt

        # monthly slips
        monthly_slips = {}  # name -> {month: slips}
        for name, ddata in cashier_data.items():
            monthly_slips[name] = {}
            for ds, cnt in ddata.items():
                m = to_month(ds)
                monthly_slips[name][m] = monthly_slips[name].get(m, 0) + cnt

        rising = []
        all_names = set(monthly_anom.keys()) | set(monthly_slips.keys())
        for name in all_names:
            def rate(months):
                anoms = sum(monthly_anom.get(name, {}).get(m, 0) for m in months)
                slips = sum(monthly_slips.get(name, {}).get(m, 0) for m in months)
                return (anoms / slips * 1000) if slips else 0.0
            r_last = rate(last3)
            r_prev = rate(prev3)
            if r_last > r_prev > 0:
                rising.append((name, r_prev, r_last))

        rising.sort(key=lambda x: x[2], reverse=True)
        _, rv = self._pill_rising; rv.setText(str(len(rising)))
        self._rising_card.setVisible(bool(rising))

        for name, r_prev, r_last in rising[:8]:
            rw = QWidget(); rw.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(rw); rl.setContentsMargins(0, 2, 0, 2); rl.setSpacing(12)
            nl = QLabel(name)
            nl.setStyleSheet(
                f"color:{Theme.TXT};font-size:12px;font-weight:500;"
            )
            al = QLabel(
                f"Prev avg: {r_prev:.1f}‰  →  Now: {r_last:.1f}‰  ▲"
            )
            al.setStyleSheet(
                f"color:{Theme.DANGER};font-size:11px;"
                f"font-family:Consolas,monospace;"
            )
            rl.addWidget(nl, 2); rl.addWidget(al, 3); rl.addStretch()
            self._rising_list.addWidget(rw)

    def _build_table(self, cashier_data, all_dates):
        while self._tbl_lay.count():
            item = self._tbl_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if not cashier_data:
            return

        # show the 8 most recent dates
        visible_dates = all_dates[-8:] if all_dates else []
        short_dates   = [self._short_label(d) for d in visible_dates]

        # header
        hdr_w = QWidget(); hdr_w.setStyleSheet("background:transparent;")
        hdr_l = QHBoxLayout(hdr_w)
        hdr_l.setContentsMargins(12, 0, 12, 4); hdr_l.setSpacing(0)

        def _hdr(t, stretch):
            l = QLabel(t)
            l.setStyleSheet(
                f"color:{Theme.TXT_DIM};font-size:9px;font-weight:700;"
                f"letter-spacing:1.5px;"
            )
            l.setAlignment(Qt.AlignCenter)
            hdr_l.addWidget(l, stretch)

        _hdr("CASHIER", 3)
        for sd in short_dates:
            _hdr(sd, 1)
        _hdr("TREND", 1)
        self._tbl_lay.addWidget(hdr_w)

        # sort by total slips desc
        totals = [
            (name, sum(d.values()), d)
            for name, d in cashier_data.items()
        ]
        totals.sort(key=lambda x: x[1], reverse=True)

        for i, (name, total, ddata) in enumerate(totals[:30]):
            rw = QFrame()
            rw.setStyleSheet(
                f"QFrame{{background:"
                f"{'#090e18' if i%2==0 else '#0e1628'};"
                f"border-radius:4px;margin:1px 0;}}"
            )
            rl = QHBoxLayout(rw)
            rl.setContentsMargins(12, 7, 12, 7); rl.setSpacing(0)

            nl = QLabel(name)
            nl.setStyleSheet(f"color:{Theme.TXT};font-size:12px;")
            rl.addWidget(nl, 3)

            for ds in visible_dates:
                v = ddata.get(ds, 0)
                vl = QLabel(f"{v:,}" if v else "—")
                vl.setAlignment(Qt.AlignCenter)
                clr = (Theme.DANGER if v > 200 else
                       Theme.WARN   if v > 0    else Theme.TXT_DIM)
                vl.setStyleSheet(
                    f"color:{clr};font-size:11px;"
                    f"font-family:Consolas,monospace;"
                )
                rl.addWidget(vl, 1)

            # trend arrow — compare last two visible dates
            if len(visible_dates) >= 2:
                lv = ddata.get(visible_dates[-1], 0)
                pv = ddata.get(visible_dates[-2], 0)
                if lv > pv:    arrow, clr = "▲", Theme.DANGER
                elif lv < pv:  arrow, clr = "▼", Theme.OK
                else:          arrow, clr = "▬", Theme.TXT_3
            else:
                arrow, clr = "—", Theme.TXT_3

            al = QLabel(arrow)
            al.setStyleSheet(
                f"color:{clr};font-size:13px;font-weight:700;"
            )
            al.setAlignment(Qt.AlignCenter)
            rl.addWidget(al, 1)
            self._tbl_lay.addWidget(rw)

        self._tbl_lay.addStretch()

    def _build_heatmap(self, anom_cashier, all_dates):
        if not anom_cashier or not all_dates:
            self._heatmap.set_data([], [], {})
            return

        visible_dates = all_dates[-12:]
        cashier_list  = sorted(
            anom_cashier.keys(),
            key=lambda n: sum(anom_cashier[n].get(d, 0) for d in visible_dates),
            reverse=True
        )[:20]

        matrix = {}
        for ri, name in enumerate(cashier_list):
            for ci, ds in enumerate(visible_dates):
                v = anom_cashier[name].get(ds, 0)
                if v:
                    matrix[(ri, ci)] = v

        self._heatmap.set_data(
            cashier_list,
            [self._short_label(d) for d in visible_dates],
            matrix
        )

    def showEvent(self, e):
        super().showEvent(e)
        if self._first_show:
            self._first_show = False
            # Default to All Time so all historical data is visible immediately
            self._period_combo.blockSignals(True)
            self._period_combo.setCurrentIndex(4)   # "All Time"
            self._period_combo.blockSignals(False)
            self._from_input.clear()
            self._to_input.clear()
        self.refresh()


# ── .also() monkey-patch ──────────────────────────────────────────────────────

def _also(self, fn):
    fn(self); return self

try:
    QLabel.also
except AttributeError:
    QLabel.also = _also

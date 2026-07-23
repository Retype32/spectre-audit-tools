"""
pages/analytics_dashboard.py — Dashboard tab.

Visualises the currently-loaded report: transaction volume per cashier,
anomaly breakdown, discrepancy trend over time, and top cashiers by value.
All charts are drawn with PySide6's QPainter — no external charting lib needed.
"""
import logging
import os
import glob
import datetime

import pandas as pd

from PySide6.QtCore import Qt, QRectF, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QScrollArea, QSizePolicy, QGridLayout
)

from config import DISCREPANCY_DB_PATH, AMOUNT, LODGEMENT
from theme import Theme


# ── tiny palette of blue shades used in charts ──────────────────────────────
CHART_BLUES = ["#4d9fff", "#74b5ff", "#2d7dd6", "#93b8ff", "#a8c8ff",
               "#1a5fa8", "#60c8ff", "#3d7fff", "#b8d4ff", "#0e3d7a"]


def _section(text):
    l = QLabel(text)
    l.setStyleSheet(
        f"color:{Theme.TXT_DIM}; font-size:9.5px; font-weight:700; letter-spacing:2px;"
    )
    return l


def _card(title=""):
    f = QFrame()
    f.setStyleSheet(
        f"QFrame {{ background:{Theme.SURFACE}; border:1px solid {Theme.BORDER_S}; border-radius:8px; }}"
    )
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 14, 18, 16)
    lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setStyleSheet(f"color:{Theme.TXT}; font-size:12px; font-weight:600; letter-spacing:0.2px;")
        lay.addWidget(t)
        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div)
    return f, lay


# ── Bar chart widget ──────────────────────────────────────────────────────────
class BarChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []   # list of (label, value)
        self._color = Theme.ACCENT
        self._show_euro = True
        self._t = 1.0     # animation progress 0→1
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, data, color=None, show_euro=True):
        self._data = data[:12]   # cap at 12 bars
        self._show_euro = show_euro
        if color:
            self._color = color
        self._t = 0.0
        self._timer.start()

    def _tick(self):
        self._t = min(1.0, self._t + 0.07)
        self.update()
        if self._t >= 1.0:
            self._timer.stop()

    def paintEvent(self, e):
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        W, H = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 8, 8, 10, 36
        chart_w = W - pad_l - pad_r
        chart_h = H - pad_t - pad_b

        ease = self._t * self._t * (3 - 2 * self._t)  # smoothstep

        max_val = max(v for _, v in self._data) or 1
        n = len(self._data)
        bar_w = max(4, int(chart_w / n * 0.6))
        gap   = max(2, int(chart_w / n * 0.4))

        for i, (label, val) in enumerate(self._data):
            x = pad_l + i * (bar_w + gap)
            bh = int(chart_h * val / max_val * ease)
            y  = pad_t + chart_h - bh

            # bar fill
            color = QColor(CHART_BLUES[i % len(CHART_BLUES)])
            p.setBrush(QBrush(color))
            p.setPen(Qt.NoPen)
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, y, bar_w, max(1, bh)), 3, 3)
            p.drawPath(path)

            # label below
            p.setPen(QPen(QColor(Theme.TXT_3)))
            font = QFont(); font.setPointSize(7)
            p.setFont(font)
            lbl = label[:12] if len(label) > 12 else label
            p.drawText(x - 2, H - pad_b + 4, bar_w + 4, pad_b - 2,
                       Qt.AlignHCenter | Qt.AlignTop, lbl)

            # value on top — appears once bars are nearly at full height
            if ease >= 0.9:
                p.setPen(QPen(QColor(Theme.TXT_2)))
                font2 = QFont(); font2.setPointSize(7); font2.setBold(True)
                p.setFont(font2)
                val_str = (f"€{val:,.0f}" if val >= 100 else f"{val}") if self._show_euro else f"{val:,.0f}"
                p.drawText(x - 4, y - 16, bar_w + 8, 16,
                           Qt.AlignHCenter | Qt.AlignBottom, val_str)
        p.end()


# ── Line chart widget ─────────────────────────────────────────────────────────
class LineChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []   # list of (label, value)
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, data):
        self._data = data
        self.update()

    def paintEvent(self, e):
        if len(self._data) < 2:
            p = QPainter(self)
            p.setPen(QColor(Theme.TXT_3))
            p.drawText(self.rect(), Qt.AlignCenter, "Not enough history data yet")
            p.end()
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 12, 12, 16, 30

        max_v = max(v for _, v in self._data) or 1
        n = len(self._data)

        def pt(i, v):
            x = pad_l + int((W - pad_l - pad_r) * i / (n - 1))
            y = pad_t + int((H - pad_t - pad_b) * (1 - v / max_v))
            return x, y

        # filled area under line
        path = QPainterPath()
        x0, y0 = pt(0, self._data[0][1])
        path.moveTo(x0, H - pad_b)
        path.lineTo(x0, y0)
        for i, (_, v) in enumerate(self._data[1:], 1):
            xi, yi = pt(i, v)
            path.lineTo(xi, yi)
        xl, yl = pt(n - 1, self._data[-1][1])
        path.lineTo(xl, H - pad_b)
        path.closeSubpath()
        fill = QColor(Theme.ACCENT); fill.setAlpha(28)
        p.setBrush(QBrush(fill)); p.setPen(Qt.NoPen)
        p.drawPath(path)

        # line
        pen = QPen(QColor(Theme.ACCENT)); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        path2 = QPainterPath()
        x0, y0 = pt(0, self._data[0][1])
        path2.moveTo(x0, y0)
        for i, (_, v) in enumerate(self._data[1:], 1):
            xi, yi = pt(i, v)
            path2.lineTo(xi, yi)
        p.drawPath(path2)

        # dots + labels
        for i, (lbl, v) in enumerate(self._data):
            xi, yi = pt(i, v)
            p.setBrush(QBrush(QColor(Theme.ACCENT)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(xi - 3, yi - 3, 6, 6)
            p.setPen(QPen(QColor(Theme.TXT_3)))
            font = QFont(); font.setPointSize(7)
            p.setFont(font)
            p.drawText(xi - 20, H - pad_b + 3, 40, 20, Qt.AlignHCenter, lbl)
        p.end()


# ── Donut chart widget ────────────────────────────────────────────────────────
class DonutChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._slices = []  # list of (label, value, color)
        self.setFixedSize(200, 200)

    def set_data(self, slices):
        self._slices = [s for s in slices if s[1] > 0]
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W // 2, H // 2
        r_outer, r_inner = min(cx, cy) - 10, min(cx, cy) - 38

        if not self._slices:
            p.setPen(QColor(Theme.TXT_3))
            p.drawText(self.rect(), Qt.AlignCenter, "No data")
            p.end()
            return

        total = sum(v for _, v, _ in self._slices)
        angle = 90 * 16   # start at top
        for label, val, color in self._slices:
            span = int(360 * 16 * val / total)
            p.setBrush(QBrush(QColor(color)))
            p.setPen(Qt.NoPen)
            p.drawPie(cx - r_outer, cy - r_outer,
                      r_outer * 2, r_outer * 2, angle, span)
            angle += span

        # punch out centre
        p.setBrush(QBrush(QColor(Theme.ELEVATED)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(cx - r_inner, cy - r_inner, r_inner * 2, r_inner * 2)

        # centre label
        p.setPen(QColor(Theme.TXT))
        font = QFont(); font.setPointSize(9); font.setBold(True)
        p.setFont(font)
        p.drawText(cx - 30, cy - 10, 60, 20, Qt.AlignCenter, str(total))
        p.setPen(QColor(Theme.TXT_3))
        font2 = QFont(); font2.setPointSize(7)
        p.setFont(font2)
        p.drawText(cx - 30, cy + 4, 60, 16, Qt.AlignCenter, "anomalies")
        p.end()


# ── Main page ─────────────────────────────────────────────────────────────────
class DashboardPage(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._build()
        QTimer.singleShot(200, self.refresh)

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
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(20)
        root.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self._root_layout = root

        # ── Summary stat row ─────────────────────────────────────────
        self._stat_row = QHBoxLayout(); self._stat_row.setSpacing(12)
        self._stat_widgets = {}
        for key, label in [("rows","Transactions"),("cashiers","Cashiers"),
                            ("value","Total Value"),("slips","Total Slips"),
                            ("anomalies","Anomalies Found")]:
            sf = QFrame()
            sf.setStyleSheet(
                f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER};"
                f"border-radius:8px;}}"
            )
            sl = QVBoxLayout(sf); sl.setContentsMargins(16,12,16,12); sl.setSpacing(4)
            v = QLabel("—"); v.setStyleSheet(
                f"color:{Theme.ACCENT};font-size:22px;font-weight:700;"
                f"font-family:Consolas,monospace;letter-spacing:-0.5px;"
            )
            k = QLabel(label); k.setStyleSheet(
                f"color:{Theme.TXT_3};font-size:9px;font-weight:700;letter-spacing:1.5px;"
            )
            sl.addWidget(v); sl.addWidget(k)
            self._stat_widgets[key] = v
            self._stat_row.addWidget(sf)
        root.addLayout(self._stat_row)

        # ── Row 1: Volume bar + Anomaly donut ────────────────────────
        row1 = QHBoxLayout(); row1.setSpacing(12)

        vol_card, vol_lay = _card()   # no pre-built title — we build a custom title row
        _tr = QHBoxLayout(); _tr.setSpacing(8)
        self._bar_title = QLabel("Transaction Volume  —  Top Cashiers by Value")
        self._bar_title.setStyleSheet(
            f"color:{Theme.TXT};font-size:12px;font-weight:600;letter-spacing:0.2px;"
        )
        _tr.addWidget(self._bar_title); _tr.addStretch()
        self._bar_mode    = "value"
        self._bar_toggles = {}
        for _mode, _lbl in [("value", "By Value"), ("slips", "By Slips")]:
            _b = QPushButton(_lbl)
            _b.setFixedHeight(22); _b.setFixedWidth(72)
            _b.clicked.connect(lambda _=False, m=_mode: self._set_bar_mode(m))
            _tr.addWidget(_b)
            self._bar_toggles[_mode] = _b
        _div = QFrame(); _div.setFixedHeight(1)
        _div.setStyleSheet(f"background:{Theme.BORDER_S};")
        vol_lay.addLayout(_tr)
        vol_lay.addWidget(_div)
        self._bar_chart = BarChart()
        vol_lay.addWidget(self._bar_chart)
        self._update_bar_toggle_style()
        row1.addWidget(vol_card, 3)

        ano_card, ano_lay = _card("Anomaly Breakdown")
        self._donut = DonutChart()
        ano_lay.addWidget(self._donut, 0, Qt.AlignHCenter)
        self._legend = QVBoxLayout(); self._legend.setSpacing(3)
        ano_lay.addLayout(self._legend)
        row1.addWidget(ano_card, 2)

        root.addLayout(row1)

        # ── Row 2: Discrepancy trend + Top 5 table ───────────────────
        row2 = QHBoxLayout(); row2.setSpacing(12)

        trend_card, trend_lay = _card("Discrepancy Events — Monthly Trend")
        self._line_chart = LineChart()
        trend_lay.addWidget(self._line_chart)
        row2.addWidget(trend_card, 3)

        top5_card, top5_lay = _card("Top 5 Cashiers  —  Highest Value Processed")
        self._top5_lay = top5_lay
        row2.addWidget(top5_card, 2)

        root.addLayout(row2)

        self._no_data_lbl = QLabel(
            "No report loaded.  Go to  Integrity Check → Import Report  to populate the dashboard."
        )
        self._no_data_lbl.setAlignment(Qt.AlignCenter)
        self._no_data_lbl.setStyleSheet(
            f"color:{Theme.TXT_3}; font-size:13px; padding:40px;"
        )
        root.addWidget(self._no_data_lbl)
        _attach_summary_stats(self)

    # ── refresh ──────────────────────────────────────────────────────────────
    def refresh(self):
        df = getattr(self.app, "active_df", None)
        has_data = df is not None and not df.empty

        self._no_data_lbl.setVisible(not has_data)

        if not has_data:
            for v in self._stat_widgets.values():
                v.setText("—")
            return

        try:
            # Summary stats
            n_rows   = len(df)
            n_cash   = df["Cashier Name"].nunique() if "Cashier Name" in df.columns else 0
            total_v  = df[AMOUNT].sum() if AMOUNT in df.columns else 0
            n_anom   = (len(getattr(self.app,"_exact_dup_rows",[])) +
                        len(getattr(self.app,"_sus_rows",[])) +
                        len(getattr(self.app,"_shared_wallet_rows",[])))

            n_slips = df[LODGEMENT].nunique() if LODGEMENT in df.columns else n_rows

            self._stat_widgets["rows"].setText(f"{n_rows:,}")
            self._stat_widgets["cashiers"].setText(str(n_cash))
            self._stat_widgets["value"].setText(f"€{total_v:,.0f}")
            self._stat_widgets["slips"].setText(f"{n_slips:,}")
            self._stat_widgets["anomalies"].setText(str(n_anom))

            # Bar chart — respects current toggle mode
            self._set_bar_mode(self._bar_mode)

            # Donut — anomaly breakdown
            n_dup    = len(getattr(self.app,"_exact_dup_rows",[]))
            n_sus    = len(getattr(self.app,"_sus_rows",[]))
            n_shared = len(getattr(self.app,"_shared_wallet_rows",[]))
            slices = [
                ("High Risk",  n_dup,    CHART_BLUES[0]),
                ("Suspicious", n_sus,    CHART_BLUES[3]),
                ("Shared",     n_shared, CHART_BLUES[6]),
            ]
            self._donut.set_data(slices)
            # rebuild legend
            while self._legend.count():
                item = self._legend.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            for label, val, color in slices:
                row = QHBoxLayout(); row.setSpacing(6)
                dot = QFrame(); dot.setFixedSize(10,10)
                dot.setStyleSheet(f"background:{color};border-radius:5px;")
                lbl = QLabel(f"{label}: {val}")
                lbl.setStyleSheet(f"color:{Theme.TXT_2};font-size:11px;")
                row.addWidget(dot); row.addWidget(lbl); row.addStretch()
                self._legend.addLayout(row)

            # Line chart — monthly discrepancy trend
            self._load_trend()

            # Top 5
            while self._top5_lay.count() > 2:   # keep title + divider
                item = self._top5_lay.takeAt(self._top5_lay.count()-1)
                if item.widget(): item.widget().deleteLater()
            if "Cashier Name" in df.columns and AMOUNT in df.columns:
                top5 = (df.groupby("Cashier Name")[AMOUNT]
                          .sum().sort_values(ascending=False).head(5))
                max_v = top5.max() or 1
                for rank, (name, val) in enumerate(top5.items(), 1):
                    row_w = QWidget()
                    row_w.setStyleSheet("background:transparent;")
                    rl = QVBoxLayout(row_w); rl.setContentsMargins(0,4,0,4); rl.setSpacing(3)
                    top_r = QHBoxLayout()
                    lbl = QLabel(f"{rank}. {self._short_name(name)}")
                    lbl.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:500;")
                    amt = QLabel(f"€{val:,.2f}")
                    amt.setStyleSheet(
                        f"color:{Theme.ACCENT};font-size:12px;font-weight:700;"
                        f"font-family:Consolas,monospace;"
                    )
                    top_r.addWidget(lbl); top_r.addStretch(); top_r.addWidget(amt)
                    rl.addLayout(top_r)
                    # mini bar
                    bar_bg = QFrame(); bar_bg.setFixedHeight(4)
                    bar_bg.setStyleSheet(f"background:{Theme.BORDER};border-radius:2px;")
                    bar_inner = QFrame(bar_bg); bar_inner.setFixedHeight(4)
                    pct = int(val / max_v * 100)
                    bar_inner.setStyleSheet(
                        f"background:{CHART_BLUES[rank-1]};border-radius:2px;"
                    )
                    bar_inner.setFixedWidth(max(4, int(bar_bg.sizeHint().width() * pct / 100)))
                    rl.addWidget(bar_bg)
                    self._top5_lay.addWidget(row_w)
        except Exception:
            logging.exception("Unhandled exception")

        if has_data:
            _refresh_summary_stats(self)

    def _update_bar_toggle_style(self):
        for mode, btn in self._bar_toggles.items():
            active = (mode == self._bar_mode)
            btn.setStyleSheet(
                f"QPushButton{{background:{Theme.ACCENT if active else Theme.ELEVATED};"
                f"color:{'white' if active else Theme.TXT_3};"
                f"border:1px solid {Theme.ACCENT if active else Theme.BORDER};"
                f"border-radius:4px;font-size:10px;font-weight:600;padding:0;}}"
                f"QPushButton:hover{{color:{'white' if active else Theme.TXT_2};}}"
            )

    @staticmethod
    def _short_name(name):
        """Return 'FirstName L' format so bar labels fit the chart width."""
        parts = str(name).strip().split()
        if len(parts) >= 2:
            return f"{parts[0]} {parts[-1][0]}"
        return str(name)

    def _fade_label(self, label, text):
        label.setText(text)
        if not hasattr(label, '_fade_fx'):
            label._fade_fx = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(label._fade_fx)
        label._fade_fx.setOpacity(0.0)
        if getattr(label, '_fade_anim', None):
            label._fade_anim.stop()
        label._fade_anim = QPropertyAnimation(label._fade_fx, b"opacity")
        label._fade_anim.setDuration(200)
        label._fade_anim.setStartValue(0.0)
        label._fade_anim.setEndValue(1.0)
        label._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        label._fade_anim.start()

    def _set_bar_mode(self, mode):
        self._bar_mode = mode
        self._update_bar_toggle_style()
        df = getattr(self.app, "active_df", None)
        if df is None or df.empty or "Cashier Name" not in df.columns:
            return
        if mode == "value":
            self._fade_label(self._bar_title,
                             "Transaction Volume  —  Top Cashiers by Value")
            if AMOUNT in df.columns:
                grp = (df.groupby("Cashier Name")[AMOUNT]
                         .sum().sort_values(ascending=False).head(12))
                labels = [self._short_name(n) for n in grp.index]
                self._bar_chart.set_data(list(zip(labels, grp.values)))
        else:
            self._fade_label(self._bar_title,
                             "Transaction Volume  —  Top Cashiers by Slip Count")
            grp = df.groupby("Cashier Name").size().sort_values(ascending=False).head(12)
            labels = [self._short_name(n) for n in grp.index]
            self._bar_chart.set_data(list(zip(labels, grp.values.astype(float))),
                                     color=Theme.GOLD, show_euro=False)

    def _load_trend(self):
        try:
            pattern = os.path.join(DISCREPANCY_DB_PATH, "**", "*.xlsx")
            files   = glob.glob(pattern, recursive=True)
            if not files:
                self._line_chart.set_data([])
                return
            monthly = {}
            for fp in files:
                try:
                    tmp = pd.read_excel(fp)
                    # Sum actual Small_Discrepancies events, not row count
                    if "Small_Discrepancies" in tmp.columns:
                        tmp["Small_Discrepancies"] = pd.to_numeric(
                            tmp["Small_Discrepancies"], errors="coerce"
                        ).fillna(0)
                        events = int(tmp["Small_Discrepancies"].sum())
                    else:
                        events = len(tmp)
                    if "Report_Date" in tmp.columns:
                        for rd in tmp["Report_Date"].dropna().unique():
                            try:
                                dt = pd.to_datetime(str(rd), dayfirst=True)
                                key = dt.strftime("%b %y")
                                monthly[key] = monthly.get(key, 0) + events
                            except Exception:
                                pass
                    else:
                        parts = fp.replace("\\", "/").split("/")
                        try:
                            key = datetime.date(int(parts[-3]), int(parts[-2]), 1).strftime("%b %y")
                        except Exception:
                            key = os.path.basename(os.path.dirname(fp))
                        monthly[key] = monthly.get(key, 0) + events
                except Exception:
                    pass
            if monthly:
                def _ms(k):
                    try: return datetime.datetime.strptime(k, "%b %y")
                    except: return datetime.datetime.min
                items = sorted(monthly.items(), key=lambda x: _ms(x[0]))[-12:]
                self._line_chart.set_data(items)
        except Exception:
            logging.exception("Unhandled exception")

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()


# =============================================================================
# Summary Statistics section — appended to DashboardPage at runtime
# =============================================================================

class HistogramWidget(QWidget):
    """Simple histogram of transaction value distribution."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bins  = []   # list of (bin_start, count)
        self._max_c = 1
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, values):
        import math
        if not values:
            self._bins = []; self.update(); return
        lo, hi = min(values), max(values)
        if lo == hi:
            self._bins = [(lo, len(values))]; self._max_c = len(values)
            self.update(); return
        n_bins = min(20, max(5, int(math.sqrt(len(values)))))
        width  = (hi - lo) / n_bins
        counts = [0] * n_bins
        for v in values:
            idx = min(int((v - lo) / width), n_bins - 1)
            counts[idx] += 1
        self._bins  = [(lo + i * width, counts[i]) for i in range(n_bins)]
        self._max_c = max(counts) or 1
        self.update()

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath
        from PySide6.QtCore import Qt, QRectF
        if not self._bins:
            return
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        pl, pr, pt, pb = 8, 8, 8, 24
        cw = W - pl - pr; ch = H - pt - pb
        n  = len(self._bins)
        bw = max(2, int(cw / n * 0.8))
        gp = max(1, int(cw / n * 0.2))
        for i, (val, cnt) in enumerate(self._bins):
            x  = pl + i * (bw + gp)
            bh = int(ch * cnt / self._max_c)
            y  = pt + ch - bh
            color = QColor(CHART_BLUES[i % len(CHART_BLUES)])
            color.setAlpha(200)
            p.setBrush(QBrush(color)); p.setPen(Qt.NoPen)
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, y, bw, bh), 2, 2)
            p.drawPath(path)
            if i % max(1, n // 5) == 0:
                p.setPen(QPen(QColor(Theme.TXT_3)))
                from PySide6.QtGui import QFont
                f = QFont(); f.setPointSize(7); p.setFont(f)
                lbl = f"€{val:,.0f}"
                p.drawText(x - 10, H - pb + 3, bw + 20, pb - 2,
                           0x0004 | 0x0080, lbl)  # AlignHCenter|AlignTop
        p.end()


def _attach_summary_stats(dashboard_page):
    """
    Builds the Summary Statistics card and attaches it to an existing
    DashboardPage's scroll root layout, right after the no-data label.
    Called once from DashboardPage._build().
    """
    root = dashboard_page._root_layout

    sec = QLabel("SUMMARY STATISTICS")
    sec.setStyleSheet(
        f"color:{Theme.TXT_DIM};font-size:9.5px;font-weight:700;letter-spacing:2px;"
    )
    root.insertWidget(root.count() - 1, sec)   # before addStretch if any

    stats_card = QFrame()
    stats_card.setStyleSheet(
        f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
    )
    cl = QVBoxLayout(stats_card); cl.setContentsMargins(18, 14, 18, 16); cl.setSpacing(12)

    title_r = QHBoxLayout()
    t = QLabel("Transaction Value Distribution")
    t.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:600;")
    title_r.addWidget(t); title_r.addStretch()
    cl.addLayout(title_r)
    div = QFrame(); div.setFixedHeight(1)
    div.setStyleSheet(f"background:{Theme.BORDER_S};"); cl.addWidget(div)

    # Stat pills row
    pill_row = QHBoxLayout(); pill_row.setSpacing(8)
    dashboard_page._stat_pills = {}
    for key, label in [("mean","Mean"),("median","Median"),("std","Std Dev"),
                        ("min","Min"),("max","Max"),("p95","95th pct")]:
        pf = QFrame()
        pf.setStyleSheet(
            f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER};"
            f"border-radius:6px;}}"
        )
        pl2 = QVBoxLayout(pf); pl2.setContentsMargins(12,8,12,8); pl2.setSpacing(2)
        vl = QLabel("—")
        vl.setStyleSheet(
            f"color:{Theme.ACCENT};font-size:14px;font-weight:700;"
            f"font-family:Consolas,monospace;"
        )
        kl = QLabel(label)
        kl.setStyleSheet(f"color:{Theme.TXT_3};font-size:9px;font-weight:700;letter-spacing:1px;")
        pl2.addWidget(vl); pl2.addWidget(kl)
        dashboard_page._stat_pills[key] = vl
        pill_row.addWidget(pf)
    cl.addLayout(pill_row)

    # Histogram
    dashboard_page._histogram = HistogramWidget()
    cl.addWidget(dashboard_page._histogram)

    root.insertWidget(root.count() - 1, stats_card)
    dashboard_page._stats_card = stats_card


def _refresh_summary_stats(dashboard_page):
    """Called from DashboardPage.refresh() to update the stats section."""
    df = getattr(dashboard_page.app, "active_df", None)
    if df is None or df.empty or AMOUNT not in df.columns:
        for v in dashboard_page._stat_pills.values():
            v.setText("—")
        dashboard_page._histogram.set_data([])
        return
    vals = df[AMOUNT].dropna().tolist()
    if not vals:
        return
    pills = dashboard_page._stat_pills
    pills["mean"].setText(f"€{sum(vals)/len(vals):,.2f}")
    s = sorted(vals); n = len(s)
    median = s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2
    pills["median"].setText(f"€{median:,.2f}")
    mean = sum(vals)/len(vals)
    std  = (sum((v-mean)**2 for v in vals)/len(vals))**0.5
    pills["std"].setText(f"€{std:,.2f}")
    pills["min"].setText(f"€{min(vals):,.2f}")
    pills["max"].setText(f"€{max(vals):,.2f}")
    p95_idx = int(0.95 * n)
    pills["p95"].setText(f"€{s[min(p95_idx, n-1)]:,.2f}")
    dashboard_page._histogram.set_data(vals)

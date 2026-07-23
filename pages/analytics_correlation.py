"""
pages/analytics_correlation.py — Correlation Explorer tab.

Scatter plot + correlation coefficient between any two numeric columns.
Answers questions like: does transaction volume correlate with anomaly rate?
Does amount processed correlate with discrepancy count?
"""
import logging
import math

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QComboBox, QScrollArea, QSizePolicy
)

from config import AMOUNT, OPERATOR
from theme import Theme


class ScatterPlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []    # list of (x, y, label)
        self._x_label = ""
        self._y_label = ""
        self._corr    = None
        self.setMinimumHeight(320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, points, x_label, y_label, corr):
        self._points  = points
        self._x_label = x_label
        self._y_label = y_label
        self._corr    = corr
        self.update()

    def paintEvent(self, e):
        if not self._points:
            p = QPainter(self)
            p.setPen(QColor(Theme.TXT_3))
            p.drawText(self.rect(), Qt.AlignCenter, "Select two columns and click Compute")
            p.end(); return

        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        pl, pr, pt, pb = 60, 20, 20, 50

        xs = [pt[0] for pt in self._points]
        ys = [pt[1] for pt in self._points]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        x_rng = (x_max - x_min) or 1
        y_rng = (y_max - y_min) or 1

        def to_screen(x, y):
            sx = pl + int((x - x_min) / x_rng * (W - pl - pr))
            sy = pt + int((1 - (y - y_min) / y_rng) * (H - pt - pb))
            return sx, sy

        # Grid lines
        p.setPen(QPen(QColor(Theme.BORDER_S)))
        for i in range(5):
            gx = pl + int(i / 4 * (W - pl - pr))
            gy = pt + int(i / 4 * (H - pt - pb))
            p.drawLine(gx, pt, gx, H - pb)
            p.drawLine(pl, gy, W - pr, gy)

        # Trend line (linear regression)
        n = len(xs)
        if n >= 2:
            mx = sum(xs)/n; my = sum(ys)/n
            num = sum((xs[i]-mx)*(ys[i]-my) for i in range(n))
            den = sum((xs[i]-mx)**2 for i in range(n)) or 1
            slope = num / den
            intercept = my - slope * mx
            x0, x1 = x_min, x_max
            y0 = slope * x0 + intercept
            y1 = slope * x1 + intercept
            sx0, sy0 = to_screen(x0, y0)
            sx1, sy1 = to_screen(x1, y1)
            pen = QPen(QColor(Theme.ACCENT)); pen.setWidth(2)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawLine(sx0, sy0, sx1, sy1)

        # Points
        for x, y, lbl in self._points:
            sx, sy = to_screen(x, y)
            p.setBrush(QBrush(QColor(Theme.ACCENT)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(sx-4, sy-4, 8, 8)

        # Axis labels
        f = QFont(); f.setPointSize(8)
        p.setFont(f); p.setPen(QColor(Theme.TXT_3))
        p.drawText(pl, H-pb+6, W-pl-pr, pb-6, Qt.AlignHCenter, self._x_label[:30])

        # Y axis label (rotated)
        p.save()
        p.translate(12, pt + (H-pt-pb)//2)
        p.rotate(-90)
        p.drawText(-60, -4, 120, 16, Qt.AlignCenter, self._y_label[:20])
        p.restore()

        # Axis tick values
        f2 = QFont(); f2.setPointSize(7); p.setFont(f2)
        for i in range(5):
            frac = i / 4
            xv   = x_min + frac * x_rng
            yv   = y_min + frac * y_rng
            gx   = pl + int(frac * (W-pl-pr))
            gy   = pt + int((1-frac) * (H-pt-pb))
            p.drawText(gx-20, H-pb+2, 40, 12, Qt.AlignCenter,
                       f"{xv:,.0f}" if xv >= 100 else f"{xv:.1f}")
            p.drawText(2, gy-6, pl-4, 12, Qt.AlignRight | Qt.AlignVCenter,
                       f"{yv:,.0f}" if yv >= 100 else f"{yv:.1f}")

        # Correlation badge
        if self._corr is not None:
            strength = abs(self._corr)
            color = (Theme.OK if strength > 0.7 else
                     Theme.WARN if strength > 0.4 else Theme.TXT_3)
            badge = f"r = {self._corr:+.3f}"
            p.setPen(QColor(color))
            bf = QFont(); bf.setPointSize(9); bf.setBold(True); p.setFont(bf)
            p.drawText(W-120, pt+4, 100, 20, Qt.AlignRight, badge)
        p.end()


class CorrelationPage(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        root = QVBoxLayout(inner)
        root.setContentsMargins(24,20,24,24); root.setSpacing(20)
        root.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner); outer.addWidget(scroll)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Correlation Explorer")
        title.setStyleSheet(f"color:{Theme.TXT};font-size:18px;font-weight:700;")
        hdr.addWidget(title); hdr.addStretch()
        root.addLayout(hdr)

        sub = QLabel(
            "Visualises the relationship between any two numeric variables. "
            "The r value (Pearson correlation) ranges from -1 (perfect negative) "
            "to +1 (perfect positive). Values above 0.7 or below -0.7 are strong correlations."
        )
        sub.setStyleSheet(f"color:{Theme.TXT_3};font-size:12px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # ── Suggested correlation combinations card ────────────────────
        sug_card = QFrame()
        sug_card.setStyleSheet(
            f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
        )
        sug_lay = QVBoxLayout(sug_card); sug_lay.setContentsMargins(20,14,20,16); sug_lay.setSpacing(10)
        sug_title_row = QHBoxLayout()
        sug_t = QLabel("★  Suggested Correlations to Watch")
        sug_t.setStyleSheet(f"color:{Theme.GOLD};font-size:12px;font-weight:700;")
        sug_title_row.addWidget(sug_t); sug_title_row.addStretch()
        sug_lay.addLayout(sug_title_row)
        div0 = QFrame(); div0.setFixedHeight(1); div0.setStyleSheet(f"background:{Theme.BORDER_S};")
        sug_lay.addWidget(div0)

        SUGGESTIONS = [
            (
                "Cashier: Txn Count",
                "Cashier: Anomaly Count",
                "Transaction Volume vs Anomaly Count",
                "Does a higher number of transactions lead to more flagged duplicates? "
                "A strong positive correlation here may indicate systematic fraud rather than "
                "incidental errors — high-volume cashiers with proportionally high anomalies warrant scrutiny."
            ),
            (
                "Cashier: Total Value",
                "Cashier: Anomaly Count",
                "Total Value Processed vs Anomaly Count",
                "Correlating total money handled with duplicate flags can expose cashiers who "
                "exploit high-value sessions to slip through duplicate transactions undetected."
            ),
            (
                "Cashier: Txn Count",
                "Cashier: Avg Amount",
                "Transaction Count vs Average Amount per Transaction",
                "A negative correlation here (more transactions = lower average value) is normal. "
                "A positive or flat correlation can indicate a cashier is processing unusually "
                "large individual amounts — potentially splitting or inflating transactions."
            ),
        ]

        for x_col, y_col, label, description in SUGGESTIONS:
            sug_row = QFrame()
            sug_row.setStyleSheet(
                f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER};"
                f"border-radius:6px;}}"
            )
            sr_lay = QHBoxLayout(sug_row); sr_lay.setContentsMargins(14,10,14,10); sr_lay.setSpacing(14)

            star = QLabel("★")
            star.setStyleSheet(f"color:{Theme.GOLD};font-size:14px;font-weight:700;")
            sr_lay.addWidget(star)

            text_lay = QVBoxLayout(); text_lay.setSpacing(2)
            lbl_w = QLabel(label)
            lbl_w.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:600;")
            det_w = QLabel(description)
            det_w.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
            det_w.setWordWrap(True)
            pair_lbl = QLabel(f"{x_col}  ×  {y_col}")
            pair_lbl.setStyleSheet(
                f"color:{Theme.ACCENT};font-size:10px;font-family:Consolas,monospace;"
            )
            text_lay.addWidget(lbl_w); text_lay.addWidget(pair_lbl); text_lay.addWidget(det_w)
            sr_lay.addLayout(text_lay, 1)

            load_btn = QPushButton("Load →")
            load_btn.setFixedHeight(28); load_btn.setMinimumWidth(70)
            load_btn.setStyleSheet(
                f"QPushButton{{background:{Theme.ACCENT};color:white;"
                f"border:none;border-radius:4px;font-size:10px;font-weight:600;padding:0 10px;}}"
                f"QPushButton:hover{{background:#5aafff;}}"
            )
            _x, _y = x_col, y_col
            load_btn.clicked.connect(lambda _=False, xc=_x, yc=_y: self._load_suggestion(xc, yc))
            sr_lay.addWidget(load_btn)

            sug_lay.addWidget(sug_row)

        root.addWidget(sug_card)

        # Controls card
        ctrl = QFrame()
        ctrl.setStyleSheet(
            f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
        )
        cl = QVBoxLayout(ctrl); cl.setContentsMargins(20,16,20,18); cl.setSpacing(14)

        axes_row = QHBoxLayout(); axes_row.setSpacing(16)
        for label, attr in [("X Axis  (independent variable)", "_x_combo"),
                             ("Y Axis  (dependent variable)",  "_y_combo")]:
            col_lay = QVBoxLayout(); col_lay.setSpacing(6)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{Theme.TXT_2};font-size:11px;font-weight:600;")
            combo = QComboBox(); combo.setMinimumWidth(240)
            combo.addItem("(load a report first)")
            col_lay.addWidget(lbl); col_lay.addWidget(combo)
            setattr(self, attr, combo)
            axes_row.addLayout(col_lay)
        axes_row.addStretch()
        cl.addLayout(axes_row)

        btn_row = QHBoxLayout()
        self._compute_btn = QPushButton("Compute Correlation")
        self._compute_btn.setObjectName("primary")
        self._compute_btn.setFixedHeight(36); self._compute_btn.setMinimumWidth(180)
        self._compute_btn.clicked.connect(self.compute)
        btn_row.addWidget(self._compute_btn); btn_row.addStretch()
        cl.addLayout(btn_row)
        root.addWidget(ctrl)

        # Result interpretation
        self._interp_card = QFrame()
        self._interp_card.setStyleSheet(
            f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
        )
        il = QVBoxLayout(self._interp_card); il.setContentsMargins(20,14,20,16); il.setSpacing(6)
        self._interp_lbl = QLabel("")
        self._interp_lbl.setStyleSheet(f"color:{Theme.TXT};font-size:13px;")
        self._interp_lbl.setWordWrap(True)
        self._interp_sub = QLabel("")
        self._interp_sub.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
        self._interp_sub.setWordWrap(True)
        il.addWidget(self._interp_lbl); il.addWidget(self._interp_sub)
        self._interp_card.setVisible(False)
        root.addWidget(self._interp_card)

        # Scatter plot
        plot_card = QFrame()
        plot_card.setStyleSheet(
            f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
        )
        pl2 = QVBoxLayout(plot_card); pl2.setContentsMargins(16,14,16,16); pl2.setSpacing(8)
        self._scatter = ScatterPlot()
        pl2.addWidget(self._scatter)
        root.addWidget(plot_card)

        # Correlation matrix of all numeric cols
        matrix_card = QFrame()
        matrix_card.setStyleSheet(
            f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
        )
        ml = QVBoxLayout(matrix_card); ml.setContentsMargins(20,14,20,18); ml.setSpacing(10)
        mt = QLabel("Correlation Matrix  —  all numeric columns")
        mt.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:600;")
        ml.addWidget(mt)
        div = QFrame(); div.setFixedHeight(1); div.setStyleSheet(f"background:{Theme.BORDER_S};")
        ml.addWidget(div)
        self._matrix_lay = QVBoxLayout(); self._matrix_lay.setSpacing(3)
        ml.addLayout(self._matrix_lay)
        root.addWidget(matrix_card)

        self._no_data = QLabel("No report loaded. Import a report in Integrity Check first.")
        self._no_data.setAlignment(Qt.AlignCenter)
        self._no_data.setStyleSheet(f"color:{Theme.TXT_3};font-size:13px;padding:40px;")
        root.addWidget(self._no_data)

    def _load_suggestion(self, x_col, y_col):
        """Load a suggested correlation pair into the combo boxes and compute."""
        self._populate_combos()
        # Set combos if options are available
        for i in range(self._x_combo.count()):
            if self._x_combo.itemText(i) == x_col:
                self._x_combo.setCurrentIndex(i)
                break
        for i in range(self._y_combo.count()):
            if self._y_combo.itemText(i) == y_col:
                self._y_combo.setCurrentIndex(i)
                break
        self.compute()

    def _populate_combos(self):
        df = getattr(self.app, "active_df", None)
        if df is None:
            return
        num_cols = df.select_dtypes(include='number').columns.tolist()
        # Also add per-cashier aggregated metrics
        extra = []
        if "Cashier Name" in df.columns and AMOUNT in df.columns:
            extra = ["Cashier: Txn Count", "Cashier: Total Value",
                     "Cashier: Avg Amount", "Cashier: Anomaly Count"]
        all_opts = num_cols + extra
        for combo in [self._x_combo, self._y_combo]:
            cur = combo.currentText()
            combo.clear()
            for opt in all_opts:
                combo.addItem(opt)
            if cur in all_opts:
                combo.setCurrentText(cur)
        self._no_data.setVisible(False)

    def _get_series(self, col_name):
        """Returns a (labels, values) pair for a given column name or derived metric."""
        df = getattr(self.app, "active_df", None)
        if df is None: return [], []

        if col_name.startswith("Cashier: ") and "Cashier Name" in df.columns:
            grp = df.groupby("Cashier Name")
            metric = col_name.replace("Cashier: ", "")
            if metric == "Txn Count":
                s = grp.size()
            elif metric == "Total Value" and AMOUNT in df.columns:
                s = grp[AMOUNT].sum()
            elif metric == "Avg Amount" and AMOUNT in df.columns:
                s = grp[AMOUNT].mean()
            elif metric == "Anomaly Count":
                counts = {}
                for rd in getattr(self.app,"_exact_dup_rows",[]) + getattr(self.app,"_sus_rows",[]):
                    n = rd.get("Cashier Name", rd.get("Cashier",""))
                    counts[n] = counts.get(n,0)+1
                s = pd.Series(counts)
                # align to all cashiers
                all_names = df["Cashier Name"].unique()
                s = s.reindex(all_names, fill_value=0)
            else:
                return [], []
            return list(s.index), list(s.values)
        elif col_name in df.columns:
            vals = df[col_name].dropna()
            return list(range(len(vals))), list(vals)
        return [], []

    def compute(self):
        try:
            x_col = self._x_combo.currentText()
            y_col = self._y_combo.currentText()
            if x_col == y_col:
                return

            # Get per-cashier aligned series if both are cashier metrics
            if x_col.startswith("Cashier: ") and y_col.startswith("Cashier: "):
                lx, vx = self._get_series(x_col)
                ly, vy = self._get_series(y_col)
                # align by cashier name
                dx = dict(zip(lx, vx))
                dy = dict(zip(ly, vy))
                common = [n for n in dx if n in dy]
                vx2 = [dx[n] for n in common]
                vy2 = [dy[n] for n in common]
                points = list(zip(vx2, vy2, common))
            else:
                _, vx2 = self._get_series(x_col)
                _, vy2 = self._get_series(y_col)
                mn = min(len(vx2), len(vy2))
                vx2, vy2 = vx2[:mn], vy2[:mn]
                points = list(zip(vx2, vy2, [""]*mn))

            if len(points) < 3:
                return

            xs = [pt[0] for pt in points]
            ys = [pt[1] for pt in points]
            n  = len(xs)
            mx = sum(xs)/n; my = sum(ys)/n
            num = sum((xs[i]-mx)*(ys[i]-my) for i in range(n))
            dx2 = sum((xs[i]-mx)**2 for i in range(n))
            dy2 = sum((ys[i]-my)**2 for i in range(n))
            denom = math.sqrt(dx2 * dy2)
            corr = num/denom if denom else 0.0

            self._scatter.set_data(points, x_col, y_col, corr)

            # Interpretation
            strength = abs(corr)
            direction = "positive" if corr > 0 else "negative"
            if strength > 0.7:
                desc = f"Strong {direction} correlation (r = {corr:+.3f})"
                detail = (f"As {x_col} increases, {y_col} tends to "
                          f"{'increase' if corr>0 else 'decrease'} significantly. "
                          f"This relationship is statistically meaningful.")
            elif strength > 0.4:
                desc = f"Moderate {direction} correlation (r = {corr:+.3f})"
                detail = (f"There is a moderate tendency for {y_col} to "
                          f"{'increase' if corr>0 else 'decrease'} with {x_col}, "
                          f"but the relationship is not consistent.")
            else:
                desc = f"Weak or no correlation (r = {corr:+.3f})"
                detail = (f"No meaningful linear relationship detected between "
                          f"{x_col} and {y_col}.")
            self._interp_lbl.setText(desc)
            self._interp_sub.setText(detail)
            self._interp_card.setVisible(True)

            # Correlation matrix
            self._build_matrix()

        except Exception:
            logging.exception("Unhandled exception")

    def _build_matrix(self):
        while self._matrix_lay.count():
            item = self._matrix_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        df = getattr(self.app, "active_df", None)
        if df is None: return
        num_cols = df.select_dtypes(include='number').columns.tolist()[:6]
        if len(num_cols) < 2: return

        corr_df = df[num_cols].corr()

        # Header row
        hdr = QHBoxLayout(); hdr.setSpacing(4)
        hdr.addWidget(QLabel("").also(lambda l: l.setFixedWidth(110)), 0)
        for col in num_cols:
            lbl = QLabel(str(col)[:10])
            lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:9px;font-weight:700;letter-spacing:1px;")
            lbl.setAlignment(Qt.AlignCenter)
            hdr.addWidget(lbl, 1)
        self._matrix_lay.addLayout(hdr)

        for row_col in num_cols:
            row = QHBoxLayout(); row.setSpacing(4)
            rl = QLabel(str(row_col)[:14])
            rl.setStyleSheet(f"color:{Theme.TXT_2};font-size:10px;")
            rl.setFixedWidth(110)
            row.addWidget(rl, 0)
            for col in num_cols:
                val = corr_df.loc[row_col, col]
                strength = abs(val)
                is_diag  = (row_col == col)
                if is_diag:
                    bg, txt = Theme.ELEVATED, Theme.TXT_3
                elif strength > 0.7:
                    bg = "#162440" if val > 0 else "#1a0e28"
                    txt = Theme.ACCENT if val > 0 else Theme.PURPLE
                elif strength > 0.4:
                    bg = "#0e1a30"
                    txt = Theme.TXT_2
                else:
                    bg = Theme.SURFACE
                    txt = Theme.TXT_DIM
                cell = QLabel("1.00" if is_diag else f"{val:+.2f}")
                cell.setAlignment(Qt.AlignCenter)
                cell.setStyleSheet(
                    f"background:{bg};color:{txt};font-size:10px;"
                    f"font-family:Consolas,monospace;font-weight:{'700' if strength>0.7 and not is_diag else '400'};"
                    f"border-radius:4px;padding:4px 2px;"
                )
                row.addWidget(cell, 1)
            self._matrix_lay.addLayout(row)

    def showEvent(self, e):
        super().showEvent(e)
        self._populate_combos()
        # Auto-load first suggested correlation when a report is freshly loaded
        df = getattr(self.app, "active_df", None)
        if df is not None and not df.empty:
            self._load_suggestion(
                "Cashier: Txn Count",
                "Cashier: Anomaly Count"
            )


# Monkey-patch helper
def _also(self, fn):
    fn(self); return self
try:
    QLabel.also
except AttributeError:
    QLabel.also = _also

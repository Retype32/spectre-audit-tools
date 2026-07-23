"""
pages/analytics_risk.py — Cashier Risk Scoring tab.

Calculates a 0-100 risk score per cashier from five weighted signals,
colour-bands results Low/Medium/High, and presents a sortable table.
"""
import logging
import os
import glob
import datetime

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QComboBox, QScrollArea, QSizePolicy
)

from config import AMOUNT, DISCREPANCY_DB_PATH, PERFORMANCE_HISTORY_DB
from theme import Theme

from pages.analytics_risk_panels import (
    _W_DUP, _W_SUS, _W_SHR, _W_HIST, _W_SLIP, _MAX_WEIGHT, _DISP_WEIGHTS,
    BAND_HIGH, BAND_MEDIUM, BAND_LOW, _band, _card_frame,
    attach_benchmarking,
)


class RiskScoringPage(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._rows = []
        self._last_scores = []
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        # Header row
        hdr = QHBoxLayout()
        title = QLabel("Cashier Risk Scoring")
        title.setStyleSheet(f"color:{Theme.TXT};font-size:18px;font-weight:700;")
        hdr.addWidget(title)
        hdr.addStretch()

        # Timeline scope selector
        scope_lbl = QLabel("Scope:")
        scope_lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
        self._timeline_combo = QComboBox()
        for opt in ["This Report", "Today", "This Week", "This Month", "All Time"]:
            self._timeline_combo.addItem(opt)
        self._timeline_combo.setCurrentIndex(0)   # default: This Report
        self._timeline_combo.setFixedWidth(155)
        hdr.addWidget(scope_lbl)
        hdr.addWidget(self._timeline_combo)

        self._refresh_btn = QPushButton("Calculate Scores")
        self._refresh_btn.setObjectName("primary")
        self._refresh_btn.setFixedHeight(34)
        self._refresh_btn.setMinimumWidth(150)
        self._refresh_btn.clicked.connect(self.calculate)
        hdr.addWidget(self._refresh_btn)
        outer.addLayout(hdr)

        # Methodology card
        meth = _card_frame()
        ml = QVBoxLayout(meth); ml.setContentsMargins(18,14,18,14); ml.setSpacing(6)
        meth_title = QLabel("Scoring Methodology")
        meth_title.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:600;")
        ml.addWidget(meth_title)
        weights = list(zip(
            ["High Risk Duplicates", "Suspicious Patterns", "Shared Wallet Incidents",
             "Historical Discrepancies", "Slip Audit Mismatches"],
            _DISP_WEIGHTS,
            [Theme.DANGER, Theme.WARN, Theme.GOLD, Theme.INFO, Theme.TXT_2],
        ))
        grid = QHBoxLayout(); grid.setSpacing(8)
        for label, weight, color in weights:
            pill = QFrame()
            pill.setStyleSheet(
                f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER};"
                f"border-radius:6px;}}"
            )
            pl = QVBoxLayout(pill); pl.setContentsMargins(12,8,12,8); pl.setSpacing(2)
            wl = QLabel(f"{weight}%")
            wl.setStyleSheet(f"color:{color};font-size:16px;font-weight:700;font-family:Consolas,monospace;")
            ll = QLabel(label)
            ll.setStyleSheet(f"color:{Theme.TXT_3};font-size:10px;")
            ll.setWordWrap(True)
            pl.addWidget(wl); pl.addWidget(ll)
            grid.addWidget(pill)
        ml.addLayout(grid)
        outer.addWidget(meth)

        # Results scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self._results_widget = QWidget()
        self._results_widget.setStyleSheet("background:transparent;")
        self._results_layout = QVBoxLayout(self._results_widget)
        self._results_layout.setContentsMargins(0,0,0,0)
        self._results_layout.setSpacing(6)
        scroll.setWidget(self._results_widget)
        outer.addWidget(scroll, 1)

        self._no_data = QLabel(
            "Load a report in  Integrity Check  first, then click  Calculate Scores."
        )
        self._no_data.setAlignment(Qt.AlignCenter)
        self._no_data.setStyleSheet(f"color:{Theme.TXT_3};font-size:13px;padding:40px;")
        self._results_layout.addWidget(self._no_data)
        self._tab_btns = {}
        attach_benchmarking(self)

    def _theme_accent(self):
        return Theme.ACCENT

    def calculate(self):
        df = getattr(self.app, "active_df", None)
        if df is None or df.empty:
            return

        try:
            # Clear results
            while self._results_layout.count():
                item = self._results_layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()

            cashiers = df["Cashier Name"].unique() if "Cashier Name" in df.columns else []
            if not len(cashiers):
                return

            # ── Timeline scope ─────────────────────────────────────────
            timeline     = self._timeline_combo.currentText()
            session_only = (timeline == "This Report")
            cutoff       = None
            today        = datetime.date.today()
            if timeline == "Today":
                cutoff = today
            elif timeline == "This Week":
                cutoff = today - datetime.timedelta(days=7)
            elif timeline == "This Month":
                cutoff = datetime.date(today.year, today.month, 1)

            # ── Build signal maps ──────────────────────────────────────
            dup_counts = {}
            for rd in getattr(self.app,"_exact_dup_rows",[]):
                n = rd.get("Cashier Name", rd.get("Cashier",""))
                dup_counts[n] = dup_counts.get(n,0) + 1

            sus_counts = {}
            for rd in getattr(self.app,"_sus_rows",[]):
                n = rd.get("Cashier Name", rd.get("Cashier",""))
                sus_counts[n] = sus_counts.get(n,0) + 1

            shared_counts = {}
            for rd in getattr(self.app,"_shared_wallet_rows",[]):
                n = rd.get("Cashier Name", rd.get("Cashier",""))
                shared_counts[n] = shared_counts.get(n,0) + 1

            # Historical discrepancies — skipped in "This Report Only" mode
            hist_counts = {}
            if not session_only:
                try:
                    files = glob.glob(os.path.join(DISCREPANCY_DB_PATH,"**","*.xlsx"), recursive=True)
                    for fp in files:
                        tmp = pd.read_excel(fp)
                        if "Cashier Name" not in tmp.columns or "Small_Discrepancies" not in tmp.columns:
                            continue
                        # Apply cutoff per-row, not just on the first row
                        if cutoff is not None and "Report_Date" in tmp.columns:
                            try:
                                tmp["_rd_dt"] = pd.to_datetime(
                                    tmp["Report_Date"], dayfirst=True, errors="coerce"
                                )
                                tmp = tmp[tmp["_rd_dt"].dt.date >= cutoff]
                            except Exception:
                                pass
                        if tmp.empty:
                            continue
                        for _, row in tmp.iterrows():
                            n = str(row["Cashier Name"])
                            hist_counts[n] = hist_counts.get(n,0) + int(row.get("Small_Discrepancies",0))
                except Exception:
                    pass

            # Slip volume anomalies — sessions where cashier deviates >20% from
            # their own average slip count.  Derived from System Count in Audit_Database.csv.
            slip_counts = {}
            if not session_only:
                try:
                    if os.path.exists(PERFORMANCE_HISTORY_DB):
                        sh = pd.read_csv(PERFORMANCE_HISTORY_DB, dtype=str)
                        if "Name" in sh.columns and "System Count" in sh.columns:
                            sh["System Count"] = pd.to_numeric(
                                sh["System Count"], errors="coerce"
                            ).fillna(0)
                            if cutoff is not None and "Date" in sh.columns:
                                try:
                                    sh["_dt"] = pd.to_datetime(
                                        sh["Date"], dayfirst=True, errors="coerce"
                                    )
                                    sh = sh[sh["_dt"].dt.date >= cutoff]
                                except Exception:
                                    pass
                            for n, grp in sh.groupby("Name"):
                                counts = grp["System Count"].tolist()
                                if len(counts) < 2:
                                    continue
                                avg = sum(counts) / len(counts)
                                if avg == 0:
                                    continue
                                # Count sessions that deviate more than 20% from personal average
                                anomalous = sum(
                                    1 for c in counts
                                    if abs(c - avg) / avg > 0.20
                                )
                                if anomalous:
                                    slip_counts[n] = anomalous
                except Exception:
                    pass

            # Max values for normalisation
            max_dup    = max(dup_counts.values(),    default=1) or 1
            max_sus    = max(sus_counts.values(),    default=1) or 1
            max_shared = max(shared_counts.values(), default=1) or 1
            max_hist   = max(hist_counts.values(),   default=1) or 1
            max_slip   = max(slip_counts.values(),   default=1) or 1

            # ── Compute scores (weights normalized to 0-100 scale) ─────
            scores = []
            for name in cashiers:
                n = str(name)
                raw = (
                    _W_DUP  * (dup_counts.get(n,0)    / max_dup)    +
                    _W_SUS  * (sus_counts.get(n,0)     / max_sus)    +
                    _W_SHR  * (shared_counts.get(n,0)  / max_shared) +
                    _W_HIST * (hist_counts.get(n,0)    / max_hist)   +
                    _W_SLIP * (slip_counts.get(n,0)    / max_slip)
                )
                score = min(100, int(raw * 100 / _MAX_WEIGHT))
                scores.append((n, score, dup_counts.get(n,0),
                               sus_counts.get(n,0), shared_counts.get(n,0),
                               hist_counts.get(n,0), slip_counts.get(n,0)))

            scores.sort(key=lambda x: x[1], reverse=True)
            self._last_scores = scores   # stored for Score Guide tab

            # ── Column headers ─────────────────────────────────────────
            hdr_w = QWidget(); hdr_w.setStyleSheet("background:transparent;")
            hdr_l = QHBoxLayout(hdr_w); hdr_l.setContentsMargins(18,0,18,0); hdr_l.setSpacing(0)
            for txt, stretch in [("Cashier",3),("Score",1),("Duplicates",1),
                                  ("Suspicious",1),("Shared",1),("Hist. Disc.",1),("Slip Δ",1)]:
                lbl = QLabel(txt)
                lbl.setStyleSheet(
                    f"color:{Theme.TXT_DIM};font-size:9px;font-weight:700;letter-spacing:1.5px;"
                )
                hdr_l.addWidget(lbl, stretch)
            self._results_layout.addWidget(hdr_w)

            # ── Score rows ─────────────────────────────────────────────
            for name, score, dups, sus, shared, hist, slip in scores:
                bg, accent, band_lbl = _band(score)
                row_f = QFrame()
                row_f.setStyleSheet(
                    f"QFrame{{background:{bg};border:1px solid {Theme.BORDER_S};"
                    f"border-radius:6px;margin:1px 0;}}"
                )
                rl = QHBoxLayout(row_f); rl.setContentsMargins(18,10,18,10); rl.setSpacing(0)

                name_lbl = QLabel(name)
                name_lbl.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:500;")
                rl.addWidget(name_lbl, 3)

                # Score with band pill
                score_w = QWidget(); score_w.setStyleSheet("background:transparent;")
                sl = QHBoxLayout(score_w); sl.setContentsMargins(0,0,0,0); sl.setSpacing(6)
                sv = QLabel(str(score))
                sv.setStyleSheet(
                    f"color:{accent};font-size:14px;font-weight:700;font-family:Consolas,monospace;"
                )
                band_pill = QLabel(band_lbl)
                band_pill.setStyleSheet(
                    f"color:{accent};font-size:8px;font-weight:700;letter-spacing:1px;"
                    f"background:transparent;padding:2px 6px;border:1px solid {accent};"
                    f"border-radius:3px;"
                )
                sl.addWidget(sv); sl.addWidget(band_pill); sl.addStretch()
                rl.addWidget(score_w, 1)

                for val in [dups, sus, shared, hist, slip]:
                    lbl = QLabel(str(val) if val else "—")
                    lbl.setStyleSheet(
                        f"color:{accent if val else Theme.TXT_3};"
                        f"font-size:12px;font-family:Consolas,monospace;"
                    )
                    rl.addWidget(lbl, 1)

                self._results_layout.addWidget(row_f)

            self._results_layout.addStretch()

        except Exception:
            logging.exception("Unhandled exception")

    def showEvent(self, e):
        super().showEvent(e)
        df = getattr(self.app, "active_df", None)
        if df is not None and not df.empty:
            self._timeline_combo.setCurrentIndex(0)   # reset to This Report
        self.calculate()


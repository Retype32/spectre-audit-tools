"""
pages/analytics_quality.py — Data Quality Report tab.

Profiles the loaded report before analysis: missing values, duplicates,
value range violations, format inconsistencies, and an overall quality score.
"""
import logging

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QScrollArea
)

from config import AMOUNT, OPERATOR, WALLET, LODGEMENT
from theme import Theme


def _card(title=""):
    f = QFrame()
    f.setStyleSheet(
        f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
    )
    lay = QVBoxLayout(f); lay.setContentsMargins(20,16,20,18); lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:600;")
        lay.addWidget(t)
        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};"); lay.addWidget(div)
    return f, lay


class DataQualityPage(QWidget):
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
        title = QLabel("Data Quality Report")
        title.setStyleSheet(f"color:{Theme.TXT};font-size:18px;font-weight:700;")
        hdr.addWidget(title); hdr.addStretch()
        run_btn = QPushButton("Run Quality Check")
        run_btn.setObjectName("primary")
        run_btn.setFixedHeight(34); run_btn.setMinimumWidth(160)
        run_btn.clicked.connect(self.run)
        hdr.addWidget(run_btn)
        root.addLayout(hdr)

        sub = QLabel(
            "Profiles the loaded report for data issues before analysis. "
            "Identifies missing values, unexpected ranges, duplicates, and format problems."
        )
        sub.setStyleSheet(f"color:{Theme.TXT_3};font-size:12px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # Overall score card
        score_card, score_lay = _card()
        score_row = QHBoxLayout(); score_row.setSpacing(20)

        self._score_circle = QLabel("—")
        self._score_circle.setFixedSize(90, 90)
        self._score_circle.setAlignment(Qt.AlignCenter)
        self._score_circle.setStyleSheet(
            f"color:{Theme.ACCENT};font-size:28px;font-weight:800;"
            f"background:{Theme.ELEVATED};border-radius:45px;"
            f"font-family:Consolas,monospace;border:2px solid {Theme.BORDER};"
        )
        score_row.addWidget(self._score_circle)

        score_text = QVBoxLayout(); score_text.setSpacing(4)
        score_title = QLabel("Overall Data Quality Score")
        score_title.setStyleSheet(f"color:{Theme.TXT};font-size:14px;font-weight:600;")
        self._score_desc = QLabel("Run a quality check to see results.")
        self._score_desc.setStyleSheet(f"color:{Theme.TXT_3};font-size:12px;")
        self._score_desc.setWordWrap(True)
        score_text.addWidget(score_title); score_text.addWidget(self._score_desc)
        score_row.addLayout(score_text, 1)
        score_lay.addLayout(score_row)
        root.addWidget(score_card)

        # Check results container
        self._checks_card, self._checks_lay = _card("Quality Checks")
        self._checks_card.setVisible(False)
        root.addWidget(self._checks_card)

        # Column profile container
        self._profile_card, self._profile_lay = _card("Column Profiles")
        self._profile_card.setVisible(False)
        root.addWidget(self._profile_card)

        self._no_data = QLabel("No report loaded. Import a report in Integrity Check first.")
        self._no_data.setAlignment(Qt.AlignCenter)
        self._no_data.setStyleSheet(f"color:{Theme.TXT_3};font-size:13px;padding:40px;")
        root.addWidget(self._no_data)

    def run(self):
        df = getattr(self.app, "active_df", None)
        if df is None or df.empty:
            return

        try:
            self._no_data.setVisible(False)

            checks = []   # (label, status, detail)  status: "pass"/"warn"/"fail"
            score_points = 0
            total_points = 0

            n = len(df)

            # ── Check 1: Missing values ────────────────────────────────
            total_points += 20
            key_cols = [c for c in [OPERATOR, AMOUNT, WALLET, LODGEMENT] if c in df.columns]
            missing  = {c: int(df[c].isna().sum()) for c in key_cols}
            total_miss = sum(missing.values())
            if total_miss == 0:
                checks.append(("Missing Values", "pass",
                               f"No missing values in key columns ({', '.join(key_cols)})"))
                score_points += 20
            elif total_miss < n * 0.05:
                checks.append(("Missing Values", "warn",
                               f"{total_miss} missing values (<5% of rows): " +
                               ", ".join(f"{c}:{v}" for c,v in missing.items() if v)))
                score_points += 10
            else:
                checks.append(("Missing Values", "fail",
                               f"{total_miss} missing values (>{total_miss/n*100:.1f}% of rows)"))

            # ── Check 2: Amount range ──────────────────────────────────
            total_points += 20
            if AMOUNT in df.columns:
                neg = int((df[AMOUNT] < 0).sum())
                zero = int((df[AMOUNT] == 0).sum())
                extreme = int((df[AMOUNT] > 50000).sum())
                issues = []
                if neg:    issues.append(f"{neg} negative amounts")
                if zero:   issues.append(f"{zero} zero amounts")
                if extreme: issues.append(f"{extreme} amounts >€50,000")
                if not issues:
                    checks.append(("Amount Range", "pass", f"All {n:,} amounts in expected range (€0–€50,000)"))
                    score_points += 20
                elif neg == 0 and (zero + extreme) < n * 0.01:
                    checks.append(("Amount Range", "warn", "Minor outliers: " + ", ".join(issues)))
                    score_points += 12
                else:
                    checks.append(("Amount Range", "fail", "Range violations: " + ", ".join(issues)))
                    score_points += 4

            # ── Check 3: Exact duplicates ──────────────────────────────
            total_points += 20
            dup_count = int(df.duplicated().sum())
            if dup_count == 0:
                checks.append(("Exact Duplicates", "pass", "No fully identical duplicate rows found"))
                score_points += 20
            elif dup_count < n * 0.02:
                checks.append(("Exact Duplicates", "warn",
                               f"{dup_count} duplicate rows ({dup_count/n*100:.1f}% of data)"))
                score_points += 8
            else:
                checks.append(("Exact Duplicates", "fail",
                               f"{dup_count} duplicate rows ({dup_count/n*100:.1f}%) — data integrity concern"))

            # ── Check 4: Operator ID format ────────────────────────────
            total_points += 20
            if OPERATOR in df.columns:
                ops = df[OPERATOR].astype(str).str.strip()
                non_numeric = int((~ops.str.match(r'^\d+$')).sum())
                if non_numeric == 0:
                    checks.append(("Operator ID Format", "pass",
                                   f"All {ops.nunique()} unique operator IDs are numeric"))
                    score_points += 20
                elif non_numeric < n * 0.05:
                    checks.append(("Operator ID Format", "warn",
                                   f"{non_numeric} non-numeric operator IDs found"))
                    score_points += 10
                else:
                    checks.append(("Operator ID Format", "fail",
                                   f"{non_numeric} operator IDs with unexpected format"))

            # ── Check 5: Row count sanity ──────────────────────────────
            total_points += 20
            if n < 10:
                checks.append(("Row Count", "warn", f"Only {n} rows — report may be incomplete"))
                score_points += 8
            elif n > 100000:
                checks.append(("Row Count", "warn", f"{n:,} rows — very large report, verify source"))
                score_points += 14
            else:
                checks.append(("Row Count", "pass", f"{n:,} rows — expected range"))
                score_points += 20


            # ── Overall score ──────────────────────────────────────────
            pct = int(score_points / total_points * 100) if total_points else 0
            self._score_circle.setText(f"{pct}")
            color = Theme.OK if pct >= 80 else Theme.WARN if pct >= 50 else Theme.DANGER
            self._score_circle.setStyleSheet(
                f"color:{color};font-size:28px;font-weight:800;"
                f"background:{Theme.ELEVATED};border-radius:45px;"
                f"font-family:Consolas,monospace;border:2px solid {color};"
            )
            grade = "Excellent" if pct>=90 else "Good" if pct>=75 else "Fair" if pct>=50 else "Poor"
            self._score_desc.setText(
                f"{grade} data quality ({pct}/100). "
                + ("Data is clean and ready for analysis." if pct>=80 else
                   "Some issues found — review checks below before drawing conclusions." if pct>=50 else
                   "Significant data quality issues. Findings may be unreliable.")
            )

            # ── Render check rows ──────────────────────────────────────
            while self._checks_lay.count() > 2:
                item = self._checks_lay.takeAt(self._checks_lay.count()-1)
                if item.widget(): item.widget().deleteLater()

            STATUS_COLOR = {"pass": Theme.OK, "warn": Theme.WARN, "fail": Theme.DANGER}
            STATUS_ICON  = {"pass": "✓", "warn": "⚠", "fail": "✗"}

            for label, status, detail in checks:
                row = QFrame()
                row.setStyleSheet(
                    f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER};"
                    f"border-radius:6px;}}"
                )
                rl = QHBoxLayout(row); rl.setContentsMargins(16,10,16,10); rl.setSpacing(14)

                icon = QLabel(STATUS_ICON[status])
                color = STATUS_COLOR[status]
                icon.setStyleSheet(
                    f"color:{color};font-size:16px;font-weight:700;"
                    f"background:{Theme.SURFACE};border-radius:12px;"
                    f"min-width:24px;max-width:24px;padding:2px;"
                )
                icon.setAlignment(Qt.AlignCenter)

                text_lay = QVBoxLayout(); text_lay.setSpacing(2)
                lbl_w = QLabel(label)
                lbl_w.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:600;")
                det_w = QLabel(detail)
                det_w.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
                det_w.setWordWrap(True)
                text_lay.addWidget(lbl_w); text_lay.addWidget(det_w)

                rl.addWidget(icon); rl.addLayout(text_lay, 1)
                self._checks_lay.addWidget(row)

            self._checks_card.setVisible(True)

            # ── Column profiles ────────────────────────────────────────
            while self._profile_lay.count() > 2:
                item = self._profile_lay.takeAt(self._profile_lay.count()-1)
                if item.widget(): item.widget().deleteLater()

            profile_grid = QHBoxLayout(); profile_grid.setSpacing(8)
            numeric_cols = df.select_dtypes(include='number').columns.tolist()[:6]

            for col in numeric_cols:
                col_f = QFrame()
                col_f.setStyleSheet(
                    f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER};"
                    f"border-radius:7px;}}"
                )
                cl = QVBoxLayout(col_f); cl.setContentsMargins(12,10,12,12); cl.setSpacing(4)

                col_title = QLabel(str(col)[:20])
                col_title.setStyleSheet(f"color:{Theme.TXT};font-size:11px;font-weight:600;")
                cl.addWidget(col_title)

                series = df[col].dropna()
                stats = [
                    ("Count",  f"{len(series):,}"),
                    ("Unique", f"{series.nunique():,}"),
                    ("Mean",   f"{series.mean():,.2f}" if len(series) else "—"),
                    ("Null%",  f"{df[col].isna().mean()*100:.1f}%"),
                ]
                for k, v in stats:
                    sr = QHBoxLayout(); sr.setSpacing(6)
                    kl = QLabel(k); kl.setStyleSheet(f"color:{Theme.TXT_3};font-size:10px;")
                    vl = QLabel(v); vl.setStyleSheet(
                        f"color:{Theme.TXT_2};font-size:10px;font-family:Consolas,monospace;"
                    )
                    sr.addWidget(kl); sr.addStretch(); sr.addWidget(vl)
                    cl.addLayout(sr)

                profile_grid.addWidget(col_f)

            self._profile_lay.addLayout(profile_grid)
            self._profile_card.setVisible(True)

        except Exception:
            logging.exception("Unhandled exception")

    def showEvent(self, e):
        super().showEvent(e)
        df = getattr(self.app, "active_df", None)
        if df is not None and not df.empty:
            self.run()
        else:
            self._no_data.setVisible(True)

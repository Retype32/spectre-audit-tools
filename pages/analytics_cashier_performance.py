"""
pages/analytics_cashier_performance.py — Cashier Performance Analytics.

Score (0–100) = six positive components − mistake penalties

Positive components (max 90 pts for single session, 100 pts for multi-day):
  Throughput   25 pts — slips/hr vs 25/hr target (capped at 1.2×, prevents over-reward)
  Value        20 pts — total € vs fixed daily target (NOT vs best colleague)
  Slip Count   15 pts — total slips vs fixed daily target (NOT vs best colleague)
  Accuracy     20 pts — (1 − mistake_rate) × 20
  Consistency  10 pts — score stability over time (multi-day scopes only)
  Clean Ratio  10 pts — % of slips untouched by any mistake

Mistake penalties (deducted after metrics, final score floored at 0):
  Duplicate Slip      −12 pts each
  Miscredit           −12 pts each
  Money Lost          −15 pts each
  Slip Not Processed   −8 pts each
  Small Mistake        −3 pts each

Confirmed duplicates from Integrity Check auto-map to Duplicate Slip penalties.
Targets are derived from the historical average in Audit_Database.csv — not from
the best performer on any given day, which removes inter-cashier score distortion.

Recency weighting (3M / 6M / 12M views):
  Most recent third of period → 50 % weight
  Middle third               → 30 % weight
  Oldest third               → 20 % weight
"""
import logging
import os
import datetime

import pandas as pd

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QComboBox, QScrollArea, QDialog, QLineEdit,
    QFormLayout, QDialogButtonBox, QDateEdit, QMessageBox,
    QSizePolicy,
)

from config import (
    AMOUNT, OPERATOR, PERFORMANCE_HISTORY_DB,
    MISTAKES_DB, MISTAKE_TYPES,
)
from theme import Theme

from scoring import (
    grade as _grade, shift_hours as _shift_hours,
    compute_targets as _compute_targets, score_one_session as _score_one_session,
    consistency_score as _consistency_score,
    recency_weighted_avg as _recency_weighted_avg,
    penalty_summary as _penalty_summary,
    all_mistakes as _all_mistakes, mistakes_by_cashier as _mistakes_by_cashier,
    _TARGET_PER_HOUR, _W_THROUGHPUT, _W_VALUE, _W_SLIPS,
    _W_ACCURACY, _W_CONSISTENCY, _W_CLEAN_RATIO, _RECENCY, SCOPES,
)

_SCOPES = SCOPES

_GRADE_COLOR = {
    "A": Theme.OK,
    "B": "#4d9fff",
    "C": Theme.WARN,
    "D": Theme.GOLD,
    "F": Theme.DANGER,
}


def _card(title=""):
    f = QFrame()
    f.setStyleSheet(
        f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};"
        f"border-radius:8px;}}"
    )
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 14, 18, 16)
    lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setStyleSheet(
            f"color:{Theme.TXT};font-size:12px;font-weight:600;letter-spacing:0.2px;"
        )
        lay.addWidget(t)
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div)
    return f, lay


# ── Log Mistake Dialog ─────────────────────────────────────────────────────────

class LogMistakeDialog(QDialog):
    """Modal dialog for logging a cashier mistake."""

    def __init__(self, cashier_names, report_date=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Cashier Mistake")
        self.setMinimumWidth(440)
        self.setStyleSheet(
            f"QDialog{{background:{Theme.BG};color:{Theme.TXT};}}"
            f"QLabel{{color:{Theme.TXT};}}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

        title = QLabel("Log Cashier Mistake")
        title.setStyleSheet(
            f"color:{Theme.TXT};font-size:15px;font-weight:700;"
        )
        lay.addWidget(title)

        sub = QLabel(
            "Mistakes are saved to the database and applied to the cashier's "
            "Accuracy and Clean Ratio scores.  Confirmed duplicates from Integrity "
            "Check are added automatically — no need to log them here."
        )
        sub.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        # Date
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("dd.MM.yyyy")
        if report_date:
            try:
                d = datetime.datetime.strptime(report_date, "%d.%m.%Y").date()
                self._date_edit.setDate(QDate(d.year, d.month, d.day))
            except Exception:
                self._date_edit.setDate(QDate.currentDate())
        else:
            self._date_edit.setDate(QDate.currentDate())
        form.addRow("Date:", self._date_edit)

        # Cashier
        self._cashier_cb = QComboBox()
        for name in sorted(cashier_names):
            self._cashier_cb.addItem(name)
        form.addRow("Cashier:", self._cashier_cb)

        # Type
        self._type_cb = QComboBox()
        for key, info in MISTAKE_TYPES.items():
            self._type_cb.addItem(f"{info['label']}  (−{info['points']} pts)", key)
        form.addRow("Mistake type:", self._type_cb)

        # Notes
        self._notes = QLineEdit()
        self._notes.setPlaceholderText("Optional — brief description")
        form.addRow("Notes:", self._notes)

        lay.addLayout(form)

        # Severity preview label
        self._sev_lbl = QLabel()
        self._sev_lbl.setStyleSheet(
            f"color:{Theme.DANGER};font-size:11px;font-weight:600;"
        )
        lay.addWidget(self._sev_lbl)
        self._type_cb.currentIndexChanged.connect(self._update_severity)
        self._update_severity()

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setObjectName("primary")
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _update_severity(self):
        key  = self._type_cb.currentData()
        info = MISTAKE_TYPES.get(key, {})
        pts  = info.get("points", 0)
        self._sev_lbl.setText(f"This will deduct {pts} points from the cashier's score.")

    def _save(self):
        date_val = self._date_edit.date().toString("dd.MM.yyyy")
        cashier  = self._cashier_cb.currentText()
        type_key = self._type_cb.currentData()
        if not type_key:
            return
        points = MISTAKE_TYPES[type_key]["points"]
        notes  = self._notes.text().strip()

        new_row = {
            "date":            date_val,
            "cashier":         cashier,
            "operator_id":     "",
            "type":            type_key,
            "severity_points": points,
            "notes":           notes,
            "logged_at":       datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        try:
            if os.path.exists(MISTAKES_DB):
                mdf = pd.read_csv(MISTAKES_DB, dtype=str)
            else:
                mdf = pd.DataFrame(columns=list(new_row.keys()))
            mdf = pd.concat([mdf, pd.DataFrame([new_row])], ignore_index=True)
            os.makedirs(os.path.dirname(MISTAKES_DB), exist_ok=True)
            mdf.to_csv(MISTAKES_DB, index=False)
            self.accept()
        except Exception as e:
            logging.exception("LogMistakeDialog._save")
            QMessageBox.critical(self, "Save Failed", f"Could not write mistake:\n{e}")


# ── Score Breakdown Dialog ─────────────────────────────────────────────────────

class BreakdownDialog(QDialog):
    """Displays the full score breakdown for one cashier."""

    def __init__(self, row_data, scope, parent=None):
        super().__init__(parent)
        name = row_data["name"]
        self.setWindowTitle(f"Score Breakdown — {name}")
        self.setMinimumWidth(460)
        self.setStyleSheet(
            f"QDialog{{background:{Theme.BG};color:{Theme.TXT};}}"
            f"QLabel{{color:{Theme.TXT};}}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color:{Theme.TXT};font-size:16px;font-weight:700;"
        )
        grade    = row_data["grade"]
        g_color  = _GRADE_COLOR.get(grade, Theme.TXT_3)
        grade_lbl = QLabel(grade)
        grade_lbl.setStyleSheet(
            f"color:{g_color};font-size:22px;font-weight:800;"
            f"font-family:Consolas,monospace;"
        )
        score_lbl = QLabel(str(row_data["score"]))
        score_lbl.setStyleSheet(
            f"color:{g_color};font-size:22px;font-weight:800;"
            f"font-family:Consolas,monospace;"
        )
        hdr.addWidget(name_lbl)
        hdr.addStretch()
        hdr.addWidget(score_lbl)
        hdr.addWidget(QLabel("/100"))
        hdr.addWidget(grade_lbl)
        lay.addLayout(hdr)

        sessions = row_data.get("sessions", 1)
        scope_txt = f"{scope}  ·  {sessions} working day{'s' if sessions != 1 else ''}"
        scope_lbl = QLabel(scope_txt)
        scope_lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
        lay.addWidget(scope_lbl)

        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div)

        # Components
        bd = row_data.get("breakdown", {})
        cons = row_data.get("consistency")  # None = single session
        single = (scope == "This Report")

        components = [
            ("Throughput",   bd.get("thr_score",  0), _W_THROUGHPUT,  Theme.ACCENT),
            ("Value",        bd.get("val_score",  0), _W_VALUE,        Theme.INFO),
            ("Slip Count",   bd.get("slip_score", 0), _W_SLIPS,        Theme.GOLD),
            ("Accuracy",     bd.get("acc_score",  0), _W_ACCURACY,     Theme.OK),
            ("Consistency",  cons if cons is not None else None, _W_CONSISTENCY, "#7eb8ff"),
            ("Clean Ratio",  bd.get("clean_score",0), _W_CLEAN_RATIO,  Theme.PURPLE),
        ]

        for label, pts, max_pts, color in components:
            row_f = QFrame()
            row_f.setStyleSheet(
                f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER};"
                f"border-radius:5px;}}"
            )
            rl = QHBoxLayout(row_f)
            rl.setContentsMargins(14, 8, 14, 8)
            rl.setSpacing(8)

            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{Theme.TXT_2};font-size:12px;")
            lbl.setFixedWidth(110)

            if pts is None:
                val_lbl = QLabel("N/A — single session")
                val_lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;font-style:italic;")
            else:
                val_lbl = QLabel(f"{pts:.1f} / {max_pts}")
                pct = pts / max_pts if max_pts else 0
                clr = color if pct >= 0.7 else (Theme.WARN if pct >= 0.4 else Theme.DANGER)
                val_lbl.setStyleSheet(
                    f"color:{clr};font-size:13px;font-weight:700;"
                    f"font-family:Consolas,monospace;"
                )

            # Progress bar
            bar_bg = QFrame()
            bar_bg.setFixedHeight(6)
            bar_bg.setStyleSheet(
                f"background:{Theme.BORDER};border-radius:3px;"
            )
            bar_bg.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            if pts is not None and max_pts:
                fill_pct = min(1.0, pts / max_pts)
                pct_int  = int(fill_pct * 100)
                fill_clr = color if fill_pct >= 0.7 else (
                    Theme.WARN if fill_pct >= 0.4 else Theme.DANGER
                )
                bar_bg.setStyleSheet(
                    f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                    f" stop:0 {fill_clr}, stop:{fill_pct:.3f} {fill_clr},"
                    f" stop:{min(fill_pct + 0.001, 1.0):.3f} {Theme.BORDER},"
                    f" stop:1 {Theme.BORDER});"
                    f"border-radius:3px;"
                )

            rl.addWidget(lbl)
            rl.addWidget(val_lbl)
            rl.addWidget(bar_bg, 1)
            lay.addWidget(row_f)

        # Penalty section
        div2 = QFrame(); div2.setFixedHeight(1)
        div2.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div2)

        penalty = bd.get("penalty", 0)
        pen_hdr = QLabel("Mistake Penalties")
        pen_hdr.setStyleSheet(
            f"color:{Theme.TXT};font-size:11px;font-weight:600;"
        )
        lay.addWidget(pen_hdr)

        pen_text = _penalty_summary(row_data.get("mistakes_list", []))
        for line in pen_text.split("\n"):
            pl = QLabel(f"  {line}")
            color = Theme.DANGER if penalty > 0 else Theme.OK
            pl.setStyleSheet(f"color:{color};font-size:11px;font-family:Consolas,monospace;")
            lay.addWidget(pl)

        if penalty > 0:
            tot_pen = QLabel(f"  Total deducted:  −{penalty} pts")
            tot_pen.setStyleSheet(
                f"color:{Theme.DANGER};font-size:12px;font-weight:700;"
                f"font-family:Consolas,monospace;"
            )
            lay.addWidget(tot_pen)

        # Final score summary
        div3 = QFrame(); div3.setFixedHeight(1)
        div3.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div3)

        base     = bd.get("base", 0)
        cons_val = cons if (cons is not None) else 0
        summary_parts = []
        if not single:
            # period_base = recency-weighted avg of daily scores (penalties already applied)
            pb = row_data.get("period_base", base)
            summary_parts.append(
                f"Period avg daily score: {pb:.1f} pts"
                f"  (penalties applied per working day)"
            )
            if cons_val:
                summary_parts.append(f"+ Consistency bonus:  +{cons_val:.1f} pts")
            if penalty:
                summary_parts.append(
                    f"Total penalties this period:  −{penalty} pts  "
                    f"({len(row_data.get('mistakes_list', []))} "
                    f"mistake{'s' if len(row_data.get('mistakes_list', [])) != 1 else ''})"
                )
        else:
            summary_parts.append(f"Base metrics total:  {base:.1f} pts")
            summary_parts.append("Consistency:  N/A (single session)")
            if penalty:
                summary_parts.append(f"− Penalties:  −{penalty} pts")

        for part in summary_parts:
            sl = QLabel(part)
            sl.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
            lay.addWidget(sl)

        final_lbl = QLabel(f"Final score:  {row_data['score']}  (Grade {row_data['grade']})")
        g_color   = _GRADE_COLOR.get(row_data['grade'], Theme.TXT)
        final_lbl.setStyleSheet(
            f"color:{g_color};font-size:14px;font-weight:700;"
            f"font-family:Consolas,monospace;"
        )
        lay.addWidget(final_lbl)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn)

        if single:
            note = QLabel(
                "Single-session view: Consistency score requires multi-day data.  "
                "Switch to a longer period to see the full 100-pt scale."
            )
            note.setStyleSheet(
                f"color:{Theme.TXT_3};font-size:10px;font-style:italic;"
            )
            note.setWordWrap(True)
            lay.addWidget(note)


# ── Clickable row widget ───────────────────────────────────────────────────────

class _ClickableRow(QFrame):
    def __init__(self, data, scope, parent=None):
        super().__init__(parent)
        self._data  = data
        self._scope = scope
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        dlg = BreakdownDialog(self._data, self._scope, self)
        dlg.exec()


# =============================================================================
class CashierPerformancePage(QWidget):

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app         = app
        self._last_data  = []
        self._sort_col   = "score"
        self._sort_asc   = False
        self._build()

    # ── UI Construction ───────────────────────────────────────────────────────
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        root = QVBoxLayout(inner)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(20)
        root.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # ── Header row ────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(10)
        title = QLabel("Cashier Performance Analytics")
        title.setStyleSheet(f"color:{Theme.TXT};font-size:18px;font-weight:700;")
        hdr.addWidget(title)
        hdr.addStretch()

        scope_lbl = QLabel("Period:")
        scope_lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
        self._scope = QComboBox()
        for s in _SCOPES:
            self._scope.addItem(s)
        self._scope.setCurrentIndex(0)
        self._scope.setFixedWidth(130)

        run_btn = QPushButton("Compute")
        run_btn.setObjectName("primary")
        run_btn.setFixedHeight(34)
        run_btn.setMinimumWidth(110)
        run_btn.clicked.connect(self.compute)

        self._log_btn = QPushButton("+ Log Mistake")
        self._log_btn.setFixedHeight(34)
        self._log_btn.setMinimumWidth(120)
        self._log_btn.clicked.connect(self._open_log_mistake)

        hdr.addWidget(scope_lbl)
        hdr.addWidget(self._scope)
        hdr.addWidget(self._log_btn)
        hdr.addWidget(run_btn)
        root.addLayout(hdr)

        sub = QLabel(
            "Scores each cashier across six dimensions: throughput, value, slip volume, "
            "accuracy, consistency, and clean work ratio.  Click any row to see the full "
            "score breakdown.  Mistakes are logged with  + Log Mistake  and applied automatically."
        )
        sub.setStyleSheet(f"color:{Theme.TXT_3};font-size:12px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # ── Methodology card ──────────────────────────────────────────
        meth_card, meth_lay = _card("Performance Score Methodology")

        # Fairness note
        fair_lbl = QLabel(
            "Scores compare against fixed targets, not colleagues — "
            "a fast colleague does not reduce your score."
        )
        fair_lbl.setStyleSheet(
            f"color:{Theme.OK};font-size:10px;font-weight:600;"
            f"letter-spacing:0.2px;"
        )
        meth_lay.addWidget(fair_lbl)

        # Component pills row
        pill_row = QHBoxLayout(); pill_row.setSpacing(6)
        for label, pts, color in [
            ("Throughput\nslips/hr vs 25/hr",    "25 pts", Theme.ACCENT),
            ("Value\nvs daily target",           "20 pts", Theme.INFO),
            ("Slip Count\nvs daily target",      "15 pts", Theme.GOLD),
            ("Accuracy\nmistake-rate based",     "20 pts", Theme.OK),
            ("Consistency\nstability over time", "10 pts", "#7eb8ff"),
            ("Clean Ratio\n% error-free slips",  "10 pts", Theme.PURPLE),
            ("Mistake Penalty\nper event logged", "−var", Theme.DANGER),
        ]:
            pf = QFrame()
            pf.setStyleSheet(
                f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER};"
                f"border-radius:6px;}}"
            )
            pl = QVBoxLayout(pf); pl.setContentsMargins(10, 7, 10, 7); pl.setSpacing(2)
            vl = QLabel(pts)
            vl.setAlignment(Qt.AlignCenter)
            vl.setStyleSheet(
                f"color:{color};font-size:13px;font-weight:700;"
                f"font-family:Consolas,monospace;"
            )
            kl = QLabel(label)
            kl.setAlignment(Qt.AlignCenter)
            kl.setStyleSheet(f"color:{Theme.TXT_3};font-size:8px;font-weight:600;")
            kl.setWordWrap(True)
            pl.addWidget(vl); pl.addWidget(kl)
            pill_row.addWidget(pf)
        meth_lay.addLayout(pill_row)

        # Grade scale row
        grades_row = QHBoxLayout(); grades_row.setSpacing(6)
        for g, color in _GRADE_COLOR.items():
            pf2 = QFrame()
            pf2.setStyleSheet(
                f"QFrame{{background:{Theme.ELEVATED};border:1px solid {color};"
                f"border-radius:6px;}}"
            )
            pl2 = QVBoxLayout(pf2); pl2.setContentsMargins(10, 5, 10, 5); pl2.setSpacing(1)
            gl = QLabel(g)
            gl.setAlignment(Qt.AlignCenter)
            gl.setStyleSheet(
                f"color:{color};font-size:15px;font-weight:800;"
                f"font-family:Consolas,monospace;"
            )
            thr = {"A": "≥90", "B": "≥75", "C": "≥60", "D": "≥45", "F": "<45"}[g]
            tl = QLabel(thr)
            tl.setAlignment(Qt.AlignCenter)
            tl.setStyleSheet(f"color:{Theme.TXT_3};font-size:9px;font-weight:700;")
            pl2.addWidget(gl); pl2.addWidget(tl)
            grades_row.addWidget(pf2)

        note_lbl = QLabel(
            "  Consistency requires multi-day scope.  Single-session max = 90 (Grade A)."
        )
        note_lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:9px;font-style:italic;")
        grades_row.addWidget(note_lbl)
        grades_row.addStretch()
        meth_lay.addLayout(grades_row)
        root.addWidget(meth_card)

        # ── Summary pills ─────────────────────────────────────────────
        self._pills_frame = QFrame()
        self._pills_frame.setVisible(False)
        self._pills_frame.setStyleSheet(
            f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
        )
        pf_lay = QHBoxLayout(self._pills_frame)
        pf_lay.setContentsMargins(18, 12, 18, 12); pf_lay.setSpacing(6)
        self._pills = {}
        for key, label in [
            ("cashiers",   "Cashiers"),
            ("total_txn",  "Total Slips"),
            ("total_val",  "Total Value"),
            ("avg_rate",   "Avg Slips/Hr"),
            ("avg_score",  "Avg Score"),
            ("grade_a",    "Grade A"),
            ("mistakes",   "Mistakes Logged"),
            ("penalties",  "Total Penalties"),
        ]:
            pf3 = QFrame()
            pf3.setStyleSheet(
                f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER};"
                f"border-radius:6px;}}"
            )
            pl3 = QVBoxLayout(pf3); pl3.setContentsMargins(11, 7, 11, 7); pl3.setSpacing(2)
            vl = QLabel("—")
            vl.setStyleSheet(
                f"color:{Theme.ACCENT};font-size:14px;font-weight:700;"
                f"font-family:Consolas,monospace;"
            )
            kl = QLabel(label)
            kl.setStyleSheet(
                f"color:{Theme.TXT_3};font-size:8px;font-weight:700;letter-spacing:1px;"
            )
            pl3.addWidget(vl); pl3.addWidget(kl)
            self._pills[key] = vl
            pf_lay.addWidget(pf3)
        root.addWidget(self._pills_frame)

        # ── Team Performance Score card ───────────────────────────────
        self._perf_score_card = QFrame()
        self._perf_score_card.setVisible(False)
        self._perf_score_card.setStyleSheet(
            f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
        )
        psc_lay = QHBoxLayout(self._perf_score_card)
        psc_lay.setContentsMargins(20, 16, 20, 16); psc_lay.setSpacing(20)

        self._perf_score_circle = QLabel("—")
        self._perf_score_circle.setFixedSize(80, 80)
        self._perf_score_circle.setAlignment(Qt.AlignCenter)
        self._perf_score_circle.setStyleSheet(
            f"color:{Theme.ACCENT};font-size:26px;font-weight:800;"
            f"background:{Theme.ELEVATED};border-radius:40px;"
            f"font-family:Consolas,monospace;border:2px solid {Theme.BORDER};"
        )
        psc_lay.addWidget(self._perf_score_circle)

        psc_text = QVBoxLayout(); psc_text.setSpacing(4)
        psc_title = QLabel("Overall Team Performance Score")
        psc_title.setStyleSheet(f"color:{Theme.TXT};font-size:14px;font-weight:600;")
        self._perf_score_desc = QLabel("Compute performance to see the team score.")
        self._perf_score_desc.setStyleSheet(f"color:{Theme.TXT_3};font-size:12px;")
        self._perf_score_desc.setWordWrap(True)
        psc_text.addWidget(psc_title)
        psc_text.addWidget(self._perf_score_desc)
        psc_lay.addLayout(psc_text, 1)

        # Targets display
        self._targets_lbl = QLabel()
        self._targets_lbl.setStyleSheet(
            f"color:{Theme.TXT_3};font-size:10px;font-family:Consolas,monospace;"
        )
        self._targets_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        psc_lay.addWidget(self._targets_lbl)
        root.addWidget(self._perf_score_card)

        # ── Sort bar ──────────────────────────────────────────────────
        self._sort_frame = QFrame()
        self._sort_frame.setVisible(False)
        self._sort_frame.setStyleSheet("background:transparent;")
        sf_lay = QHBoxLayout(self._sort_frame)
        sf_lay.setContentsMargins(0, 0, 0, 0); sf_lay.setSpacing(5)
        sort_lbl = QLabel("Sort by:")
        sort_lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
        sf_lay.addWidget(sort_lbl)
        self._sort_btns = {}
        for key, label in [
            ("name",        "Cashier"),
            ("score",       "Score"),
            ("txn",         "Slips"),
            ("value",       "Value"),
            ("throughput",  "Throughput"),
            ("accuracy",    "Accuracy"),
            ("consistency", "Consistency"),
            ("mistakes",    "Mistakes"),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(26); b.setMinimumWidth(80)
            b.clicked.connect(lambda _=False, k=key: self._sort_by(k))
            sf_lay.addWidget(b)
            self._sort_btns[key] = b
        sf_lay.addStretch()
        root.addWidget(self._sort_frame)

        # ── Results card ──────────────────────────────────────────────
        self._results_card = QFrame()
        self._results_card.setVisible(False)
        self._results_card.setStyleSheet(
            f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
        )
        rc_lay = QVBoxLayout(self._results_card)
        rc_lay.setContentsMargins(0, 0, 0, 0); rc_lay.setSpacing(0)

        hdr_w = QWidget()
        hdr_w.setStyleSheet(f"background:{Theme.ELEVATED};border-radius:7px 7px 0 0;")
        hdr_l = QHBoxLayout(hdr_w)
        hdr_l.setContentsMargins(18, 8, 18, 8); hdr_l.setSpacing(0)
        for txt, stretch in [
            ("Cashier",      3),
            ("Score",        1),
            ("Slips",        1),
            ("Value",        1),
            ("Throughput",   2),
            ("Accuracy",     1),
            ("Consistency",  1),
            ("Mistakes",     1),
        ]:
            lbl = QLabel(txt)
            lbl.setStyleSheet(
                f"color:{Theme.TXT_DIM};font-size:9px;font-weight:700;letter-spacing:1.5px;"
            )
            hdr_l.addWidget(lbl, stretch)
        rc_lay.addWidget(hdr_w)

        row_scroll = QScrollArea()
        row_scroll.setWidgetResizable(True)
        row_scroll.setFrameShape(QFrame.NoFrame)
        row_scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        row_scroll.setMinimumHeight(280)
        self._rows_w = QWidget()
        self._rows_w.setStyleSheet("background:transparent;")
        self._rows_lay = QVBoxLayout(self._rows_w)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(0)
        row_scroll.setWidget(self._rows_w)
        rc_lay.addWidget(row_scroll, 1)
        root.addWidget(self._results_card)

        # ── No data placeholder ───────────────────────────────────────
        self._no_data = QLabel(
            "Load a report in  Integrity Check  first, then click  Compute."
        )
        self._no_data.setAlignment(Qt.AlignCenter)
        self._no_data.setStyleSheet(
            f"color:{Theme.TXT_3};font-size:13px;padding:60px;"
        )
        root.addWidget(self._no_data)

        self._update_sort_styles()

    # ── Sort ──────────────────────────────────────────────────────────────────
    def _update_sort_styles(self):
        for key, btn in self._sort_btns.items():
            active = (key == self._sort_col)
            btn.setStyleSheet(
                f"QPushButton{{background:{Theme.ACCENT if active else Theme.ELEVATED};"
                f"color:{'white' if active else Theme.TXT_3};"
                f"border:1px solid {Theme.ACCENT if active else Theme.BORDER};"
                f"border-radius:4px;font-size:10px;font-weight:600;padding:0 6px;}}"
                f"QPushButton:hover{{color:{'white' if active else Theme.TXT_2};}}"
            )

    def _sort_by(self, key):
        if self._sort_col == key:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = key
            self._sort_asc = False
        self._update_sort_styles()
        self._render_rows(self._last_data)

    # ── Log Mistake ───────────────────────────────────────────────────────────
    def _open_log_mistake(self):
        df = getattr(self.app, "active_df", None)
        if df is None or df.empty or "Cashier Name" not in df.columns:
            QMessageBox.information(
                self, "No Report",
                "Load a report first so cashier names are available."
            )
            return
        cashiers    = sorted(df["Cashier Name"].dropna().unique().tolist())
        report_date = getattr(self.app, "_active_report_date", None)
        dlg = LogMistakeDialog(cashiers, report_date=report_date, parent=self)
        if dlg.exec():
            self.compute()  # refresh scores after saving

    # ── Compute ───────────────────────────────────────────────────────────────
    def compute(self):
        df = getattr(self.app, "active_df", None)
        if df is None or df.empty:
            return

        try:
            scope        = self._scope.currentText()
            session_only = (scope == "This Report")
            today        = datetime.date.today()
            cutoff       = None

            if scope == "Today":
                cutoff = today
            elif scope == "This Week":
                cutoff = today - datetime.timedelta(days=7)
            elif scope == "This Month":
                cutoff = datetime.date(today.year, today.month, 1)
            elif scope == "3 Months":
                cutoff = today - datetime.timedelta(days=90)
            elif scope == "6 Months":
                cutoff = today - datetime.timedelta(days=180)
            elif scope == "12 Months":
                cutoff = today - datetime.timedelta(days=365)

            if "Cashier Name" not in df.columns:
                return

            active_date = getattr(self.app, "_active_report_date", None)

            # ── Session data ──────────────────────────────────────────
            session_txn:    dict = {}
            session_val:    dict = {}
            cashier_op_ids: dict = {}

            for name, grp in df.groupby("Cashier Name"):
                n = str(name)
                session_txn[n] = len(grp)
                session_val[n] = float(grp[AMOUNT].sum()) if AMOUNT in df.columns else 0.0
                if OPERATOR in grp.columns:
                    op = grp[OPERATOR].mode()
                    cashier_op_ids[n] = str(op.iloc[0]).strip() if not op.empty else ""

            all_cashiers = set(session_txn.keys())

            # ── Historical data ───────────────────────────────────────
            # hist_daily: {cashier: [(date_obj_or_None, slips, value), ...]}
            hist_daily: dict = {}
            hist_df    = None

            if not session_only:
                try:
                    if os.path.exists(PERFORMANCE_HISTORY_DB):
                        hist_df = pd.read_csv(PERFORMANCE_HISTORY_DB, dtype=str)
                        if "Name" in hist_df.columns and "System Count" in hist_df.columns:
                            hist_df["System Count"] = pd.to_numeric(
                                hist_df["System Count"], errors="coerce"
                            ).fillna(0)
                            has_val = "Total Value" in hist_df.columns
                            if has_val:
                                hist_df["Total Value"] = pd.to_numeric(
                                    hist_df["Total Value"], errors="coerce"
                                ).fillna(0)

                            for _, row in hist_df.iterrows():
                                n        = str(row.get("Name", "")).strip()
                                date_str = str(row.get("Date", "")).strip()
                                if not n:
                                    continue
                                if active_date and date_str == active_date:
                                    continue  # already in session
                                if cutoff is not None and date_str:
                                    try:
                                        rd = datetime.datetime.strptime(
                                            date_str, "%d.%m.%Y"
                                        ).date()
                                        if rd < cutoff:
                                            continue
                                    except Exception:
                                        continue  # unparseable date — exclude when cutoff active
                                try:
                                    d_obj = datetime.datetime.strptime(
                                        date_str, "%d.%m.%Y"
                                    ).date()
                                except Exception:
                                    d_obj = None

                                # Backfill op_id for cashiers not in the current session
                                if n not in cashier_op_ids:
                                    op = str(row.get("Operator_Id", "")).strip()
                                    if op and op.lower() not in ("nan", "none", ""):
                                        cashier_op_ids[n] = op

                                slips = int(row.get("System Count", 0))
                                value = float(row.get("Total Value", 0)) if has_val else 0.0
                                all_cashiers.add(n)
                                hist_daily.setdefault(n, []).append((d_obj, slips, value))
                except Exception:
                    logging.exception("compute: loading history")

            # ── Targets from full history (unfiltered) ────────────────
            # Load the full history DB for target derivation regardless of scope
            full_hist_df = hist_df
            if hist_df is None and os.path.exists(PERFORMANCE_HISTORY_DB):
                try:
                    full_hist_df = pd.read_csv(PERFORMANCE_HISTORY_DB, dtype=str)
                except Exception:
                    pass
            target_slips, target_value = _compute_targets(full_hist_df)

            # ── Mistakes ──────────────────────────────────────────────
            mistakes_by_c = _mistakes_by_cashier(cutoff)

            # Group active-session mistakes by cashier (filter to report date)
            session_mistakes: dict = {}
            if active_date:
                for cashier, mlist in mistakes_by_c.items():
                    day_m = [m for m in mlist if m["date"] == active_date]
                    if day_m:
                        session_mistakes[cashier] = day_m

            # ── Build result rows ─────────────────────────────────────
            raw_rows = []

            for name in sorted(all_cashiers):
                op_id = cashier_op_ids.get(name, "")

                if session_only:
                    # ── Single session ────────────────────────────────
                    slips    = session_txn.get(name, 0)
                    value    = session_val.get(name, 0.0)
                    mistakes = session_mistakes.get(name, [])

                    sc = _score_one_session(
                        slips, value, op_id, mistakes, target_slips, target_value
                    )
                    sc["consistency"] = None  # explicitly N/A

                    raw_rows.append({
                        "name":          name,
                        "txn":           slips,
                        "value":         value,
                        "avg_val":       value / slips if slips else 0.0,
                        "slips_per_hr":  sc["slips_per_hr"],
                        "throughput":    sc["slips_per_hr"] / _TARGET_PER_HOUR,
                        "accuracy":      sc["acc_score"],
                        "consistency":   None,
                        "score":         int(round(sc["total"])),
                        "grade":         _grade(sc["total"]),
                        "breakdown":     sc,
                        "mistakes":      len(mistakes),
                        "penalty":       sc["penalty"],
                        "mistakes_list": mistakes,
                        "op_id":         op_id,
                        "sessions":      1,
                    })

                else:
                    # ── Multi-day ─────────────────────────────────────
                    daily_entries = []

                    # Add current session as one entry
                    if name in session_txn:
                        if active_date:
                            try:
                                sess_date = datetime.datetime.strptime(
                                    active_date, "%d.%m.%Y"
                                ).date()
                            except Exception:
                                sess_date = today
                        else:
                            sess_date = today
                        daily_entries.append((
                            sess_date,
                            session_txn[name],
                            session_val.get(name, 0.0),
                        ))

                    for entry in hist_daily.get(name, []):
                        daily_entries.append(entry)

                    if not daily_entries:
                        continue

                    # Group this cashier's mistakes by date string
                    cashier_mistakes = mistakes_by_c.get(name, [])
                    mistakes_by_date: dict = {}
                    for m in cashier_mistakes:
                        mistakes_by_date.setdefault(m["date"], []).append(m)

                    # Compute a base score for every working day
                    daily_scores = []
                    dated_daily  = []   # (date, base_score) for recency weighting
                    total_slips  = 0
                    total_value  = 0.0
                    all_mistakes_flat = list(cashier_mistakes)  # full period

                    for entry_date, slips, value in daily_entries:
                        date_str  = entry_date.strftime("%d.%m.%Y") if entry_date else ""
                        day_mist  = mistakes_by_date.get(date_str, [])
                        sc_day    = _score_one_session(
                            slips, value, op_id, day_mist, target_slips, target_value
                        )
                        daily_scores.append(sc_day["total"])
                        if entry_date:
                            dated_daily.append((entry_date, sc_day["total"]))
                        total_slips += slips
                        total_value += value

                    sessions = len(daily_entries)

                    # Consistency from spread of daily base scores
                    cons = _consistency_score(daily_scores)

                    # Period base score (recency-weighted for 3M/6M/12M)
                    if scope in _RECENCY and dated_daily:
                        period_base = _recency_weighted_avg(dated_daily, scope, today)
                    else:
                        period_base = (
                            sum(daily_scores) / len(daily_scores)
                            if daily_scores else 0.0
                        )

                    final_score = max(0.0, min(100.0, period_base + cons))

                    total_penalty = sum(m["points"] for m in all_mistakes_flat)

                    # Build period-level display breakdown (correct rates, not inflated)
                    hpd     = _shift_hours(op_id)
                    avg_spd = total_slips / sessions
                    avg_vpd = total_value / sessions
                    avg_sph = avg_spd / hpd if hpd else 0.0
                    thr_r   = avg_sph / _TARGET_PER_HOUR
                    per_err = len(all_mistakes_flat) / total_slips if total_slips else 0.0

                    d_thr   = round(min(float(_W_THROUGHPUT), min(thr_r, 1.2) * _W_THROUGHPUT), 1)
                    d_val   = round(min(float(_W_VALUE), (avg_vpd / target_value) * _W_VALUE if target_value else 0.0), 1)
                    d_slip  = round(min(float(_W_SLIPS), (avg_spd / target_slips) * _W_SLIPS if target_slips else 0.0), 1)
                    d_acc   = round(max(0.0, (1.0 - min(per_err, 1.0)) * _W_ACCURACY), 1)
                    d_clean = round(max(0.0, (1.0 - min(per_err, 1.0)) * _W_CLEAN_RATIO), 1)

                    sample_sc = {
                        "thr_score":    d_thr,
                        "val_score":    d_val,
                        "slip_score":   d_slip,
                        "acc_score":    d_acc,
                        "clean_score":  d_clean,
                        "consistency":  cons,
                        "penalty":      total_penalty,
                        "base":         round(d_thr + d_val + d_slip + d_acc + d_clean, 1),
                        "total":        round(final_score, 1),
                        "slips_per_hr": round(avg_sph, 2),
                        "mistake_count": len(all_mistakes_flat),
                    }

                    raw_rows.append({
                        "name":          name,
                        "txn":           total_slips,
                        "value":         total_value,
                        "avg_val":       total_value / total_slips if total_slips else 0.0,
                        "slips_per_hr":  sample_sc["slips_per_hr"],
                        "throughput":    sample_sc["slips_per_hr"] / _TARGET_PER_HOUR,
                        "accuracy":      sample_sc["acc_score"],
                        "consistency":   cons,
                        "score":         int(round(final_score)),
                        "grade":         _grade(final_score),
                        "breakdown":     sample_sc,
                        "mistakes":      len(all_mistakes_flat),
                        "penalty":       total_penalty,
                        "mistakes_list": all_mistakes_flat,
                        "op_id":         op_id,
                        "sessions":      sessions,
                        "period_base":   round(period_base, 1),
                    })

            if not raw_rows:
                self._no_data.setVisible(True)
                self._results_card.setVisible(False)
                self._pills_frame.setVisible(False)
                self._sort_frame.setVisible(False)
                self._perf_score_card.setVisible(False)
                return

            self._last_data = raw_rows

            # ── Update summary pills ──────────────────────────────────
            grades       = [r["grade"]   for r in raw_rows]
            total_txn    = sum(r["txn"]   for r in raw_rows)
            total_val    = sum(r["value"] for r in raw_rows)
            avg_score    = sum(r["score"] for r in raw_rows) / len(raw_rows)
            total_mist   = sum(r["mistakes"] for r in raw_rows)
            total_pen    = sum(r["penalty"]  for r in raw_rows)
            avg_rate     = sum(r["slips_per_hr"] for r in raw_rows) / len(raw_rows)

            self._pills["cashiers"].setText(str(len(raw_rows)))
            self._pills["total_txn"].setText(f"{total_txn:,}")
            self._pills["total_val"].setText(f"€{total_val:,.0f}")
            self._pills["avg_rate"].setText(f"{avg_rate:.1f}/hr")
            self._pills["avg_score"].setText(
                f"{avg_score:.0f} / {_grade(int(avg_score))}"
            )
            self._pills["grade_a"].setText(str(grades.count("A")))

            mist_color = Theme.DANGER if total_mist > 0 else Theme.TXT_3
            self._pills["mistakes"].setText(str(total_mist))
            self._pills["mistakes"].setStyleSheet(
                f"color:{mist_color};font-size:14px;font-weight:700;"
                f"font-family:Consolas,monospace;"
            )
            pen_color = Theme.DANGER if total_pen > 0 else Theme.TXT_3
            self._pills["penalties"].setText(
                f"−{total_pen}" if total_pen else "0"
            )
            self._pills["penalties"].setStyleSheet(
                f"color:{pen_color};font-size:14px;font-weight:700;"
                f"font-family:Consolas,monospace;"
            )
            self._pills_frame.setVisible(True)
            self._sort_frame.setVisible(True)

            # ── Team score circle ─────────────────────────────────────
            team_score  = int(avg_score)
            color       = (Theme.OK   if team_score >= 75 else
                           Theme.WARN if team_score >= 50 else Theme.DANGER)
            grade_label = _grade(team_score)
            grade_desc  = (
                "Outstanding team performance."                         if team_score >= 90 else
                "Good performance with room for improvement."           if team_score >= 75 else
                "Fair performance — several cashiers need attention."   if team_score >= 50 else
                "Poor performance — significant coaching required."
            )
            self._perf_score_circle.setText(str(team_score))
            self._perf_score_circle.setStyleSheet(
                f"color:{color};font-size:26px;font-weight:800;"
                f"background:{Theme.ELEVATED};border-radius:40px;"
                f"font-family:Consolas,monospace;border:2px solid {color};"
            )
            self._perf_score_desc.setText(
                f"Grade {grade_label} — {grade_desc}  "
                f"({grades.count('A')} A-grade, "
                f"{grades.count('F')} F-grade out of {len(raw_rows)} cashiers.)"
            )

            # Targets note
            self._targets_lbl.setText(
                f"Targets (from history)\n"
                f"Daily slips:  {target_slips:.0f}\n"
                f"Daily value:  €{target_value:,.0f}"
            )
            self._perf_score_card.setVisible(True)
            self._no_data.setVisible(False)
            self._render_rows(raw_rows)

        except Exception:
            logging.exception("CashierPerformancePage.compute")

    # ── Render rows ───────────────────────────────────────────────────────────
    def _render_rows(self, rows):
        while self._rows_lay.count():
            item = self._rows_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not rows:
            self._results_card.setVisible(False)
            return

        scope   = self._scope.currentText()
        reverse = not self._sort_asc

        if self._sort_col == "name":
            sorted_r = sorted(
                rows, key=lambda r: str(r.get("name", "")).lower(), reverse=reverse
            )
        elif self._sort_col == "accuracy":
            sorted_r = sorted(rows, key=lambda r: r.get("accuracy") or 0, reverse=reverse)
        elif self._sort_col == "consistency":
            sorted_r = sorted(rows, key=lambda r: r.get("consistency") or 0, reverse=reverse)
        elif self._sort_col == "mistakes":
            sorted_r = sorted(rows, key=lambda r: r.get("mistakes", 0), reverse=reverse)
        else:
            sorted_r = sorted(rows, key=lambda r: r.get(self._sort_col, 0), reverse=reverse)

        for i, r in enumerate(sorted_r):
            grade = r["grade"]
            color = _GRADE_COLOR[grade]

            # Background: alternating, red-tinted if there are penalties
            if r["penalty"] > 0:
                bg = "#1a0d0a" if i % 2 == 0 else "#1f1008"
            else:
                bg = "#090e18" if i % 2 == 0 else "#0e1628"

            row_f = _ClickableRow(r, scope)
            row_f.setStyleSheet(
                f"QFrame{{background:{bg};border-bottom:1px solid {Theme.BORDER_S};}}"
                f"QFrame:hover{{background:{Theme.HOVER};}}"
            )
            rl = QHBoxLayout(row_f)
            rl.setContentsMargins(18, 9, 18, 9); rl.setSpacing(0)

            # ── Cashier name ──────────────────────────────────────────
            nl = QLabel(r["name"])
            nl.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:500;")
            rl.addWidget(nl, 3)

            # ── Grade + Score ─────────────────────────────────────────
            gw = QWidget(); gw.setStyleSheet("background:transparent;")
            gl = QHBoxLayout(gw); gl.setContentsMargins(0, 0, 0, 0); gl.setSpacing(4)
            sl = QLabel(str(r["score"]))
            sl.setStyleSheet(
                f"color:{color};font-size:13px;font-weight:700;"
                f"font-family:Consolas,monospace;"
            )
            gp = QLabel(grade)
            gp.setStyleSheet(
                f"color:{color};font-size:8px;font-weight:700;"
                f"background:transparent;padding:2px 5px;"
                f"border:1px solid {color};border-radius:3px;"
            )
            gl.addWidget(sl); gl.addWidget(gp); gl.addStretch()
            rl.addWidget(gw, 1)

            def _cell(txt, clr=Theme.TXT_2, bold=False, stretch=1):
                lb = QLabel(txt)
                lb.setStyleSheet(
                    f"color:{clr};font-size:11px;font-family:Consolas,monospace;"
                    + ("font-weight:600;" if bold else "")
                )
                rl.addWidget(lb, stretch)

            # ── Slips ─────────────────────────────────────────────────
            _cell(f"{r['txn']:,}")

            # ── Value ─────────────────────────────────────────────────
            _cell(
                f"€{r['value']:,.0f}" if r["value"] else "—",
                clr=Theme.ACCENT if r["value"] > 0 else Theme.TXT_3,
                bold=r["value"] > 0,
            )

            # ── Throughput (two-line) ─────────────────────────────────
            sphr   = r["slips_per_hr"]
            tp_pct = r["throughput"] * 100
            tp_clr = (Theme.OK   if tp_pct >= 80 else
                      Theme.WARN if tp_pct >= 50 else Theme.DANGER)
            if r["txn"]:
                tp_w = QWidget(); tp_w.setStyleSheet("background:transparent;")
                tp_l = QVBoxLayout(tp_w)
                tp_l.setContentsMargins(0, 0, 0, 0); tp_l.setSpacing(0)
                rate_lbl = QLabel(f"{sphr:.1f}/hr")
                rate_lbl.setStyleSheet(
                    f"color:{tp_clr};font-size:11px;font-weight:600;"
                    f"font-family:Consolas,monospace;"
                )
                pct_lbl = QLabel(f"{tp_pct:.0f}% of target")
                pct_lbl.setStyleSheet(
                    f"color:{Theme.TXT_3};font-size:9px;font-family:Consolas,monospace;"
                )
                tp_l.addWidget(rate_lbl); tp_l.addWidget(pct_lbl)
                rl.addWidget(tp_w, 2)
            else:
                tp_lbl = QLabel("—")
                tp_lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
                rl.addWidget(tp_lbl, 2)

            # ── Accuracy ─────────────────────────────────────────────
            acc = r.get("accuracy") or 0
            acc_pct = acc / _W_ACCURACY if _W_ACCURACY else 0
            acc_clr = (Theme.OK   if acc_pct >= 0.8 else
                       Theme.WARN if acc_pct >= 0.5 else Theme.DANGER)
            _cell(f"{acc:.1f}/{_W_ACCURACY}", clr=acc_clr, bold=(acc_pct < 0.5))

            # ── Consistency ──────────────────────────────────────────
            cons = r.get("consistency")
            if cons is None:
                cons_lbl = QLabel("—")
                cons_lbl.setStyleSheet(
                    f"color:{Theme.TXT_3};font-size:11px;font-style:italic;"
                )
                cons_lbl.setToolTip("Consistency requires multi-day scope")
                rl.addWidget(cons_lbl, 1)
            else:
                cons_pct = cons / _W_CONSISTENCY if _W_CONSISTENCY else 0
                cons_clr = (Theme.OK   if cons_pct >= 0.8 else
                            Theme.WARN if cons_pct >= 0.5 else Theme.DANGER)
                _cell(f"{cons:.1f}/{_W_CONSISTENCY}", clr=cons_clr)

            # ── Mistakes ─────────────────────────────────────────────
            mc  = r.get("mistakes", 0)
            pen = r.get("penalty",  0)
            if mc > 0:
                m_w = QWidget(); m_w.setStyleSheet("background:transparent;")
                m_l = QVBoxLayout(m_w)
                m_l.setContentsMargins(0, 0, 0, 0); m_l.setSpacing(0)
                mc_lbl = QLabel(f"{mc} mistake{'s' if mc != 1 else ''}")
                mc_lbl.setStyleSheet(
                    f"color:{Theme.DANGER};font-size:11px;font-weight:600;"
                    f"font-family:Consolas,monospace;"
                )
                pen_lbl = QLabel(f"−{pen} pts")
                pen_lbl.setStyleSheet(
                    f"color:{Theme.DANGER};font-size:9px;"
                    f"font-family:Consolas,monospace;"
                )
                m_l.addWidget(mc_lbl); m_l.addWidget(pen_lbl)
                rl.addWidget(m_w, 1)
            else:
                clean_lbl = QLabel("✓ clean")
                clean_lbl.setStyleSheet(
                    f"color:{Theme.OK};font-size:11px;"
                    f"font-family:Consolas,monospace;"
                )
                rl.addWidget(clean_lbl, 1)

            self._rows_lay.addWidget(row_f)

        self._rows_lay.addStretch()
        self._results_card.setVisible(True)

    # ── Auto-show on tab switch ───────────────────────────────────────────────
    def showEvent(self, e):
        super().showEvent(e)
        df = getattr(self.app, "active_df", None)
        if df is None or df.empty:
            self._no_data.setVisible(True)
            self._results_card.setVisible(False)
            self._pills_frame.setVisible(False)
            self._sort_frame.setVisible(False)
            self._perf_score_card.setVisible(False)
        else:
            # Reset scope to "This Report" only on first visit; preserve selection on return
            if not getattr(self, "_ever_shown", False):
                self._scope.setCurrentIndex(0)
                self._ever_shown = True
            self.compute()

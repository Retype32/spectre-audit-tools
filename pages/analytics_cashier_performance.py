"""
pages/analytics_cashier_performance.py — Cashier Performance Analytics.

Display only: every number comes from engine.performance (which days count,
each day's targets) and scoring.py (the per-day score):

  Slips per hour  50 pts — vs 25/hr (VMS); lower on days when all bags were cleared
  Cash volume     10 pts — vs the team's average cash per hour that day (capped)
  Accuracy        20 pts — (1 − mistake_rate) × 20
  Consistency     10 pts — score stability over time (multi-day scopes only)
  Clean Ratio     10 pts — % of slips untouched by any mistake
  minus mistake penalties (a confirmed duplicate is the most serious, −20)

360 processing days and non-VMS (e.g. ISA) days are listed but not scored.
Recency weighting (3M / 6M / 12M views): most recent third 50 %, middle 30 %,
oldest 20 %.
"""
import datetime
import logging

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QComboBox, QScrollArea, QDialog, QLineEdit,
    QFormLayout, QDialogButtonBox, QDateEdit, QMessageBox,
    QSizePolicy,
)

from config import MISTAKE_TYPES
from theme import Theme

from engine.performance import compute_performance, log_mistake, sort_rows, team_summary
from engine.volume import available_months, current_month, monthly_volume
from scoring import (
    penalty_summary as _penalty_summary,
    _W_SLIP_RATE, _W_CASH,
    _W_ACCURACY, _W_CONSISTENCY, _W_CLEAN_RATIO, SCOPES,
)
from widgets import DataTable

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
        notes  = self._notes.text().strip()
        try:
            log_mistake(date_val, cashier, type_key, notes)
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
            ("Slips / hour", bd.get("rate_score", 0), _W_SLIP_RATE,   Theme.ACCENT),
            ("Cash volume",  bd.get("cash_score", 0), _W_CASH,         Theme.INFO),
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


# ── Monthly cash volume dialog ────────────────────────────────────────────────

class MonthlyVolumeDialog(QDialog):
    """Cash volume per cashier for one month, highest cash per hour first."""

    COLUMNS = ("Cashier", "Days", "Slips", "Cash €", "Cash/day €", "Cash/hr €",
               "Slips/hr", "Speed ±%", "Cash/slip €", "Size ±%",
               "360 days", "360 cash €", "Other days")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Monthly Cash Volume")
        self.resize(1340, 560)
        self.setStyleSheet(f"QDialog{{background:{Theme.BG};color:{Theme.TXT};}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16); lay.setSpacing(10)

        top = QHBoxLayout()
        top.addWidget(QLabel("Month:"))
        self._month = QComboBox()
        months = available_months() or [current_month()]
        for m in months:
            self._month.addItem(m)
        self._month.currentTextChanged.connect(self._load)
        top.addWidget(self._month)
        top.addStretch()
        lay.addLayout(top)

        note = QLabel(
            "Cash per hour = slips per hour × cash per slip.  'Speed ±%' compares slips per "
            "hour with the team, 'Size ±%' compares cash per slip (lodgement size) — together "
            "they show why a cashier's cash rate is high or low.  360 and non-VMS (other) days "
            "are left out of the rates."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
        lay.addWidget(note)

        self._summary = QLabel()
        self._summary.setStyleSheet(f"color:{Theme.TXT_2};font-size:12px;")
        lay.addWidget(self._summary)

        self._table = DataTable(self.COLUMNS)
        for col in self.COLUMNS:
            self._table.set_column_width(col, 170 if col == "Cashier" else 92)
        lay.addWidget(self._table, 1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn)
        self._load(self._month.currentText())

    @staticmethod
    def _pct(v):
        return None if v is None else int(round(v))

    def _load(self, month):
        self._table.clear()
        try:
            data = monthly_volume(month)
        except Exception as e:
            logging.exception("MonthlyVolumeDialog._load")
            self._summary.setText(f"Could not read the history: {e}")
            return
        t = data["team"]
        self._summary.setText(
            f"{month}:  {t['cashiers']} cashiers  ·  {t['working_days']} working days  ·  "
            f"€{t['cash']:,.0f} cash  ·  team €{t['cash_per_hour']:,.0f}/hr, "
            f"{t['slips_per_hour']:.1f} slips/hr, €{t['cash_per_slip']:,.0f}/slip"
            + (f"  ·  360: {t['days_360']} day(s), €{t['cash_360']:,.0f}" if t["days_360"] else ""))
        # Raw numbers (not text) so clicking a column header sorts correctly
        for r in data["rows"]:
            self._table.add_row({
                "Cashier": r["name"], "Days": r["days"], "Slips": r["slips"],
                "Cash €": int(round(r["cash"])), "Cash/day €": int(round(r["cash_per_day"])),
                "Cash/hr €": int(round(r["cash_per_hour"])),
                "Slips/hr": round(r["slips_per_hour"], 1),
                "Speed ±%": self._pct(r["slips_per_hour_vs_team_pct"]),
                "Cash/slip €": int(round(r["cash_per_slip"])),
                "Size ±%": self._pct(r["cash_per_slip_vs_team_pct"]),
                "360 days": r["days_360"], "360 cash €": int(round(r["cash_360"])),
                "Other days": r["days_other"],
            })
        self._table.sortByColumn(self.COLUMNS.index("Cash/hr €"), Qt.DescendingOrder)


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

        self._month_btn = QPushButton("Monthly Cash Volume")
        self._month_btn.setFixedHeight(34)
        self._month_btn.setMinimumWidth(150)
        self._month_btn.clicked.connect(self._open_monthly_volume)

        hdr.addWidget(scope_lbl)
        hdr.addWidget(self._scope)
        hdr.addWidget(self._month_btn)
        hdr.addWidget(self._log_btn)
        hdr.addWidget(run_btn)
        root.addLayout(hdr)

        sub = QLabel(
            "Scores each cashier on slips per hour first, with a small bonus for keeping up "
            "with the team's cash, plus accuracy, consistency and clean work.  360 processing "
            "and non-VMS days are listed but not scored.  Click any row to see the full score "
            "breakdown.  Mistakes are logged with  + Log Mistake  and applied automatically."
        )
        sub.setStyleSheet(f"color:{Theme.TXT_3};font-size:12px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # ── Methodology card ──────────────────────────────────────────
        meth_card, meth_lay = _card("Performance Score Methodology")

        # Fairness note
        fair_lbl = QLabel(
            "Slips are measured against 25 per hour (lower on days when every bag was "
            "cleared). Cash only adds a small bonus for keeping up with the team's average."
        )
        fair_lbl.setStyleSheet(
            f"color:{Theme.OK};font-size:10px;font-weight:600;"
            f"letter-spacing:0.2px;"
        )
        meth_lay.addWidget(fair_lbl)

        # Component pills row
        pill_row = QHBoxLayout(); pill_row.setSpacing(6)
        for label, pts, color in [
            ("Slips per hour\nvs 25/hr (VMS)",   "50 pts", Theme.ACCENT),
            ("Cash volume\nvs team average",     "10 pts", Theme.INFO),
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

        self._unscored_lbl = QLabel()
        self._unscored_lbl.setWordWrap(True)
        self._unscored_lbl.setVisible(False)
        self._unscored_lbl.setStyleSheet(
            f"color:{Theme.TXT_2};font-size:11px;background:{Theme.SURFACE};"
            f"border:1px solid {Theme.BORDER_S};border-radius:8px;padding:10px 14px;"
        )
        root.addWidget(self._unscored_lbl)

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
            scope  = self._scope.currentText()
            result = compute_performance(
                df, scope, active_date=getattr(self.app, "_active_report_date", None),
                report_fmt=getattr(self.app, "_active_report_fmt", "VMS"),
            )
            if result is None:          # report has no "Cashier Name" column
                return
            raw_rows = result.rows
            self._show_unscored(result)

            if not raw_rows:
                self._no_data.setVisible(True)
                self._results_card.setVisible(False)
                self._pills_frame.setVisible(False)
                self._sort_frame.setVisible(False)
                self._perf_score_card.setVisible(False)
                return

            self._last_data = raw_rows

            # ── Update summary pills ──────────────────────────────────
            team         = team_summary(raw_rows)
            grades       = [r["grade"] for r in raw_rows]
            total_txn    = team["total_txn"]
            total_val    = team["total_value"]
            avg_score    = team["avg_score"]
            total_mist   = team["total_mistakes"]
            total_pen    = team["total_penalty"]
            avg_rate     = team["avg_rate"]

            self._pills["cashiers"].setText(str(len(raw_rows)))
            self._pills["total_txn"].setText(f"{total_txn:,}")
            self._pills["total_val"].setText(f"€{total_val:,.0f}")
            self._pills["avg_rate"].setText(f"{avg_rate:.1f}/hr")
            self._pills["avg_score"].setText(
                f"{avg_score:.0f} / {team['team_grade']}"
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
            team_score  = team["team_score"]
            color       = (Theme.OK   if team_score >= 75 else
                           Theme.WARN if team_score >= 50 else Theme.DANGER)
            grade_label = team["team_grade"]
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
            rate = result.target_per_hour
            src = "set by manager" if result.target_sources.get("per_hour") == "manager" else "default"
            logged = [d for d in result.days if d["bags"] is not None]
            cleared = [d for d in logged if d["cleared"]]
            lines = [
                "Targets",
                f"Slips/hr:  {rate:g}  ({src})",
                f"Per day:  {rate * 8:g} (8 hr) / {rate * 10:g} (10 hr)",
                "Cash:  vs team average that day",
            ]
            if logged:
                lines.append(f"Bags cleared:  {len(cleared)} of {len(logged)} logged day(s)")
            self._targets_lbl.setText("\n".join(lines))
            self._perf_score_card.setVisible(True)
            self._no_data.setVisible(False)
            self._render_rows(raw_rows)

        except Exception:
            logging.exception("CashierPerformancePage.compute")

    def _show_unscored(self, result):
        """List 360 / non-VMS cashier-days that are not scored."""
        if not result.unscored:
            self._unscored_lbl.setVisible(False)
            return
        parts = []
        for u in result.unscored[:12]:
            kind = "360" if u["kind"] == "360" else u["format"]
            parts.append(f"{u['name']} ({kind}, {u['date']}: {u['slips']} slips, "
                         f"€{u['value']:,.0f})")
        more = len(result.unscored) - 12
        self._unscored_lbl.setText(
            "Not scored — 360 processing or non-VMS work:  " + "  ·  ".join(parts)
            + (f"  ·  +{more} more" if more > 0 else ""))
        self._unscored_lbl.setVisible(True)

    def _open_monthly_volume(self):
        MonthlyVolumeDialog(self).exec()

    # ── Render rows ───────────────────────────────────────────────────────────
    def _render_rows(self, rows):
        while self._rows_lay.count():
            item = self._rows_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not rows:
            self._results_card.setVisible(False)
            return

        scope    = self._scope.currentText()
        sorted_r = sort_rows(rows, self._sort_col, ascending=self._sort_asc)

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
            self._unscored_lbl.setVisible(False)
        else:
            self._scope.setCurrentIndex(0)
            self.compute()

"""
pages/analytics_risk_panels.py — Shared constants, helpers, and the three
panel sections of the Risk Scoring tab.

Extracted from analytics_risk.py so each section lives in its own logical
unit.  No import from analytics_risk.py — all shared state is passed in via
the risk_page parameter.
"""
import datetime
import os

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QScrollArea, QSizePolicy,
)

from config import AMOUNT, PERFORMANCE_HISTORY_DB
from theme import Theme


# ── Risk score weights (raw) ──────────────────────────────────────────────────
_W_DUP, _W_SUS, _W_SHR, _W_HIST, _W_SLIP = 45, 8, 5, 10, 5
_MAX_WEIGHT = _W_DUP + _W_SUS + _W_SHR + _W_HIST + _W_SLIP   # 73

# Display percentages (rounded, sum = 100) shown in the methodology card
_DISP_WEIGHTS = [62, 11, 7, 13, 7]

# ── Risk band definitions: (background, accent-colour, label) ─────────────────
BAND_HIGH   = ("#162440", "#3d7fff", "HIGH RISK")
BAND_MEDIUM = ("#0e1628", "#93b8ff", "MEDIUM")
BAND_LOW    = ("#090e18", "#4d9fff", "LOW")


def _band(score):
    """Return the (bg, accent, label) tuple for a given risk score."""
    if score >= 61: return BAND_HIGH
    if score >= 31: return BAND_MEDIUM
    return BAND_LOW


def _card_frame():
    f = QFrame()
    f.setStyleSheet(
        f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
    )
    return f


# =============================================================================
# Tab-bar + Benchmarking panel
# =============================================================================

def attach_benchmarking(risk_page):
    """Build and attach the Benchmarking and Score Guide tabs to risk_page."""

    # ── Tab bar ───────────────────────────────────────────────────────────────
    toggle_row = QHBoxLayout(); toggle_row.setSpacing(0)
    tab_defs = [
        ("Risk Scores", "scores", "border-radius:6px 0 0 6px"),
        ("Benchmarking", "bench", "border-radius:0"),
        ("Score Guide",  "guide", "border-radius:0 6px 6px 0"),
    ]
    for lbl, key, radius in tab_defs:
        btn = QPushButton(lbl)
        btn.setCheckable(True)
        btn.setChecked(key == "scores")
        btn.setFixedHeight(32)
        btn._active_style = (
            f"QPushButton{{background:{risk_page._theme_accent()};color:#ffffff;"
            f"border:none;font-size:11px;font-weight:700;{radius};}}"
        )
        btn._idle_style = (
            f"QPushButton{{background:{Theme.ELEVATED};color:{Theme.TXT_3};"
            f"border:1px solid {Theme.BORDER};font-size:11px;font-weight:500;{radius};}}"
            f"QPushButton:hover{{color:{Theme.TXT_2};}}"
        )
        btn.setStyleSheet(btn._active_style if key == "scores" else btn._idle_style)
        toggle_row.addWidget(btn)
        risk_page._tab_btns[key] = btn
    toggle_row.addStretch()

    # Insert toggle before the methodology card (index 1, after the header row)
    risk_page.layout().insertLayout(1, toggle_row)

    # ── Benchmarking widget (hidden initially) ────────────────────────────────
    bench_w = QWidget(); bench_w.setStyleSheet("background:transparent;")
    bench_w.setVisible(False)
    bench_lay = QVBoxLayout(bench_w)
    bench_lay.setContentsMargins(0, 0, 0, 0); bench_lay.setSpacing(8)

    info = QLabel(
        "Compares each cashier against the group average across key metrics. "
        "Values highlighted in blue are above average."
    )
    info.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
    info.setWordWrap(True)
    bench_lay.addWidget(info)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
    bench_inner = QWidget(); bench_inner.setStyleSheet("background:transparent;")
    bench_inner_lay = QVBoxLayout(bench_inner)
    bench_inner_lay.setContentsMargins(0, 0, 0, 0); bench_inner_lay.setSpacing(4)
    scroll.setWidget(bench_inner)
    bench_lay.addWidget(scroll, 1)

    risk_page._bench_widget    = bench_w
    risk_page._bench_inner_lay = bench_inner_lay
    risk_page.layout().addWidget(bench_w)

    # ── Score Guide widget (hidden initially) ─────────────────────────────────
    guide_w = _build_score_guide_widget(risk_page)
    guide_w.setVisible(False)
    risk_page._guide_widget = guide_w
    risk_page.layout().addWidget(guide_w)

    # ── Wire tab buttons ──────────────────────────────────────────────────────
    def _switch(key):
        risk_page._results_widget.setVisible(key == "scores")
        risk_page._bench_widget.setVisible(key == "bench")
        risk_page._guide_widget.setVisible(key == "guide")
        for k, b in risk_page._tab_btns.items():
            b.setStyleSheet(b._active_style if k == key else b._idle_style)
            b.setChecked(k == key)
        if key == "bench":
            refresh_benchmarking(risk_page)
        elif key == "guide":
            refresh_recommendations(risk_page)

    risk_page._tab_btns["scores"].clicked.connect(lambda: _switch("scores"))
    risk_page._tab_btns["bench"].clicked.connect(lambda: _switch("bench"))
    risk_page._tab_btns["guide"].clicked.connect(lambda: _switch("guide"))


def refresh_benchmarking(risk_page):
    """Populate the benchmarking table.

    Respects the same scope/cutoff as the Risk Scores tab.
    """
    lay = risk_page._bench_inner_lay
    while lay.count():
        item = lay.takeAt(0)
        if item.widget(): item.widget().deleteLater()

    df = getattr(risk_page.app, "active_df", None)
    if df is None or df.empty or "Cashier Name" not in df.columns:
        lbl = QLabel("No report loaded.")
        lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:12px;padding:20px;")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)
        return

    # ── Determine scope from the dropdown ─────────────────────────────────────
    timeline     = risk_page._timeline_combo.currentText()
    session_only = (timeline == "This Report")
    cutoff       = None
    today        = datetime.date.today()
    if timeline == "Today":
        cutoff = today
    elif timeline == "This Week":
        cutoff = today - datetime.timedelta(days=7)
    elif timeline == "This Month":
        cutoff = datetime.date(today.year, today.month, 1)

    active_date = getattr(risk_page.app, "_active_report_date", None)

    # ── Build per-cashier txn/value totals (session + history) ────────────────
    txn_totals = {}
    val_totals = {}

    if AMOUNT in df.columns:
        for name, grp in df.groupby("Cashier Name"):
            n = str(name)
            txn_totals[n] = txn_totals.get(n, 0) + len(grp)
            val_totals[n] = val_totals.get(n, 0.0) + float(grp[AMOUNT].sum())

    if not session_only and os.path.exists(PERFORMANCE_HISTORY_DB):
        try:
            sh = pd.read_csv(PERFORMANCE_HISTORY_DB, dtype=str)
            sh["System Count"] = pd.to_numeric(
                sh.get("System Count", pd.Series()), errors="coerce"
            ).fillna(0)
            sh["Total Value"] = pd.to_numeric(
                sh.get("Total Value", pd.Series()), errors="coerce"
            ).fillna(0)
            for _, row in sh.iterrows():
                n        = str(row.get("Name", "")).strip()
                row_date = str(row.get("Date", "")).strip()
                if not n:
                    continue
                if active_date and row_date == active_date:
                    continue
                if cutoff is not None and row_date:
                    try:
                        rd = datetime.datetime.strptime(row_date, "%d.%m.%Y").date()
                        if rd < cutoff:
                            continue
                    except Exception:
                        pass
                txn_totals[n] = txn_totals.get(n, 0) + int(row.get("System Count", 0))
                val_totals[n] = val_totals.get(n, 0.0) + float(row.get("Total Value", 0))
        except Exception:
            pass

    avg_val_map = {
        n: (val_totals[n] / txn_totals[n]) if txn_totals.get(n, 0) else 0.0
        for n in txn_totals
    }

    if AMOUNT not in df.columns:
        lay.addStretch()
        return

    dup_c = {}
    for rd in getattr(risk_page.app, "_exact_dup_rows", []):
        n = rd.get("Cashier Name", rd.get("Cashier", ""))
        dup_c[n] = dup_c.get(n, 0) + 1
    sus_c = {}
    for rd in getattr(risk_page.app, "_sus_rows", []):
        n = rd.get("Cashier Name", rd.get("Cashier", ""))
        sus_c[n] = sus_c.get(n, 0) + 1

    cashiers = sorted(set(txn_totals.keys()) | set(df["Cashier Name"].unique().tolist()))

    group_avg_txn = sum(txn_totals.values()) / max(len(cashiers), 1)
    group_avg_val = sum(val_totals.values()) / max(len(cashiers), 1)
    group_avg_amt = sum(avg_val_map.values()) / max(len(avg_val_map), 1)
    group_avg_dup = sum(dup_c.values()) / max(len(cashiers), 1)
    group_avg_sus = sum(sus_c.values()) / max(len(cashiers), 1)

    # Header
    hdr = QWidget(); hdr.setStyleSheet("background:transparent;")
    hl  = QHBoxLayout(hdr); hl.setContentsMargins(12, 0, 12, 4); hl.setSpacing(0)
    for txt, stretch in [("Cashier", 3), ("Transactions", 1), ("Total Value", 1),
                         ("Avg Amount", 1), ("Duplicates", 1), ("Suspicious", 1)]:
        l = QLabel(txt)
        l.setStyleSheet(
            f"color:{Theme.TXT_DIM};font-size:9px;font-weight:700;letter-spacing:1.5px;"
        )
        hl.addWidget(l, stretch)
    lay.addWidget(hdr)

    for i, name in enumerate(cashiers):
        n    = str(name)
        txn  = int(txn_totals.get(n, 0))
        totv = float(val_totals.get(n, 0.0))
        avgv = float(avg_val_map.get(n, 0.0))
        dups = dup_c.get(n, 0)
        sus  = sus_c.get(n, 0)

        rw = QFrame()
        rw.setStyleSheet(
            f"QFrame{{background:{'#090e18' if i % 2 == 0 else '#0e1628'};"
            f"border-radius:4px;margin:1px 0;}}"
        )
        rl = QHBoxLayout(rw); rl.setContentsMargins(12, 7, 12, 7); rl.setSpacing(0)

        def _cell(val_str, is_above, stretch, _rl=rl):
            l = QLabel(val_str)
            l.setStyleSheet(
                f"color:{Theme.ACCENT if is_above else Theme.TXT_2};"
                f"font-size:11px;font-family:Consolas,monospace;"
                + ("font-weight:700;" if is_above else "")
            )
            _rl.addWidget(l, stretch)

        nl = QLabel(n); nl.setStyleSheet(f"color:{Theme.TXT};font-size:12px;")
        rl.addWidget(nl, 3)
        _cell(str(txn),        txn  > group_avg_txn, 1)
        _cell(f"€{totv:,.0f}", totv > group_avg_val, 1)
        _cell(f"€{avgv:,.2f}", avgv > group_avg_amt, 1)
        _cell(str(dups) if dups else "—", dups > group_avg_dup, 1)
        _cell(str(sus)  if sus  else "—", sus  > group_avg_sus, 1)
        lay.addWidget(rw)

    # Group average footer
    foot = QFrame()
    foot.setStyleSheet(
        f"QFrame{{background:{Theme.SELECTED};border:1px solid {Theme.BORDER};"
        f"border-radius:4px;margin-top:4px;}}"
    )
    fl = QHBoxLayout(foot); fl.setContentsMargins(12, 7, 12, 7); fl.setSpacing(0)
    al = QLabel("GROUP AVERAGE")
    al.setStyleSheet(
        f"color:{Theme.TXT_3};font-size:10px;font-weight:700;letter-spacing:1px;"
    )
    fl.addWidget(al, 3)
    for val, stretch in [
        (f"{group_avg_txn:.1f}", 1),
        (f"€{group_avg_val:,.0f}", 1),
        (f"€{group_avg_amt:,.2f}", 1),
        (f"{group_avg_dup:.1f}", 1),
        (f"{group_avg_sus:.1f}", 1),
    ]:
        l = QLabel(val)
        l.setStyleSheet(
            f"color:{Theme.TXT_2};font-size:11px;"
            f"font-family:Consolas,monospace;font-weight:600;"
        )
        fl.addWidget(l, stretch)
    lay.addWidget(foot)

    lay.addStretch()


# =============================================================================
# Score Guide panel
# =============================================================================

def _build_score_guide_widget(risk_page):
    """Build the static Score Guide panel (band meanings, signal guide, recommendations)."""
    outer = QWidget(); outer.setStyleSheet("background:transparent;")
    lay = QVBoxLayout(outer); lay.setContentsMargins(0, 0, 0, 24); lay.setSpacing(12)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
    inner = QWidget(); inner.setStyleSheet("background:transparent;")
    il = QVBoxLayout(inner); il.setContentsMargins(0, 0, 0, 0); il.setSpacing(12)
    scroll.setWidget(inner)
    lay.addWidget(scroll, 1)

    # ── Band interpretation card ──────────────────────────────────────────────
    band_card = _card_frame()
    bl = QVBoxLayout(band_card); bl.setContentsMargins(18, 14, 18, 16); bl.setSpacing(10)
    t = QLabel("What Your Score Means")
    t.setStyleSheet(f"color:{Theme.TXT};font-size:13px;font-weight:700;")
    bl.addWidget(t)
    div = QFrame(); div.setFixedHeight(1)
    div.setStyleSheet(f"background:{Theme.BORDER_S};")
    bl.addWidget(div)

    bands = [
        ("0 – 20",   "TARGET ZONE",  Theme.ACCENT,  Theme.ELEVATED,
         "Clean operation. No significant patterns detected. Continue standard monitoring "
         "and periodic spot-checks. This is where everyone should be."),
        ("21 – 30",  "LOW",          Theme.INFO,    Theme.ELEVATED,
         "Low-level signals present. Likely operational noise — customer-provided slip numbers, "
         "minor coincidences. Monitor for upward trends across reports."),
        ("31 – 45",  "MEDIUM",       Theme.WARN,    "#0e1628",
         "Real signals are firing. At least one signal type is consistently elevated. "
         "Recommended action: informal one-on-one review with the cashier's manager within the month."),
        ("46 – 60",  "MEDIUM-HIGH",  Theme.GOLD,    "#0e1520",
         "Multiple signals elevated or one signal is dominant. Active monitoring required. "
         "Schedule a formal review within 7 days. Begin documenting findings."),
        ("61 – 100", "HIGH RISK",    Theme.DANGER,  "#162440",
         "Formal investigation required. Escalate to management immediately. Do not wait for "
         "the next report cycle. High Risk scores indicate patterns that do not occur by chance."),
    ]
    for rng, label, color, bg, desc in bands:
        row = QFrame()
        row.setStyleSheet(
            f"QFrame{{background:{bg};border-radius:6px;border:1px solid {Theme.BORDER_S};}}"
        )
        rl = QHBoxLayout(row); rl.setContentsMargins(14, 10, 14, 10); rl.setSpacing(12)

        score_col = QWidget(); score_col.setStyleSheet("background:transparent;")
        sc_lay = QVBoxLayout(score_col); sc_lay.setContentsMargins(0, 0, 0, 0); sc_lay.setSpacing(2)
        score_col.setFixedWidth(80)
        rng_lbl = QLabel(rng)
        rng_lbl.setStyleSheet(
            f"color:{color};font-size:14px;font-weight:700;font-family:Consolas,monospace;"
        )
        band_lbl2 = QLabel(label)
        band_lbl2.setStyleSheet(
            f"color:{color};font-size:8px;font-weight:700;letter-spacing:1.5px;"
        )
        sc_lay.addWidget(rng_lbl); sc_lay.addWidget(band_lbl2)
        rl.addWidget(score_col)

        sep = QFrame(); sep.setFixedWidth(1); sep.setStyleSheet(f"background:{color};")
        rl.addWidget(sep)

        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color:{Theme.TXT_2};font-size:11px;line-height:140%;")
        rl.addWidget(desc_lbl, 1)
        bl.addWidget(row)

    target = QFrame()
    target.setStyleSheet(
        f"QFrame{{background:#0a1f3a;border:1px solid {Theme.ACCENT};"
        f"border-left:4px solid {Theme.ACCENT};border-radius:6px;}}"
    )
    tl = QHBoxLayout(target); tl.setContentsMargins(16, 12, 16, 12); tl.setSpacing(10)
    star = QLabel("★")
    star.setStyleSheet(f"color:{Theme.ACCENT};font-size:18px;")
    msg = QLabel(
        "Business target: <b>all cashiers scoring below 20.</b>  "
        "Any cashier consistently above 30 across multiple report cycles warrants a formal review, "
        "regardless of whether they are currently in the HIGH RISK band."
    )
    msg.setWordWrap(True)
    msg.setStyleSheet(f"color:{Theme.TXT};font-size:11px;")
    tl.addWidget(star); tl.addWidget(msg, 1)
    bl.addWidget(target)
    il.addWidget(band_card)

    # ── Signal breakdown card ─────────────────────────────────────────────────
    sig_card = _card_frame()
    sl = QVBoxLayout(sig_card); sl.setContentsMargins(18, 14, 18, 16); sl.setSpacing(10)
    t2 = QLabel("What Drives Each Signal")
    t2.setStyleSheet(f"color:{Theme.TXT};font-size:13px;font-weight:700;")
    sl.addWidget(t2)
    div2 = QFrame(); div2.setFixedHeight(1)
    div2.setStyleSheet(f"background:{Theme.BORDER_S};")
    sl.addWidget(div2)

    signals = [
        (f"{_DISP_WEIGHTS[0]}%", "High Risk Duplicates",     Theme.DANGER, Theme.ELEVATED,
         "Identical transaction processed more than once by the same cashier. One confirmed pair "
         "is a serious event. First, verify whether the slip number was provided by the customer "
         "or entered manually. If manually entered and duplicated — escalate."),
        (f"{_DISP_WEIGHTS[1]}%", "Suspicious Patterns",      Theme.WARN,   Theme.ELEVATED,
         "Repeated round-amount transactions, clustering at specific times, or sequences that "
         "match known fraud patterns. A low score here alone is rarely conclusive — look for it "
         "combined with other signals before drawing conclusions."),
        (f"{_DISP_WEIGHTS[2]}%", "Shared Wallet Incidents",  Theme.GOLD,   Theme.ELEVATED,
         "Multiple cashiers handling the same customer wallet. This is often a legitimate customer "
         "request, but repeated incidents involving the same cashier warrant verification. Confirm "
         "with the customer that they authorised each transaction."),
        (f"{_DISP_WEIGHTS[3]}%", "Historical Discrepancies", Theme.INFO,   Theme.ELEVATED,
         "Discrepancies logged across previous audit reports. A cashier with a long clean history "
         "who suddenly scores here has had a change in behaviour — worth investigating the timing. "
         "A cashier who has always had low discrepancies is a different concern."),
        (f"{_DISP_WEIGHTS[4]}%", "Slip Audit Mismatches",    Theme.TXT_2,  Theme.ELEVATED,
         "Physical slip count does not match the digital record for this cashier. Occasional "
         "mismatches are operational. Repeated mismatches in the same direction (always short, "
         "or always over) is a pattern that requires reconciliation."),
    ]
    for weight, name, color, bg, desc in signals:
        row = QFrame()
        row.setStyleSheet(
            f"QFrame{{background:{bg};border-radius:6px;border:1px solid {Theme.BORDER_S};}}"
        )
        rl = QHBoxLayout(row); rl.setContentsMargins(14, 10, 14, 10); rl.setSpacing(12)
        wl = QLabel(weight)
        wl.setFixedWidth(38)
        wl.setStyleSheet(
            f"color:{color};font-size:15px;font-weight:700;font-family:Consolas,monospace;"
        )
        sep = QFrame(); sep.setFixedWidth(1); sep.setStyleSheet(f"background:{color};")
        text_col = QWidget(); text_col.setStyleSheet("background:transparent;")
        tcl = QVBoxLayout(text_col); tcl.setContentsMargins(0, 0, 0, 0); tcl.setSpacing(2)
        nl = QLabel(name); nl.setStyleSheet(f"color:{color};font-size:11px;font-weight:700;")
        dl = QLabel(desc); dl.setWordWrap(True)
        dl.setStyleSheet(f"color:{Theme.TXT_3};font-size:10.5px;")
        tcl.addWidget(nl); tcl.addWidget(dl)
        rl.addWidget(wl); rl.addWidget(sep); rl.addWidget(text_col, 1)
        sl.addWidget(row)
    il.addWidget(sig_card)

    # ── Recommendations placeholder (populated dynamically) ───────────────────
    rec_card = _card_frame()
    rl2 = QVBoxLayout(rec_card); rl2.setContentsMargins(18, 14, 18, 16); rl2.setSpacing(8)
    t3 = QLabel("Cashier Recommendations")
    t3.setStyleSheet(f"color:{Theme.TXT};font-size:13px;font-weight:700;")
    rl2.addWidget(t3)
    div3 = QFrame(); div3.setFixedHeight(1)
    div3.setStyleSheet(f"background:{Theme.BORDER_S};")
    rl2.addWidget(div3)
    placeholder = QLabel(
        "Click  Calculate Scores  on the Risk Scores tab first, then return here."
    )
    placeholder.setAlignment(Qt.AlignCenter)
    placeholder.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;padding:20px;")
    rl2.addWidget(placeholder)
    il.addWidget(rec_card)

    risk_page._guide_rec_card   = rec_card
    risk_page._guide_rec_layout = rl2

    return outer


def refresh_recommendations(risk_page):
    """Populate the per-cashier recommendations section from _last_scores."""
    lay = risk_page._guide_rec_layout

    # Remove everything after the divider (index 0=title, 1=divider)
    while lay.count() > 2:
        item = lay.takeAt(lay.count() - 1)
        if item.widget(): item.widget().deleteLater()

    scores = getattr(risk_page, "_last_scores", [])
    if not scores:
        ph = QLabel(
            "Click  Calculate Scores  on the Risk Scores tab first, then return here."
        )
        ph.setAlignment(Qt.AlignCenter)
        ph.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;padding:20px;")
        lay.addWidget(ph)
        return

    for name, score, dups, sus, shared, hist, slip in scores:
        _, accent, band_lbl = _band(score)

        rec_f = QFrame()
        rec_f.setStyleSheet(
            f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER_S};"
            f"border-left:3px solid {accent};border-radius:6px;margin:2px 0;}}"
        )
        fl = QVBoxLayout(rec_f); fl.setContentsMargins(16, 10, 16, 10); fl.setSpacing(6)

        top = QHBoxLayout()
        nl = QLabel(name)
        nl.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:600;")
        sl2 = QLabel(f"{score}  {band_lbl}")
        sl2.setStyleSheet(
            f"color:{accent};font-size:11px;font-weight:700;"
            f"font-family:Consolas,monospace;letter-spacing:0.5px;"
        )
        top.addWidget(nl); top.addStretch(); top.addWidget(sl2)
        fl.addLayout(top)

        bullets = []
        if score < 20:
            bullets.append(("Clean. No action required. Continue standard monitoring.", Theme.TXT_3))
        else:
            if score >= 61:
                bullets.append((
                    "PRIORITY: IMMEDIATE — Escalate to management and begin formal investigation.",
                    Theme.DANGER,
                ))
            elif score >= 46:
                bullets.append((
                    "PRIORITY: HIGH — Schedule a formal review within 7 days. Begin documentation.",
                    Theme.GOLD,
                ))
            elif score >= 31:
                bullets.append((
                    "PRIORITY: MODERATE — Schedule an informal review with the cashier's manager.",
                    Theme.WARN,
                ))
            else:
                bullets.append((
                    "Monitor — review at next report cycle to check for upward trend.",
                    Theme.INFO,
                ))

            if dups:
                bullets.append((
                    f"Duplicates ({dups} row{'s' if dups > 1 else ''}): Confirm whether slip numbers were "
                    f"customer-provided or manually entered. If manually entered and duplicated — escalate.",
                    Theme.DANGER,
                ))
            if sus:
                bullets.append((
                    f"Suspicious patterns ({sus}): Check for round-amount clustering or timing sequences. "
                    f"Cross-reference with any duplicate signals.",
                    Theme.WARN,
                ))
            if shared:
                bullets.append((
                    f"Shared wallet ({shared}): Verify with the affected customer(s) that each transaction "
                    f"was authorised.",
                    Theme.GOLD,
                ))
            if hist:
                bullets.append((
                    f"Historical discrepancies ({hist}): Review the audit trail for timing patterns — "
                    f"same day of week, same customer, or same shift.",
                    Theme.INFO,
                ))
            if slip:
                bullets.append((
                    f"Slip mismatches ({slip}): Reconcile physical slips against the digital log. "
                    f"Check whether mismatches are consistently in the same direction.",
                    Theme.TXT_2,
                ))

        for text, color in bullets:
            brow = QHBoxLayout(); brow.setSpacing(8)
            dot = QLabel("•")
            dot.setFixedWidth(12)
            dot.setStyleSheet(f"color:{color};font-size:14px;font-weight:700;")
            txt_lbl = QLabel(text)
            txt_lbl.setWordWrap(True)
            txt_lbl.setStyleSheet(
                f"color:{color if color != Theme.TXT_3 else Theme.TXT_3};font-size:10.5px;"
            )
            brow.addWidget(dot, 0, Qt.AlignTop)
            brow.addWidget(txt_lbl, 1)
            fl.addLayout(brow)

        lay.addWidget(rec_f)

    lay.addStretch()

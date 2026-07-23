"""
pages/analytics_visual_report.py — Visual Report Generator.

Produces a polished multi-page PDF or a chart-rich Excel workbook from the
current session's data.  No external files required — everything is drawn
inline using openpyxl chart objects and reportlab vector primitives.

Touches nothing outside this file.
"""

import logging
import os
import math
import datetime
import glob

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
    QPushButton, QFileDialog, QCheckBox, QScrollArea,
    QProgressBar, QApplication
)

from config import AMOUNT, DISCREPANCY_DB_PATH, APP_VERSION
from theme import Theme


# ── colour palette (kept inside this file — self-contained) ──────────────────
_BLUES = ["#4d9fff", "#74b5ff", "#2d7dd6", "#93b8ff", "#a8c8ff",
          "#1a5fa8", "#60c8ff", "#3d7fff", "#b8d4ff", "#0e3d7a"]
_BG    = "#05070d"
_SURF  = "#0d1117"
_ELEV  = "#141923"
_TXT   = "#dde8f5"
_TXT2  = "#7a96b8"
_TXT3  = "#3d5470"
_ACCNT = "#4d9fff"
_OK    = "#60c8ff"
_WARN  = "#93b8ff"
_DNGR  = "#3d7fff"


# ═══════════════════════════════════════════════════════════════════════════════
# EXCEL GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_excel(app, path, options):
    """Build a focused audit .xlsx report (6 sheets)."""
    # ── Light professional palette for Excel readability ──────────────────────
    _BG    = "#F8FAFF"   # page background (white-blue tint)
    _SURF  = "#EEF4FF"   # card surface
    _ELEV  = "#E2EDF9"   # elevated / alternating row
    _TXT   = "#1A2A45"   # primary dark text
    _TXT2  = "#3A5070"   # secondary text
    _TXT3  = "#6A86A8"   # muted labels
    _ACCNT = "#2B4A8A"   # accent blue
    _OK    = "#1A6A30"   # green
    _WARN  = "#8A5A0A"   # amber
    _DNGR  = "#8A1A1A"   # red
    # Risk row backgrounds (light, for readability on screen and print)
    _RISK_HIGH = "#FDEAEA"   # light red
    _RISK_MED  = "#FFF4E0"   # light amber

    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from openpyxl.chart import BarChart, LineChart, Reference
    from openpyxl.utils import get_column_letter

    from config import (LODGEMENT, COL_DISC, OPERATOR, CUSTOMER_ID, CUSTOMER_LOC,
                        CUSTOMER_DISC_DB, DISCREPANCY_DB_PATH)

    wb  = openpyxl.Workbook()
    wb.remove(wb.active)

    df       = getattr(app, "active_df", None)
    dup_rows = getattr(app, "_exact_dup_rows", [])
    sus_rows = getattr(app, "_sus_rows",       [])
    shr_rows = getattr(app, "_shared_wallet_rows", [])

    # ── helpers ───────────────────────────────────────────────────────────────
    def _hex(h):   return h.lstrip("#")
    def _fill(h):  return PatternFill("solid", fgColor=_hex(h))
    def _font(color=_TXT, size=10, bold=False):
        return Font(color=_hex(color), size=size, bold=bold)
    def _center(): return Alignment(horizontal="center", vertical="center", wrap_text=True)
    def _left():   return Alignment(horizontal="left",   vertical="center", wrap_text=True)
    def _border(): return Border(bottom=Side(style="thin", color=_hex("#C0CDE0")))

    def _title_row(ws, row, text, subtitle=""):
        ws.row_dimensions[row].height = 34
        c = ws.cell(row, 1, text)
        c.font = Font(color=_hex(_ACCNT), size=16, bold=True)
        c.alignment = _left(); c.fill = _fill(_SURF)
        if subtitle:
            ws.cell(row, 2, subtitle).font = _font(_TXT2, 10)

    def _section_hdr(ws, row, text, ncols=8):
        ws.row_dimensions[row].height = 20
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
        c = ws.cell(row, 1, text.upper())
        c.font = Font(color=_hex(_TXT3), size=8, bold=True)
        c.alignment = _left(); c.fill = _fill(_BG)

    def _kpi(ws, sr, sc, label, value, color=_ACCNT):
        for r in range(sr, sr + 3):
            for c in range(sc, sc + 2):
                ws.cell(r, c).fill = _fill(_ELEV)
        ws.row_dimensions[sr].height     = 8
        ws.row_dimensions[sr + 1].height = 28
        ws.row_dimensions[sr + 2].height = 14
        lc = ws.cell(sr + 2, sc, label)
        lc.font = Font(color=_hex(_TXT3), size=8, bold=True)
        lc.alignment = _center()
        ws.merge_cells(start_row=sr+2, start_column=sc, end_row=sr+2, end_column=sc+1)
        vc = ws.cell(sr + 1, sc, value)
        vc.font = Font(color=_hex(color), size=18, bold=True)
        vc.alignment = _center()
        ws.merge_cells(start_row=sr+1, start_column=sc, end_row=sr+1, end_column=sc+1)

    def _col_w(ws, mapping):
        for col, w in mapping.items():
            ws.column_dimensions[get_column_letter(col)].width = w

    def _chart_series(chart, color):
        if chart.series:
            chart.series[0].graphicalProperties.solidFill     = _hex(color)
            chart.series[0].graphicalProperties.line.solidFill = _hex(color)

    # ── Sheet 1: Executive Summary ────────────────────────────────────────────
    if options.get("summary", True):
        ws = wb.create_sheet("Executive Summary")
        ws.sheet_view.showGridLines = False
        ws.sheet_properties.tabColor = _hex(_ACCNT)
        _col_w(ws, {1:2,2:16,3:16,4:16,5:16,6:16,7:16,8:16,9:16,10:16})

        # Title banner
        for r in range(1, 4):
            ws.row_dimensions[r].height = 18
            for c in range(1, 11): ws.cell(r, c).fill = _fill(_SURF)
        ws.merge_cells("B1:J3")
        tc = ws["B1"]
        tc.value = f"{APP_VERSION}  —  Audit Intelligence Report"
        tc.font  = Font(color=_hex(_ACCNT), size=18, bold=True); tc.alignment = _left()
        ws.merge_cells("B4:J4")
        sc = ws["B4"]
        sc.value = (f"Generated {datetime.datetime.now():%d %B %Y  %H:%M}"
                    + (f"   ·   {len(df):,} transactions" if df is not None else ""))
        sc.font = _font(_TXT2, 10); sc.alignment = _left()
        ws.row_dimensions[4].height = 16

        n_rows  = len(df) if df is not None else 0
        n_cash  = df["Cashier Name"].nunique() if df is not None and "Cashier Name" in df.columns else 0
        tot_val = df[AMOUNT].sum() if df is not None and AMOUNT in df.columns else 0
        n_slips = df[LODGEMENT].nunique() if df is not None and LODGEMENT in df.columns else 0
        n_anom  = len(dup_rows)//2 + len(sus_rows)//2 + len(shr_rows)

        ws.row_dimensions[5].height = 10
        _kpi(ws, 6, 2, "TRANSACTIONS", f"{n_rows:,}",      _ACCNT)
        _kpi(ws, 6, 4, "TOTAL SLIPS",  f"{n_slips:,}",     _OK)
        _kpi(ws, 6, 6, "TOTAL VALUE",  f"€{tot_val:,.0f}", _WARN)
        _kpi(ws, 6, 8, "CASHIERS",     str(n_cash),        _ACCNT)
        ws.row_dimensions[10].height = 16

        # Anomaly summary table
        _section_hdr(ws, 11, "Anomaly Summary", 5)
        hdr = 12
        ws.row_dimensions[hdr].height = 18
        for ci, h in enumerate(["Type", "Count (pairs)", "% of Transactions"], 2):
            c = ws.cell(hdr, ci, h)
            c.font = Font(color=_hex(_TXT3), size=8, bold=True)
            c.fill = _fill(_BG); c.alignment = _center()
        anom_rows = [
            ("High Risk Duplicates",    len(dup_rows)//2, _DNGR),
            ("Suspicious Patterns",     len(sus_rows)//2, _WARN),
            ("Shared Wallet Incidents", len(shr_rows),    _OK),
        ]
        for ri, (lbl, cnt, color) in enumerate(anom_rows):
            r = hdr + 1 + ri
            ws.row_dimensions[r].height = 16
            bg = _fill(_ELEV if ri % 2 == 0 else _SURF)
            pct = f"{cnt/n_rows*100:.2f}%" if n_rows else "—"
            for ci, val in enumerate([lbl, cnt if cnt else "—", pct], 2):
                c = ws.cell(r, ci, val)
                c.fill = bg; c.border = _border()
                c.alignment = _center() if ci > 2 else _left()
                c.font = _font(color if ci == 2 else _TXT, 10)
        _kpi(ws, hdr + 5, 2, "TOTAL ANOMALIES", str(n_anom), _DNGR if n_anom else _OK)

    # ── Sheet 2: Cashier Performance ──────────────────────────────────────────
    if options.get("performance", True) and df is not None and "Cashier Name" in df.columns:
        ws = wb.create_sheet("Cashier Performance")
        ws.sheet_view.showGridLines = False
        ws.sheet_properties.tabColor = _hex(_OK)
        _col_w(ws, {1:2,2:24,3:14,4:14,5:16,6:14,7:12})

        _title_row(ws, 1, "Cashier Performance", "Volume, value, and slip counts per cashier")
        ws.merge_cells("B1:G1")

        # Build data
        grp_val   = df.groupby("Cashier Name")[AMOUNT].agg(["sum","mean","count"])
        grp_val.columns = ["Total_Value","Avg_Value","Transactions"]
        if LODGEMENT in df.columns:
            grp_slips = df.groupby("Cashier Name")[LODGEMENT].nunique().rename("Slips")
        else:
            grp_slips = df.groupby("Cashier Name").size().rename("Slips")
        perf = grp_val.join(grp_slips, how="left").fillna(0)
        perf["Pct_Val"] = perf["Total_Value"] / (perf["Total_Value"].sum() or 1) * 100
        perf = perf.sort_values("Total_Value", ascending=False)

        _section_hdr(ws, 3, "Per-Cashier Breakdown", 7)
        hdr = 4; ws.row_dimensions[hdr].height = 18
        for ci, h in enumerate(["Cashier","Transactions","Slip Count",
                                 "Total Value","Avg Value","% of Total Value"], 2):
            c = ws.cell(hdr, ci, h)
            c.font = Font(color=_hex(_TXT3), size=8, bold=True)
            c.fill = _fill(_BG); c.alignment = _center()
        for ri, (name, row) in enumerate(perf.iterrows()):
            r = hdr + 1 + ri
            ws.row_dimensions[r].height = 16
            bg = _fill(_ELEV if ri % 2 == 0 else _SURF)
            for ci, val in enumerate([str(name), int(row["Transactions"]),
                                       int(row["Slips"]), f"€{row['Total_Value']:,.2f}",
                                       f"€{row['Avg_Value']:,.2f}", f"{row['Pct_Val']:.1f}%"], 2):
                c = ws.cell(r, ci, val)
                c.fill = bg; c.border = _border()
                c.alignment = _center() if ci > 2 else _left()
                c.font = _font(_ACCNT if ci == 5 else _TXT, 10, ci == 5)
        data_end = hdr + len(perf)

        # Chart: top 10 by value
        top10v = perf.head(10)
        cs = data_end + 3
        _section_hdr(ws, cs, "Top 10 Cashiers — By Value", 7)
        cr = cs + 1; ws.cell(cr, 2, "Cashier").font = _font(_TXT3, 8, True)
        ws.cell(cr, 3, "Total Value").font = _font(_TXT3, 8, True)
        for ri, (name, row) in enumerate(top10v.iterrows()):
            r = cr + 1 + ri
            ws.cell(r, 2, str(name)).font = _font(_TXT, 9)
            ws.cell(r, 3, round(float(row["Total_Value"]), 2)).font = _font(_ACCNT, 9)
            ws.cell(r, 3).number_format = '#,##0.00'
        vc = BarChart(); vc.type = "bar"; vc.grouping = "clustered"
        vc.title = "Total Value per Cashier"; vc.y_axis.title = "€ Value"
        vc.style = 2; vc.width = 20; vc.height = 12
        vc.add_data(Reference(ws, min_col=3, min_row=cr, max_row=cr+len(top10v)), titles_from_data=True)
        vc.set_categories(Reference(ws, min_col=2, min_row=cr+1, max_row=cr+len(top10v)))
        _chart_series(vc, _ACCNT); ws.add_chart(vc, f"E{cs}")

        # Chart: top 10 by slips
        top10s = perf.sort_values("Slips", ascending=False).head(10)
        cs2 = cs + len(top10v) + 4
        _section_hdr(ws, cs2, "Top 10 Cashiers — By Slip Count", 7)
        cr2 = cs2 + 1; ws.cell(cr2, 2, "Cashier").font = _font(_TXT3, 8, True)
        ws.cell(cr2, 3, "Slip Count").font = _font(_TXT3, 8, True)
        for ri, (name, row) in enumerate(top10s.iterrows()):
            r = cr2 + 1 + ri
            ws.cell(r, 2, str(name)).font = _font(_TXT, 9)
            ws.cell(r, 3, int(row["Slips"])).font = _font(_OK, 9)
        sc2 = BarChart(); sc2.type = "bar"; sc2.grouping = "clustered"
        sc2.title = "Slip Count per Cashier"; sc2.y_axis.title = "Slips"
        sc2.style = 2; sc2.width = 20; sc2.height = 12
        sc2.add_data(Reference(ws, min_col=3, min_row=cr2, max_row=cr2+len(top10s)), titles_from_data=True)
        sc2.set_categories(Reference(ws, min_col=2, min_row=cr2+1, max_row=cr2+len(top10s)))
        _chart_series(sc2, _OK); ws.add_chart(sc2, f"E{cs2}")

    # ── Sheet 3: Risk Intelligence ────────────────────────────────────────────
    if options.get("risk", True) and df is not None and "Cashier Name" in df.columns:
        ws = wb.create_sheet("Risk Intelligence")
        ws.sheet_view.showGridLines = False
        ws.sheet_properties.tabColor = _hex(_DNGR)
        _col_w(ws, {1:2,2:22,3:10,4:10,5:10,6:10,7:10,8:10})

        _title_row(ws, 1, "Risk Intelligence", "Cashier risk scores — Dup 66%  Sus 12%  Shared 7%  Hist 15%")
        ws.merge_cells("B1:H1")

        dup_c = {}
        for rd in dup_rows:
            n = rd.get("Cashier Name", rd.get("Cashier", ""))
            dup_c[n] = dup_c.get(n, 0) + 1
        sus_c = {}
        for rd in sus_rows:
            n = rd.get("Cashier Name", rd.get("Cashier", ""))
            sus_c[n] = sus_c.get(n, 0) + 1
        shr_c = {}
        for rd in shr_rows:
            n = rd.get("Cashier Name", rd.get("Cashier", ""))
            shr_c[n] = shr_c.get(n, 0) + 1
        hist_c = {}
        try:
            for fp in glob.glob(os.path.join(DISCREPANCY_DB_PATH, "**", "*.xlsx"), recursive=True):
                tmp = pd.read_excel(fp)
                if "Cashier Name" in tmp.columns and "Small_Discrepancies" in tmp.columns:
                    for _, row in tmp.iterrows():
                        n = str(row["Cashier Name"])
                        hist_c[n] = hist_c.get(n, 0) + int(row.get("Small_Discrepancies", 0))
        except Exception:
            pass
        mx = lambda d: max(d.values(), default=1) or 1
        scores = []
        for name in df["Cashier Name"].unique():
            n = str(name)
            raw = (45*(dup_c.get(n,0)/mx(dup_c)) + 8*(sus_c.get(n,0)/mx(sus_c)) +
                    5*(shr_c.get(n,0)/mx(shr_c)) + 10*(hist_c.get(n,0)/mx(hist_c)))
            s = min(100, int(raw * 100 / 68))
            scores.append((n, s, dup_c.get(n,0)//2, sus_c.get(n,0)//2,
                           shr_c.get(n,0), hist_c.get(n,0)))
        scores.sort(key=lambda x: x[1], reverse=True)

        _section_hdr(ws, 3, "Cashier Risk Scores", 8)
        hdr = 4; ws.row_dimensions[hdr].height = 18
        for ci, h in enumerate(["Cashier","Score","Band","Duplicates",
                                 "Suspicious","Shared","Hist. Disc."], 2):
            c = ws.cell(hdr, ci, h)
            c.font = Font(color=_hex(_TXT3), size=8, bold=True)
            c.fill = _fill(_BG); c.alignment = _center()
        for ri, (name, score, dups, sus, shr, hist) in enumerate(scores):
            r = hdr + 1 + ri; ws.row_dimensions[r].height = 16
            band  = "HIGH" if score >= 61 else "MEDIUM" if score >= 31 else "LOW"
            color = _DNGR if score >= 61 else _WARN if score >= 31 else _OK
            bg    = _fill(_RISK_HIGH if score >= 61 else _RISK_MED if score >= 31 else _SURF)
            for ci, val in enumerate([name, score, band, dups or "—",
                                       sus or "—", shr or "—", hist or "—"], 2):
                c = ws.cell(r, ci, val)
                c.fill = bg; c.alignment = _center() if ci > 2 else _left()
                c.border = _border()
                c.font = (Font(color=_hex(color), size=10, bold=True)
                          if ci in (3, 4) else _font(_TXT, 10))

        cs = hdr + len(scores) + 3
        _section_hdr(ws, cs, "Anomaly Composition per Cashier", 8)
        cr = cs + 1
        for ci, h in enumerate(["Cashier","Duplicates","Suspicious","Shared"], 2):
            ws.cell(cr, ci, h).font = _font(_TXT3, 8, True)
        for ri, (name, _, dups, sus, shr, _) in enumerate(scores[:15]):
            r = cr + 1 + ri; ws.row_dimensions[r].height = 14
            ws.cell(r, 2, name).font = _font(_TXT, 9)
            ws.cell(r, 3, dups).font = _font(_DNGR, 9)
            ws.cell(r, 4, sus).font  = _font(_WARN,  9)
            ws.cell(r, 5, shr).font  = _font(_OK,    9)
        stk = BarChart(); stk.type = "bar"; stk.grouping = "stacked"
        stk.title = "Anomaly Composition"; stk.y_axis.title = "Count"
        stk.style = 2; stk.width = 20; stk.height = 12
        nr = min(15, len(scores))
        for col_idx in [3, 4, 5]:
            stk.add_data(Reference(ws, min_col=col_idx, min_row=cr,
                                   max_row=cr+nr), titles_from_data=True)
        stk.set_categories(Reference(ws, min_col=2, min_row=cr+1, max_row=cr+nr))
        for i, color in enumerate([_DNGR, _WARN, _OK]):
            if len(stk.series) > i:
                stk.series[i].graphicalProperties.solidFill     = _hex(color)
                stk.series[i].graphicalProperties.line.solidFill = _hex(color)
        ws.add_chart(stk, f"G{cs+1}")

    # ── Sheet 4: Customer Analysis ────────────────────────────────────────────
    if options.get("customers", True) and df is not None and CUSTOMER_ID in df.columns:
        ws = wb.create_sheet("Customer Analysis")
        ws.sheet_view.showGridLines = False
        ws.sheet_properties.tabColor = _hex(_WARN)
        _col_w(ws, {1:2,2:16,3:20,4:12,5:12,6:12,7:14,8:14})

        _title_row(ws, 1, "Customer Analysis",
                   "Customer ID · Location · Discrepancies (≤€10) · Not declaring")
        ws.merge_cells("B1:H1")

        has_disc = COL_DISC in df.columns
        has_loc  = CUSTOMER_LOC in df.columns
        if has_disc:
            df2 = df.copy()
            df2[COL_DISC] = pd.to_numeric(df2[COL_DISC], errors="coerce").fillna(0)
            df2[AMOUNT]   = pd.to_numeric(df2[AMOUNT],   errors="coerce").fillna(0)

            cust_rows = []
            for cid, grp in df2.groupby(CUSTOMER_ID):
                loc = ""
                if has_loc:
                    ls = grp[CUSTOMER_LOC].dropna().astype(str)
                    loc = ls.mode().iloc[0] if not ls.empty else ""
                all_disc = grp[grp[COL_DISC].abs() > 0]
                small    = grp[(grp[COL_DISC].abs() > 0) & (grp[COL_DISC].abs() <= 10)]
                not_decl = grp[(grp[AMOUNT] > 0) &
                               ((grp[COL_DISC].abs() - grp[AMOUNT].abs()).abs() < 0.01)]
                cust_rows.append({
                    "CustId":    str(cid), "Location": loc, "Txns": len(grp),
                    "All_Disc":  len(all_disc), "Small_Disc": len(small),
                    "Small_Amt": float(small[COL_DISC].abs().sum()),
                    "Not_Decl":  len(not_decl),
                    "Disc_Rate": len(all_disc)/len(grp)*100 if len(grp) else 0,
                })
            cust_df = pd.DataFrame(cust_rows)

            # Section A — top customers by all discrepancies
            _section_hdr(ws, 3, "Top Customers — All Discrepancies (This Report)", 8)
            hdr_a = 4; ws.row_dimensions[hdr_a].height = 18
            for ci, h in enumerate(["Customer ID","Location","Transactions",
                                     "All Disc","Disc Rate %","Small Disc",
                                     "Small Disc Amt"], 2):
                c = ws.cell(hdr_a, ci, h)
                c.font = Font(color=_hex(_TXT3), size=8, bold=True)
                c.fill = _fill(_BG); c.alignment = _center()
            top_disc = (cust_df[cust_df["All_Disc"] > 0]
                        .sort_values("All_Disc", ascending=False).head(25))
            for ri, (_, row) in enumerate(top_disc.iterrows()):
                r = hdr_a + 1 + ri; ws.row_dimensions[r].height = 15
                bg = _fill(_ELEV if ri % 2 == 0 else _SURF)
                hi = _DNGR if row["All_Disc"] > 5 else _WARN if row["All_Disc"] > 2 else _TXT
                for ci, val in enumerate([
                    row["CustId"], row["Location"], int(row["Txns"]),
                    int(row["All_Disc"]), f"{row['Disc_Rate']:.1f}%",
                    int(row["Small_Disc"]), f"€{row['Small_Amt']:.2f}"
                ], 2):
                    c = ws.cell(r, ci, val)
                    c.fill = bg; c.border = _border()
                    c.alignment = _center() if ci > 3 else _left()
                    c.font = _font(hi if ci == 5 else _TXT, 10)

            # Section B — location hotspots
            if has_loc:
                loc_stats = (df2.assign(_disc=df2[COL_DISC].abs() > 0)
                               .groupby(CUSTOMER_LOC)
                               .agg(Txns=("_disc", "count"),
                                    All_Disc=("_disc", "sum"))
                               .reset_index()
                               .sort_values("All_Disc", ascending=False))
                sec_b = hdr_a + len(top_disc) + 4
                _section_hdr(ws, sec_b, "Location Hotspots — Discrepancies by Customer Location", 5)
                hdr_b = sec_b + 1; ws.row_dimensions[hdr_b].height = 18
                for ci, h in enumerate(["Location","Transactions","All Discrepancies","Disc Rate %"], 2):
                    c = ws.cell(hdr_b, ci, h)
                    c.font = Font(color=_hex(_TXT3), size=8, bold=True)
                    c.fill = _fill(_BG); c.alignment = _center()
                for ri, (_, row) in enumerate(loc_stats.iterrows()):
                    r = hdr_b + 1 + ri; ws.row_dimensions[r].height = 15
                    bg  = _fill(_ELEV if ri % 2 == 0 else _SURF)
                    pct = float(row["All_Disc"]) / float(row["Txns"]) * 100 if row["Txns"] else 0
                    hi  = _DNGR if row["All_Disc"] > 10 else _WARN if row["All_Disc"] > 4 else _TXT
                    for ci, val in enumerate([row[CUSTOMER_LOC], int(row["Txns"]),
                                              int(row["All_Disc"]), f"{pct:.1f}%"], 2):
                        c = ws.cell(r, ci, val)
                        c.fill = bg; c.border = _border()
                        c.alignment = _center() if ci > 2 else _left()
                        c.font = _font(hi if ci == 4 else _TXT, 10)
                sec_c_base = sec_b + len(loc_stats) + 4
            else:
                sec_c_base = hdr_a + len(top_disc) + 4

            # Section C — not declaring
            _section_hdr(ws, sec_c_base, "Customers Not Declaring Amounts  (Expected = 0, Processed > 0)", 6)
            hdr_c = sec_c_base + 1; ws.row_dimensions[hdr_c].height = 18
            for ci, h in enumerate(["Customer ID","Location","Occurrences","Total Undeclared Value"], 2):
                c = ws.cell(hdr_c, ci, h)
                c.font = Font(color=_hex(_TXT3), size=8, bold=True)
                c.fill = _fill(_BG); c.alignment = _center()
            nd_df = cust_df[cust_df["Not_Decl"] > 0].sort_values("Not_Decl", ascending=False)
            if nd_df.empty:
                ws.cell(hdr_c+1, 2, "No undeclared-amount customers in this report.").font = _font(_TXT3, 10)
            else:
                for ri, (_, row) in enumerate(nd_df.iterrows()):
                    r = hdr_c + 1 + ri; ws.row_dimensions[r].height = 15
                    bg      = _fill(_ELEV if ri % 2 == 0 else _SURF)
                    nd_rows = df2[(df2[CUSTOMER_ID] == row["CustId"]) &
                                  (df2[AMOUNT] > 0) &
                                  ((df2[COL_DISC].abs() - df2[AMOUNT].abs()).abs() < 0.01)]
                    undecl  = float(nd_rows[AMOUNT].sum())
                    for ci, val in enumerate([row["CustId"], row["Location"],
                                              int(row["Not_Decl"]), f"€{undecl:,.2f}"], 2):
                        c = ws.cell(r, ci, val)
                        c.fill = bg; c.border = _border()
                        c.alignment = _center() if ci > 3 else _left()
                        c.font = _font(_DNGR if ci >= 4 else _TXT, 10)
        else:
            ws.cell(3, 2, "No Discrepancy column found in the imported report.").font = _font(_TXT3, 11)

    # ── Sheet 5: Small Discrepancy Trends ────────────────────────────────────
    if options.get("trends", True):
        ws = wb.create_sheet("Small Disc Trends")
        ws.sheet_view.showGridLines = False
        ws.sheet_properties.tabColor = _hex(_DNGR)
        _col_w(ws, {1:2,2:14,3:16,4:2})

        _title_row(ws, 1, "Small Discrepancy Trends",
                   "Unapproved amounts ≤ €10 — all-time archive")
        ws.merge_cells("B1:D1")

        monthly_data  = {}
        cashier_tots  = {}
        cashier_rpts  = {}
        try:
            for fp in glob.glob(os.path.join(DISCREPANCY_DB_PATH, "**", "*.xlsx"),
                                recursive=True):
                try:
                    tmp = pd.read_excel(fp)
                    if "Small_Discrepancies" not in tmp.columns:
                        continue
                    mkey = None
                    if "Report_Date" in tmp.columns:
                        try:
                            dt   = pd.to_datetime(str(tmp["Report_Date"].iloc[0]), dayfirst=True)
                            mkey = dt.strftime("%b %y")
                        except Exception:
                            pass
                    mkey = mkey or os.path.basename(os.path.dirname(fp))
                    monthly_data[mkey] = monthly_data.get(mkey, 0) + int(tmp["Small_Discrepancies"].sum())
                    if "Cashier Name" in tmp.columns:
                        for _, row in tmp.iterrows():
                            cn = str(row["Cashier Name"])
                            cashier_tots[cn] = cashier_tots.get(cn, 0) + int(row.get("Small_Discrepancies", 0))
                            cashier_rpts[cn] = cashier_rpts.get(cn, 0) + 1
                except Exception:
                    pass
        except Exception:
            pass

        _section_hdr(ws, 3, "Monthly Small Discrepancy Events", 4)
        hdr_m = 4; ws.row_dimensions[hdr_m].height = 18
        ws.cell(hdr_m, 2, "Month").font  = _font(_TXT3, 8, True)
        ws.cell(hdr_m, 3, "Events").font = _font(_TXT3, 8, True)
        if monthly_data:
            def _ms(k):
                try:    return datetime.datetime.strptime(k, "%b %y")
                except: return datetime.datetime.min
            sorted_m = sorted(monthly_data.items(), key=lambda x: _ms(x[0]))[-24:]
            for ri, (month, cnt) in enumerate(sorted_m):
                r = hdr_m + 1 + ri; ws.row_dimensions[r].height = 14
                ws.cell(r, 2, month).font = _font(_TXT, 10)
                ws.cell(r, 3, cnt).font   = _font(_DNGR if cnt > 10 else _WARN, 10)
            line = LineChart()
            line.title = "Small Discrepancy Events — Monthly"; line.y_axis.title = "Events"
            line.style = 2; line.width = 20; line.height = 10
            line.add_data(Reference(ws, min_col=3, min_row=hdr_m,
                                    max_row=hdr_m+len(sorted_m)), titles_from_data=True)
            line.set_categories(Reference(ws, min_col=2, min_row=hdr_m+1,
                                          max_row=hdr_m+len(sorted_m)))
            if line.series:
                line.series[0].graphicalProperties.line.solidFill = _hex(_DNGR)
                line.series[0].graphicalProperties.line.width = 25000
                line.series[0].marker.symbol = "circle"
                line.series[0].marker.size   = 5
            ws.add_chart(line, "E3")
            trend_end = hdr_m + len(sorted_m) + 4
        else:
            ws.cell(hdr_m+1, 2, "No archive data found.").font = _font(_TXT3, 10)
            trend_end = hdr_m + 4

        _section_hdr(ws, trend_end, "All-Time Cashier Ranking — Cumulative Small Discrepancies", 4)
        hdr_c = trend_end + 1; ws.row_dimensions[hdr_c].height = 18
        ws.cell(hdr_c, 2, "Cashier").font          = _font(_TXT3, 8, True)
        ws.cell(hdr_c, 3, "Cumulative Events").font = _font(_TXT3, 8, True)
        if cashier_tots:
            for ri, (cn, total) in enumerate(
                sorted(cashier_tots.items(), key=lambda x: x[1], reverse=True)[:25]
            ):
                r = hdr_c + 1 + ri; ws.row_dimensions[r].height = 14
                bg = _fill(_ELEV if ri % 2 == 0 else _SURF)
                color = _DNGR if total > 10 else _WARN if total > 4 else _OK
                ws.cell(r, 2, cn).fill   = bg; ws.cell(r, 2).font = _font(_TXT, 10)
                ws.cell(r, 3, total).fill = bg; ws.cell(r, 3).font = _font(color, 10, total > 10)
        else:
            ws.cell(hdr_c+1, 2, "No cashier data in archive.").font = _font(_TXT3, 10)

    # ── Sheet 6: Cashier Discrepancy Profile ──────────────────────────────────
    if options.get("discprofile", True) and df is not None:
        ws = wb.create_sheet("Discrepancy Profile")
        ws.sheet_view.showGridLines = False
        ws.sheet_properties.tabColor = _hex(_OK)
        _col_w(ws, {1:2,2:22,3:14,4:14,5:16,6:16,7:14})

        _title_row(ws, 1, "Cashier Discrepancy Profile",
                   "This report + all-time small discrepancy history")
        ws.merge_cells("B1:G1")

        has_disc = COL_DISC in df.columns
        if has_disc:
            df3 = df.copy()
            df3[COL_DISC] = pd.to_numeric(df3[COL_DISC], errors="coerce").fillna(0)
            df3[AMOUNT]   = pd.to_numeric(df3[AMOUNT],   errors="coerce").fillna(0)

            _section_hdr(ws, 3, "This Report — Small Discrepancies per Cashier", 7)
            hdr = 4; ws.row_dimensions[hdr].height = 18
            for ci, h in enumerate(["Cashier","Transactions","Small Disc Events",
                                     "Total Small Amount","Not Decl. Customers","Disc Rate %"], 2):
                c = ws.cell(hdr, ci, h)
                c.font = Font(color=_hex(_TXT3), size=8, bold=True)
                c.fill = _fill(_BG); c.alignment = _center()

            if "Cashier Name" in df3.columns:
                cashier_data = []
                for cashier, grp in df3.groupby("Cashier Name"):
                    small    = grp[(grp[COL_DISC].abs() > 0) & (grp[COL_DISC].abs() <= 10)]
                    not_decl = grp[(grp[AMOUNT] > 0) &
                                   ((grp[COL_DISC].abs() - grp[AMOUNT].abs()).abs() < 0.01)]
                    cashier_data.append({
                        "Cashier": str(cashier), "Txns": len(grp),
                        "Small_Events": len(small),
                        "Small_Amount": float(small[COL_DISC].abs().sum()),
                        "Not_Decl": len(not_decl),
                        "Rate": len(small)/len(grp)*100 if len(grp) else 0,
                    })
                cashier_data.sort(key=lambda x: x["Small_Events"], reverse=True)
                for ri, row in enumerate(cashier_data):
                    r = hdr + 1 + ri; ws.row_dimensions[r].height = 16
                    bg = _fill(_ELEV if ri % 2 == 0 else _SURF)
                    hi = _DNGR if row["Small_Events"] > 5 else _WARN if row["Small_Events"] > 2 else _TXT
                    for ci, val in enumerate([
                        row["Cashier"], row["Txns"], row["Small_Events"],
                        f"€{row['Small_Amount']:.2f}", row["Not_Decl"],
                        f"{row['Rate']:.1f}%"
                    ], 2):
                        c = ws.cell(r, ci, val)
                        c.fill = bg; c.border = _border()
                        c.alignment = _center() if ci > 2 else _left()
                        c.font = _font(hi if ci == 4 else _TXT, 10)
                report_end = hdr + len(cashier_data) + 4
            else:
                report_end = hdr + 4
        else:
            ws.cell(3, 2, "No Discrepancy column in this report.").font = _font(_TXT3, 11)
            report_end = 6

        # Historical archive summary
        arch_c = {}; arch_r = {}
        try:
            for fp in glob.glob(os.path.join(DISCREPANCY_DB_PATH, "**", "*.xlsx"),
                                recursive=True):
                try:
                    tmp = pd.read_excel(fp)
                    if "Cashier Name" in tmp.columns and "Small_Discrepancies" in tmp.columns:
                        for _, row in tmp.iterrows():
                            cn = str(row["Cashier Name"])
                            arch_c[cn] = arch_c.get(cn, 0) + int(row.get("Small_Discrepancies", 0))
                            arch_r[cn] = arch_r.get(cn, 0) + 1
                except Exception:
                    pass
        except Exception:
            pass

        _section_hdr(ws, report_end, "All-Time Archive — Cashier Small Discrepancy History", 7)
        hdr_h = report_end + 1; ws.row_dimensions[hdr_h].height = 18
        for ci, h in enumerate(["Cashier","Total Events (All Time)","Reports Involved"], 2):
            c = ws.cell(hdr_h, ci, h)
            c.font = Font(color=_hex(_TXT3), size=8, bold=True)
            c.fill = _fill(_BG); c.alignment = _center()
        if arch_c:
            for ri, (cn, total) in enumerate(
                sorted(arch_c.items(), key=lambda x: x[1], reverse=True)[:25]
            ):
                r = hdr_h + 1 + ri; ws.row_dimensions[r].height = 14
                bg = _fill(_ELEV if ri % 2 == 0 else _SURF)
                color = _DNGR if total > 10 else _WARN if total > 4 else _OK
                for ci, val in enumerate([cn, total, arch_r.get(cn, 0)], 2):
                    c = ws.cell(r, ci, val)
                    c.fill = bg; c.border = _border()
                    c.alignment = _center() if ci > 2 else _left()
                    c.font = _font(color if ci == 3 else _TXT, 10, ci == 3 and total > 10)
        else:
            ws.cell(hdr_h+1, 2, "No archive data found.").font = _font(_TXT3, 10)

    wb.save(path)


# ═══════════════════════════════════════════════════════════════════════════════
# PDF GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_pdf(app, path, options):
    """Build a clean cursor-based PDF report (5 pages)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen.canvas import Canvas

    from config import (LODGEMENT, COL_DISC, OPERATOR, CUSTOMER_ID, CUSTOMER_LOC,
                        DISCREPANCY_DB_PATH)

    W, H = A4
    c = Canvas(path, pagesize=A4)

    def _hc(h): return HexColor(h)
    BG = _hc(_BG); SURF = _hc(_SURF); ELEV = _hc(_ELEV)
    TXT = _hc(_TXT); TXT2 = _hc(_TXT2); TXT3 = _hc(_TXT3)
    ACC = _hc(_ACCNT); OK_ = _hc(_OK); WRN = _hc(_WARN); DNG = _hc(_DNGR)

    # ── primitive helpers ──────────────────────────────────────────────────────
    # ── drawing primitives ────────────────────────────────────────────────────
    def _rect(x, y, w, h, fill=None, stroke=None, radius=4):
        c.saveState()
        if fill:   c.setFillColor(fill)
        if stroke: c.setStrokeColor(stroke)
        else:      c.setStrokeColor(_hc("#00000000"))
        c.roundRect(x, y, w, h, radius, fill=1 if fill else 0,
                    stroke=1 if stroke else 0)
        c.restoreState()

    def _text(x, y, text, size=10, color=None, bold=False, align="left"):
        c.saveState()
        c.setFillColor(color or TXT)
        fname = "Helvetica-Bold" if bold else "Helvetica"
        c.setFont(fname, size)
        if align == "center":
            c.drawCentredString(x, y, str(text))
        elif align == "right":
            c.drawRightString(x, y, str(text))
        else:
            c.drawString(x, y, str(text))
        c.restoreState()

    # ── layout helpers ────────────────────────────────────────────────────────
    MARGIN = 18 * mm
    COL_W  = W - 2 * MARGIN
    ROW_H  = 6.5 * mm

    def _page_bg():
        _rect(0, 0, W, H, fill=BG)

    def _header_banner(title, subtitle=""):
        _rect(0, H - 52*mm, W, 52*mm, fill=SURF)
        _rect(0, H - 2.5*mm, W, 2.5*mm, fill=ACC)
        _text(MARGIN, H - 18*mm, title,    size=20, color=ACC, bold=True)
        _text(MARGIN, H - 28*mm, subtitle, size=10, color=TXT2)
        _text(W - MARGIN, H - 18*mm,
              datetime.datetime.now().strftime("%d %B %Y"),
              size=9, color=TXT3, align="right")

    def _footer(page_num):
        _rect(0, 0, W, 10*mm, fill=SURF)
        _text(MARGIN,  3.5*mm, APP_VERSION, size=8, color=TXT3)
        _text(W/2,     3.5*mm, "CONFIDENTIAL — AUDIT INTELLIGENCE",
              size=8, color=TXT3, align="center")
        _text(W-MARGIN, 3.5*mm, f"Page {page_num}", size=8, color=TXT3, align="right")

    def _kpi_card(x, y, w, h, label, value, color):
        _rect(x, y, w, h, fill=ELEV, radius=5)
        _rect(x, y + h - 2*mm, w, 2*mm, fill=color, radius=5)
        _text(x + w/2, y + h - 11*mm, str(value), size=16, color=color,
              bold=True, align="center")
        _text(x + w/2, y + 3.5*mm, label.upper(), size=7, color=TXT3,
              align="center")

    df       = getattr(app, "active_df", None)
    dup_rows = getattr(app, "_exact_dup_rows", [])
    sus_rows = getattr(app, "_sus_rows",       [])
    shr_rows = getattr(app, "_shared_wallet_rows", [])

    page     = 1
    BODY_TOP = H - 58*mm
    BODY_BOT = 14*mm

    def _section_label(y, text):
        _rect(MARGIN, y - 1*mm, COL_W, 6.5*mm, fill=ELEV, radius=3)
        _text(MARGIN + 3*mm, y + 1*mm, text.upper(), size=7, color=TXT3, bold=True)
        return y - 9*mm

    def _table_hdr(y, cols):
        _rect(MARGIN, y - 1.5*mm, COL_W, 7*mm, fill=_hc("#07090f"), radius=3)
        for lbl, x, w, align in cols:
            _text(x + (w / 2 if align == "center" else 0), y + 1*mm,
                  lbl, size=7, color=TXT3, bold=True, align=align)
        return y - 8*mm

    def _table_row(y, vals_cols, bg, row_h=7*mm):
        _rect(MARGIN, y - 1.5*mm, COL_W, row_h, fill=bg, radius=2)
        for val, x, w, align, col in vals_cols:
            _text(x + (w / 2 if align == "center" else 0), y + 1*mm,
                  str(val)[:30], size=8, color=col, align=align)
        return y - (row_h + 1*mm)

    # ══════════════════════════════════════════════
    # PAGE 1 — EXECUTIVE SUMMARY
    # ══════════════════════════════════════════════
    _page_bg()
    _header_banner(
        f"{APP_VERSION}  —  Audit Intelligence Report",
        f"Executive Summary  ·  {datetime.datetime.now():%d %B %Y}"
    )

    n_rows  = len(df) if df is not None else 0
    tot_val = df[AMOUNT].sum() if df is not None and AMOUNT in df.columns else 0
    n_cash  = (df["Cashier Name"].nunique()
               if df is not None and "Cashier Name" in df.columns else 0)
    n_slips = (df[LODGEMENT].nunique()
               if df is not None and LODGEMENT in df.columns else 0)
    n_anom  = len(dup_rows)//2 + len(sus_rows)//2 + len(shr_rows)

    card_w = (COL_W - 9*mm) / 4
    for i, (lbl, val, col) in enumerate([
        ("TRANSACTIONS", f"{n_rows:,}",      _ACCNT),
        ("TOTAL SLIPS",  f"{n_slips:,}",     _OK),
        ("TOTAL VALUE",  f"€{tot_val:,.0f}", _WARN),
        ("CASHIERS",     str(n_cash),         _ACCNT),
    ]):
        _kpi_card(MARGIN + i * (card_w + 3*mm), BODY_TOP - 30*mm,
                  card_w, 26*mm, lbl, val, _hc(col))

    y = BODY_TOP - 42*mm
    y = _section_label(y, "Anomaly Summary")
    C1 = MARGIN + 3*mm;   W1 = 70*mm
    C2 = MARGIN + 75*mm;  W2 = 30*mm
    C3 = MARGIN + 107*mm; W3 = 38*mm
    C4 = MARGIN + 147*mm; W4 = 24*mm
    y = _table_hdr(y, [
        ("Type",               C1, W1, "left"),
        ("Count (pairs)",      C2, W2, "center"),
        ("% of Transactions",  C3, W3, "center"),
        ("Status",             C4, W4, "center"),
    ])
    for ri, (lbl, cnt, col) in enumerate([
        ("High Risk Duplicates",    len(dup_rows)//2, _DNGR),
        ("Suspicious Patterns",     len(sus_rows)//2, _WARN),
        ("Shared Wallet Incidents", len(shr_rows),    _OK),
    ]):
        pct    = f"{cnt/n_rows*100:.2f}%" if n_rows else "—"
        status = "RISK" if cnt > 0 else "CLEAR"
        bg     = _hc(_ELEV if ri % 2 == 0 else _SURF)
        y = _table_row(y, [
            (lbl,        C1, W1, "left",   TXT),
            (cnt or "—", C2, W2, "center", _hc(col)),
            (pct,        C3, W3, "center", TXT3),
            (status,     C4, W4, "center", _hc(col)),
        ], bg)
    y -= 6*mm
    _kpi_card(MARGIN, y - 22*mm, card_w * 1.5, 20*mm,
              "TOTAL ANOMALIES", str(n_anom), _hc(_DNGR if n_anom else _OK))
    _footer(page); c.showPage(); page += 1

    # ══════════════════════════════════════════════
    # PAGE 2 — CASHIER PERFORMANCE
    # ══════════════════════════════════════════════
    if options.get("performance", True) and df is not None and "Cashier Name" in df.columns:
        _page_bg()
        _header_banner("Cashier Performance",
                        "Volume, value, and slip counts per cashier")

        grp_val = df.groupby("Cashier Name")[AMOUNT].agg(["sum", "mean", "count"])
        grp_val.columns = ["Total_Value", "Avg_Value", "Transactions"]
        if LODGEMENT in df.columns:
            grp_slips = df.groupby("Cashier Name")[LODGEMENT].nunique().rename("Slips")
        else:
            grp_slips = df.groupby("Cashier Name").size().rename("Slips")
        perf = grp_val.join(grp_slips, how="left").fillna(0)
        perf["Pct_Val"] = perf["Total_Value"] / (perf["Total_Value"].sum() or 1) * 100
        perf = perf.sort_values("Total_Value", ascending=False)

        y  = BODY_TOP - 4*mm
        y  = _section_label(y, "Per-Cashier Breakdown — Sorted by Total Value")
        C1 = MARGIN + 3*mm;   W1 = 48*mm
        C2 = MARGIN + 53*mm;  W2 = 19*mm
        C3 = MARGIN + 74*mm;  W3 = 19*mm
        C4 = MARGIN + 95*mm;  W4 = 32*mm
        C5 = MARGIN + 129*mm; W5 = 26*mm
        C6 = MARGIN + 157*mm; W6 = 15*mm
        y = _table_hdr(y, [
            ("Cashier",     C1, W1, "left"),
            ("Txns",        C2, W2, "center"),
            ("Slips",       C3, W3, "center"),
            ("Total Value", C4, W4, "center"),
            ("Avg Value",   C5, W5, "center"),
            ("% Total",     C6, W6, "center"),
        ])
        for ri, (name, row) in enumerate(perf.iterrows()):
            if y < BODY_BOT + 4*mm:
                break
            bg  = _hc(_ELEV if ri % 2 == 0 else _SURF)
            hic = _hc(_ACCNT) if ri == 0 else TXT
            y = _table_row(y, [
                (str(name)[:26],               C1, W1, "left",   hic),
                (int(row["Transactions"]),      C2, W2, "center", TXT),
                (int(row["Slips"]),             C3, W3, "center", TXT),
                (f"€{row['Total_Value']:,.2f}", C4, W4, "center", _hc(_ACCNT)),
                (f"€{row['Avg_Value']:,.2f}",   C5, W5, "center", TXT),
                (f"{row['Pct_Val']:.1f}%",      C6, W6, "center", TXT3),
            ], bg)
        _footer(page); c.showPage(); page += 1

    # ══════════════════════════════════════════════
    # PAGE 3 — RISK INTELLIGENCE
    # ══════════════════════════════════════════════
    if options.get("risk", True) and df is not None and "Cashier Name" in df.columns:
        _page_bg()
        _header_banner("Risk Intelligence",
                        "Cashier risk scores — Dup 66%  Sus 12%  Shared 7%  Hist 15%")

        dup_c2 = {}
        for rd in dup_rows:
            n = rd.get("Cashier Name", rd.get("Cashier", ""))
            dup_c2[n] = dup_c2.get(n, 0) + 1
        sus_c2 = {}
        for rd in sus_rows:
            n = rd.get("Cashier Name", rd.get("Cashier", ""))
            sus_c2[n] = sus_c2.get(n, 0) + 1
        shr_c2 = {}
        for rd in shr_rows:
            n = rd.get("Cashier Name", rd.get("Cashier", ""))
            shr_c2[n] = shr_c2.get(n, 0) + 1
        hist_c2 = {}
        try:
            for fp in glob.glob(os.path.join(DISCREPANCY_DB_PATH, "**", "*.xlsx"),
                                recursive=True):
                tmp = pd.read_excel(fp)
                if "Cashier Name" in tmp.columns and "Small_Discrepancies" in tmp.columns:
                    for _, row in tmp.iterrows():
                        n = str(row["Cashier Name"])
                        hist_c2[n] = hist_c2.get(n, 0) + int(row.get("Small_Discrepancies", 0))
        except Exception:
            pass

        mx2 = lambda d: max(d.values(), default=1) or 1
        scores2 = []
        for name in df["Cashier Name"].unique():
            n   = str(name)
            raw = (45*(dup_c2.get(n, 0)/mx2(dup_c2)) + 8*(sus_c2.get(n, 0)/mx2(sus_c2)) +
                    5*(shr_c2.get(n, 0)/mx2(shr_c2)) + 10*(hist_c2.get(n, 0)/mx2(hist_c2)))
            s   = min(100, int(raw * 100 / 68))
            scores2.append((n, s, dup_c2.get(n, 0)//2, sus_c2.get(n, 0)//2,
                            shr_c2.get(n, 0), hist_c2.get(n, 0)))
        scores2.sort(key=lambda x: x[1], reverse=True)

        y  = BODY_TOP - 4*mm
        y  = _section_label(y, "Cashier Risk Scores — Highest First")
        C1 = MARGIN + 3*mm;   W1 = 45*mm
        C2 = MARGIN + 50*mm;  W2 = 15*mm
        C3 = MARGIN + 67*mm;  W3 = 20*mm
        C4 = MARGIN + 89*mm;  W4 = 15*mm
        C5 = MARGIN + 106*mm; W5 = 15*mm
        C6 = MARGIN + 123*mm; W6 = 15*mm
        C7 = MARGIN + 140*mm; W7 = 15*mm
        BAR_X   = MARGIN + 157*mm
        BAR_MAX = COL_W - 157*mm - 2*mm
        y = _table_hdr(y, [
            ("Cashier", C1, W1, "left"),
            ("Score",   C2, W2, "center"),
            ("Band",    C3, W3, "center"),
            ("Dups",    C4, W4, "center"),
            ("Sus",     C5, W5, "center"),
            ("Shared",  C6, W6, "center"),
            ("Hist",    C7, W7, "center"),
        ])
        for name, score, dups, sus, shr, hist in scores2:
            if y < BODY_BOT + 4*mm:
                break
            band = "HIGH" if score >= 61 else "MED" if score >= 31 else "LOW"
            scol = _hc(_DNGR if score >= 61 else _WARN if score >= 31 else _OK)
            bg   = _hc("#162440" if score >= 61 else "#0e1628" if score >= 31 else _SURF)
            _rect(MARGIN, y - 1.5*mm, COL_W, 7*mm, fill=bg, radius=2)
            bw = max(1, int(BAR_MAX * score / 100))
            _rect(BAR_X, y, bw, 5*mm, fill=scol, radius=2)
            _text(C1,        y + 1*mm, str(name)[:24], size=8, color=TXT)
            _text(C2 + W2/2, y + 1*mm, str(score),  size=9, color=scol, bold=True, align="center")
            _text(C3 + W3/2, y + 1*mm, band,         size=7, color=scol, align="center")
            _text(C4 + W4/2, y + 1*mm, str(dups) if dups else "—",
                  size=8, color=_hc(_DNGR) if dups else TXT3, align="center")
            _text(C5 + W5/2, y + 1*mm, str(sus)  if sus  else "—",
                  size=8, color=_hc(_WARN) if sus  else TXT3, align="center")
            _text(C6 + W6/2, y + 1*mm, str(shr)  if shr  else "—",
                  size=8, color=_hc(_OK)   if shr  else TXT3, align="center")
            _text(C7 + W7/2, y + 1*mm, str(hist) if hist else "—",
                  size=8, color=TXT, align="center")
            y -= 8*mm
        _footer(page); c.showPage(); page += 1

    # ══════════════════════════════════════════════
    # PAGE 4 — CUSTOMER ANALYSIS
    # ══════════════════════════════════════════════
    if options.get("customers", True) and df is not None and CUSTOMER_ID in df.columns:
        _page_bg()
        _header_banner("Customer Analysis",
                        "Customer ID · Location · Discrepancies (≤€10) · Not declaring")

        y = BODY_TOP - 4*mm
        if COL_DISC in df.columns:
            has_loc = CUSTOMER_LOC in df.columns
            df2 = df.copy()
            df2[COL_DISC] = pd.to_numeric(df2[COL_DISC], errors="coerce").fillna(0)
            df2[AMOUNT]   = pd.to_numeric(df2[AMOUNT],   errors="coerce").fillna(0)
            cust_d = []
            for cid, grp in df2.groupby(CUSTOMER_ID):
                loc = ""
                if has_loc:
                    ls = grp[CUSTOMER_LOC].dropna().astype(str)
                    loc = ls.mode().iloc[0] if not ls.empty else ""
                all_d = grp[grp[COL_DISC].abs() > 0]
                small = grp[(grp[COL_DISC].abs() > 0) & (grp[COL_DISC].abs() <= 10)]
                ndecl = grp[(grp[AMOUNT] > 0) &
                            ((grp[COL_DISC].abs() - grp[AMOUNT].abs()).abs() < 0.01)]
                cust_d.append({"cid": str(cid), "loc": loc, "txns": len(grp),
                               "all": len(all_d), "sm": len(small),
                               "sm_amt": float(small[COL_DISC].abs().sum()),
                               "nd": len(ndecl)})
            cust_d.sort(key=lambda x: x["all"], reverse=True)

            y = _section_label(y, "Top Customers — All Discrepancies (This Report)")
            C1 = MARGIN + 3*mm;   W1 = 28*mm   # Customer ID
            C2 = MARGIN + 33*mm;  W2 = 35*mm   # Location
            C3 = MARGIN + 70*mm;  W3 = 18*mm   # Txns
            C4 = MARGIN + 90*mm;  W4 = 18*mm   # All Disc
            C5 = MARGIN + 110*mm; W5 = 18*mm   # Small Disc
            C6 = MARGIN + 130*mm; W6 = 24*mm   # Small Amt
            C7 = MARGIN + 156*mm; W7 = 16*mm   # Not Decl
            y = _table_hdr(y, [
                ("Cust. ID",   C1, W1, "left"),
                ("Location",   C2, W2, "left"),
                ("Txns",       C3, W3, "center"),
                ("All Disc",   C4, W4, "center"),
                ("Small Disc", C5, W5, "center"),
                ("Small Amt",  C6, W6, "center"),
                ("Not Decl",   C7, W7, "center"),
            ])
            for ri, row in enumerate(cust_d[:12]):
                if y < BODY_BOT + 50*mm:
                    break
                dcol = _hc(_DNGR if row["all"] > 5 else _WARN if row["all"] > 2 else _TXT)
                bg   = _hc(_ELEV if ri % 2 == 0 else _SURF)
                y = _table_row(y, [
                    (row["cid"][:14],         C1, W1, "left",   TXT),
                    (row["loc"][:20],         C2, W2, "left",   TXT2),
                    (row["txns"],             C3, W3, "center", TXT),
                    (row["all"] or "—",       C4, W4, "center", dcol),
                    (row["sm"] or "—",        C5, W5, "center",
                     _hc(_WARN) if row["sm"] else TXT3),
                    (f"€{row['sm_amt']:.2f}", C6, W6, "center",
                     _hc(_WARN) if row["sm_amt"] else TXT3),
                    (row["nd"] or "—",        C7, W7, "center",
                     _hc(_DNGR) if row["nd"] else TXT3),
                ], bg)

            # Location hotspots
            y -= 3*mm
            if has_loc:
                y = _section_label(y, "Location Hotspots — Discrepancy Frequency by Location")
                loc_map = {}
                for row in cust_d:
                    if row["loc"]:
                        loc_map[row["loc"]] = (loc_map.get(row["loc"], (0, 0))[0] + row["all"],
                                               loc_map.get(row["loc"], (0, 0))[1] + row["txns"])
                loc_sorted = sorted(loc_map.items(), key=lambda x: x[1][0], reverse=True)[:8]
                L1 = MARGIN + 3*mm;  LW1 = 58*mm
                L2 = MARGIN + 63*mm; LW2 = 22*mm
                L3 = MARGIN + 87*mm; LW3 = 22*mm
                y = _table_hdr(y, [
                    ("Location",         L1, LW1, "left"),
                    ("All Disc",         L2, LW2, "center"),
                    ("Transactions",     L3, LW3, "center"),
                ])
                for ri, (loc, (disc_cnt, txn_cnt)) in enumerate(loc_sorted):
                    if y < BODY_BOT + 38*mm:
                        break
                    lcol = _hc(_DNGR if disc_cnt > 10 else _WARN if disc_cnt > 4 else _OK)
                    bg   = _hc(_ELEV if ri % 2 == 0 else _SURF)
                    y = _table_row(y, [
                        (loc[:32],    L1, LW1, "left",   TXT),
                        (disc_cnt,    L2, LW2, "center", lcol),
                        (txn_cnt,     L3, LW3, "center", TXT),
                    ], bg)
                y -= 3*mm

            # Not declaring
            ndcust = sorted([r for r in cust_d if r["nd"] > 0],
                            key=lambda x: x["nd"], reverse=True)
            y = _section_label(y, "Customers Not Declaring (Expected=0, Processed>0)")
            if ndcust:
                N1 = MARGIN + 3*mm;  NW1 = 35*mm
                N2 = MARGIN + 40*mm; NW2 = 38*mm
                N3 = MARGIN + 80*mm; NW3 = 24*mm
                N4 = MARGIN + 106*mm; NW4 = 34*mm
                y = _table_hdr(y, [
                    ("Cust. ID",     N1, NW1, "left"),
                    ("Location",     N2, NW2, "left"),
                    ("Occurrences",  N3, NW3, "center"),
                    ("Undecl. Value", N4, NW4, "center"),
                ])
                for ri, row in enumerate(ndcust[:8]):
                    if y < BODY_BOT + 4*mm:
                        break
                    ndrows = df2[(df2[CUSTOMER_ID] == row["cid"]) & (df2[AMOUNT] > 0) &
                                  ((df2[COL_DISC].abs() - df2[AMOUNT].abs()).abs() < 0.01)]
                    undecl = float(ndrows[AMOUNT].sum())
                    bg     = _hc(_ELEV if ri % 2 == 0 else _SURF)
                    y = _table_row(y, [
                        (row["cid"][:14],    N1, NW1, "left",   TXT),
                        (row["loc"][:20],    N2, NW2, "left",   TXT2),
                        (row["nd"],          N3, NW3, "center", _hc(_DNGR)),
                        (f"€{undecl:,.2f}",  N4, NW4, "center", _hc(_DNGR)),
                    ], bg)
            else:
                _text(MARGIN + 3*mm, y - 4*mm,
                      "No undeclared-amount customers in this report.", size=9, color=TXT3)
        else:
            _text(MARGIN + 3*mm, y - 8*mm,
                  "No Discrepancy column found in the imported report.", size=11, color=TXT3)
        _footer(page); c.showPage(); page += 1

    # ══════════════════════════════════════════════
    # PAGE 5 — SMALL DISCREPANCY TRENDS
    # ══════════════════════════════════════════════
    if options.get("trends", True) or options.get("discprofile", True):
        _page_bg()
        _header_banner("Small Discrepancy Trends",
                        "Unapproved amounts ≤ €10 — monthly trend + all-time cashier ranking")

        monthly_data = {}
        cashier_tots = {}
        try:
            for fp in glob.glob(os.path.join(DISCREPANCY_DB_PATH, "**", "*.xlsx"),
                                recursive=True):
                try:
                    tmp = pd.read_excel(fp)
                    if "Small_Discrepancies" not in tmp.columns:
                        continue
                    mkey = None
                    if "Report_Date" in tmp.columns:
                        try:
                            dt   = pd.to_datetime(str(tmp["Report_Date"].iloc[0]),
                                                  dayfirst=True)
                            mkey = dt.strftime("%b %y")
                        except Exception:
                            pass
                    mkey = mkey or os.path.basename(os.path.dirname(fp))
                    monthly_data[mkey] = (monthly_data.get(mkey, 0)
                                          + int(tmp["Small_Discrepancies"].sum()))
                    if "Cashier Name" in tmp.columns:
                        for _, row in tmp.iterrows():
                            cn = str(row["Cashier Name"])
                            cashier_tots[cn] = (cashier_tots.get(cn, 0)
                                                + int(row.get("Small_Discrepancies", 0)))
                except Exception:
                    pass
        except Exception:
            pass

        y = BODY_TOP - 4*mm
        y = _section_label(y, "Monthly Small Discrepancy Events — All-Time Trend")
        if monthly_data:
            def _ms(k):
                try:    return datetime.datetime.strptime(k, "%b %y")
                except: return datetime.datetime.min
            sorted_m = sorted(monthly_data.items(), key=lambda x: _ms(x[0]))[-24:]
            max_v    = max(v for _, v in sorted_m) or 1
            bar_area = COL_W - 50*mm
            bar_rh   = 6*mm
            for mkey, cnt in sorted_m:
                if y < BODY_BOT + 55*mm:
                    break
                bw2  = max(2*mm, bar_area * cnt / max_v)
                col2 = _hc(_DNGR if cnt > 10 else _WARN if cnt > 4 else _OK)
                _text(MARGIN + 3*mm, y, str(mkey), size=7, color=TXT2)
                _rect(MARGIN + 22*mm, y - 1*mm, bw2, bar_rh - 2*mm, fill=col2, radius=2)
                _text(MARGIN + 22*mm + bw2 + 2*mm, y, str(cnt), size=7, color=TXT3)
                y -= bar_rh + 1*mm
        else:
            _text(MARGIN + 3*mm, y - 4*mm, "No archive data found.", size=9, color=TXT3)
            y -= 16*mm

        y -= 6*mm
        y = _section_label(y, "All-Time Cashier Ranking — Cumulative Small Discrepancies")
        if cashier_tots:
            ranking = sorted(cashier_tots.items(), key=lambda x: x[1], reverse=True)[:20]
            R1 = MARGIN + 3*mm;  RW1 = 65*mm
            R2 = MARGIN + 70*mm; RW2 = 32*mm
            y = _table_hdr(y, [
                ("Cashier",           R1, RW1, "left"),
                ("Cumulative Events",  R2, RW2, "center"),
            ])
            for ri, (cn, total) in enumerate(ranking):
                if y < BODY_BOT + 4*mm:
                    break
                col3 = _hc(_DNGR if total > 10 else _WARN if total > 4 else _OK)
                bg3  = _hc(_ELEV if ri % 2 == 0 else _SURF)
                y = _table_row(y, [
                    (cn[:34], R1, RW1, "left",   TXT),
                    (total,   R2, RW2, "center",  col3),
                ], bg3)
        else:
            _text(MARGIN + 3*mm, y - 4*mm, "No cashier archive data found.",
                  size=9, color=TXT3)
        _footer(page); c.showPage(); page += 1

    c.save()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE WIDGET
# ═══════════════════════════════════════════════════════════════════════════════

def _card_ui(title=""):
    f = QFrame()
    f.setStyleSheet(
        f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};"
        f"border-radius:8px;}}"
    )
    lay = QVBoxLayout(f)
    lay.setContentsMargins(20, 16, 20, 18); lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setStyleSheet(f"color:{Theme.TXT};font-size:13px;font-weight:600;")
        lay.addWidget(t)
        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div)
    return f, lay


class VisualReportPage(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        root = QVBoxLayout(inner)
        root.setContentsMargins(24, 20, 24, 24); root.setSpacing(20)
        root.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner); outer.addWidget(scroll)

        # ── Header ─────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("Visual Report Generator")
        title.setStyleSheet(f"color:{Theme.TXT};font-size:18px;font-weight:700;")
        hdr.addWidget(title); hdr.addStretch()
        root.addLayout(hdr)

        sub = QLabel(
            "Produces a polished multi-page PDF or a chart-rich Excel workbook "
            "from the current session. KPI tiles, risk score tables, cashier performance, "
            "customer analysis, and small discrepancy trends — all formatted for presentation."
        )
        sub.setStyleSheet(f"color:{Theme.TXT_3};font-size:12px;")
        sub.setWordWrap(True); root.addWidget(sub)

        # ── What's included card ────────────────────────────────────────
        inc_card, inc_lay = _card_ui("What's Included")
        self._checks = {}
        sections = [
            ("summary",     "Executive Summary",
             "KPI tiles · Anomaly summary table",                          True),
            ("performance", "Cashier Performance",
             "Volume, value, and slip counts per cashier",                  True),
            ("risk",        "Risk Intelligence",
             "Risk score table · Anomaly breakdown per cashier",            True),
            ("customers",   "Customer Analysis",
             "Discrepancies · Small amounts (≤€10) · Not declaring",        True),
            ("trends",      "Small Disc Trends",
             "Monthly events chart · All-time cashier ranking",             True),
            ("discprofile", "Discrepancy Profile",
             "This report + all-time small discrepancy history",            True),
        ]
        grid = QGridLayout(); grid.setSpacing(10)
        for idx, (key, label, desc, default) in enumerate(sections):
            tile = QFrame()
            tile.setStyleSheet(
                f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER};"
                f"border-radius:7px;}}"
            )
            tl = QVBoxLayout(tile); tl.setContentsMargins(14, 12, 14, 14); tl.setSpacing(6)
            cb = QCheckBox(label); cb.setChecked(default)
            cb.setStyleSheet(
                f"QCheckBox{{color:{Theme.TXT};font-size:12px;font-weight:600;}}"
                f"QCheckBox::indicator{{width:14px;height:14px;border:1px solid {Theme.BORDER};"
                f"border-radius:3px;background:{Theme.ELEVATED};}}"
                f"QCheckBox::indicator:checked{{background:{Theme.ACCENT};"
                f"border-color:{Theme.ACCENT};}}"
            )
            dl = QLabel(desc)
            dl.setStyleSheet(f"color:{Theme.TXT_3};font-size:10px;")
            dl.setWordWrap(True)
            tl.addWidget(cb); tl.addWidget(dl)
            self._checks[key] = cb
            grid.addWidget(tile, idx // 3, idx % 3)
        inc_lay.addLayout(grid)
        root.addWidget(inc_card)

        # ── Format selector + generate ──────────────────────────────────
        fmt_card, fmt_lay = _card_ui("Choose Format & Generate")

        fmt_row = QHBoxLayout(); fmt_row.setSpacing(12)
        self._fmt_btns = {}
        for fmt, label, desc in [
            ("xlsx", "Excel (.xlsx)",
             "Native chart objects · Sortable tables · Opens in Excel/LibreOffice"),
            ("pdf",  "PDF",
             "Vector shapes · Print-ready · Requires: pip install reportlab"),
        ]:
            tile = QFrame()
            tile.setStyleSheet(
                f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER};"
                f"border-radius:7px;}}"
            )
            tl = QVBoxLayout(tile); tl.setContentsMargins(16, 14, 16, 14); tl.setSpacing(6)
            rb = QPushButton(label); rb.setCheckable(True)
            rb.setChecked(fmt == "xlsx")
            rb.setStyleSheet(self._fmt_btn_style(fmt == "xlsx"))
            rb.clicked.connect(lambda _, f=fmt: self._select_fmt(f))
            dl2 = QLabel(desc)
            dl2.setStyleSheet(f"color:{Theme.TXT_3};font-size:10px;")
            dl2.setWordWrap(True)
            tl.addWidget(rb); tl.addWidget(dl2)
            self._fmt_btns[fmt] = rb
            fmt_row.addWidget(tile)
        fmt_row.addStretch()
        fmt_lay.addLayout(fmt_row)

        gen_row = QHBoxLayout()
        self._gen_btn = QPushButton("Generate Report")
        self._gen_btn.setObjectName("primary")
        self._gen_btn.setFixedHeight(42); self._gen_btn.setMinimumWidth(200)
        self._gen_btn.clicked.connect(self._generate)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate
        self._progress.setFixedHeight(6)
        self._progress.setVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar{{background:{Theme.ELEVATED};border-radius:3px;border:none;}}"
            f"QProgressBar::chunk{{background:{Theme.ACCENT};border-radius:3px;}}"
        )
        gen_row.addWidget(self._gen_btn); gen_row.addWidget(self._progress, 1)
        gen_row.addStretch()
        fmt_lay.addLayout(gen_row)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{Theme.OK};font-size:12px;font-weight:600;")
        fmt_lay.addWidget(self._status)
        root.addWidget(fmt_card)

        # ── Data preview ────────────────────────────────────────────────
        self._prev_card, prev_lay = _card_ui("Session Data Available")
        self._prev_lbl = QLabel("No report loaded.")
        self._prev_lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:12px;")
        self._prev_lbl.setWordWrap(True)
        prev_lay.addWidget(self._prev_lbl)
        root.addWidget(self._prev_card)

        self._active_fmt = "xlsx"

    # ── helpers ───────────────────────────────────────────────────────────────

    def _fmt_btn_style(self, active):
        if active:
            return (f"QPushButton{{background:{Theme.ACCENT};color:#ffffff;"
                    f"border:none;border-radius:5px;padding:6px 14px;"
                    f"font-size:12px;font-weight:700;}}"
                    f"QPushButton:hover{{background:{Theme.ACCENT_H};color:#ffffff;}}")
        return (f"QPushButton{{background:{Theme.ELEVATED};color:{Theme.TXT_2};"
                f"border:1px solid {Theme.BORDER};border-radius:5px;padding:6px 14px;"
                f"font-size:12px;font-weight:500;}}"
                f"QPushButton:hover{{color:{Theme.TXT};background:{Theme.HOVER};}}")

    def _select_fmt(self, fmt):
        self._active_fmt = fmt
        for f, btn in self._fmt_btns.items():
            btn.setStyleSheet(self._fmt_btn_style(f == fmt))
            btn.setChecked(f == fmt)

    def _options(self):
        return {k: cb.isChecked() for k, cb in self._checks.items()}

    def _update_preview(self):
        df = getattr(self.app, "active_df", None)
        lines = []
        if df is not None and not df.empty:
            lines.append(f"✓  {len(df):,} transactions loaded")
        else:
            lines.append("✗  No transaction data  (import a report in Integrity Check)")
        n_dup = len(getattr(self.app, "_exact_dup_rows", []))
        n_sus = len(getattr(self.app, "_sus_rows", []))
        lines.append(f"{'✓' if n_dup or n_sus else '○'}  Anomaly data: "
                     f"{n_dup} high-risk, {n_sus} suspicious")
        files = glob.glob(
            os.path.join(DISCREPANCY_DB_PATH, "**", "*.xlsx"), recursive=True)
        lines.append(f"{'✓' if files else '○'}  Discrepancy archive: "
                     f"{len(files)} file(s)")
        self._prev_lbl.setText("\n".join(lines))

    def _generate(self):
        fmt  = self._active_fmt
        opts = self._options()
        ext  = "xlsx" if fmt == "xlsx" else "pdf"
        filt = ("Excel (*.xlsx)" if fmt == "xlsx"
                else "PDF (*.pdf)")
        default = (f"Spectre_Visual_Report_"
                   f"{datetime.date.today():%Y%m%d}.{ext}")
        path, _ = QFileDialog.getSaveFileName(self, "Save Report", default, filt)
        if not path:
            return

        self._gen_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status.setText("Generating…")
        QApplication.processEvents()

        try:
            if fmt == "xlsx":
                generate_excel(self.app, path, opts)
            else:
                generate_pdf(self.app, path, opts)
            self._status.setText(f"✓  Saved to {os.path.basename(path)}")
            self._status.setStyleSheet(
                f"color:{Theme.OK};font-size:12px;font-weight:600;"
            )
        except ImportError as ie:
            self._status.setText(
                f"Missing library: {ie}  —  run:  pip install reportlab"
            )
            self._status.setStyleSheet(
                f"color:{Theme.WARN};font-size:12px;font-weight:600;"
            )
        except Exception as e:
            logging.exception("Unhandled exception")
            self._status.setText(f"Error: {e}")
            self._status.setStyleSheet(
                f"color:{Theme.DANGER};font-size:12px;font-weight:600;"
            )
        finally:
            self._gen_btn.setEnabled(True)
            self._progress.setVisible(False)

    def showEvent(self, e):
        super().showEvent(e)
        self._update_preview()

"""
pages/analytics_export.py — Export Report tab.

Generates a polished multi-sheet .xlsx audit report from the current session.
Sheets: Summary, High Risk Transactions, Cashier Risk Scores,
        Discrepancy History, (chart data for manual chart creation).
"""
import logging
import os
import glob
import datetime

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QFileDialog, QScrollArea, QCheckBox,
    QButtonGroup, QDialog,
)

from config import AMOUNT, DISCREPANCY_DB_PATH, APP_VERSION
from theme import Theme


DATE_RANGES = ["Today", "This Week", "This Month", "This Year", "All Time", "Custom Range"]


def _parse_file_date(fp):
    """Return a date parsed from a filename like DD.MM.YYYY.xlsx, or None."""
    stem = os.path.splitext(os.path.basename(fp))[0]
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(stem, fmt).date()
        except ValueError:
            pass
    return None


def _filter_archive_files(files, date_range, custom_start=None, custom_end=None):
    if date_range == "All Time":
        return files
    today = datetime.date.today()
    result = []
    for fp in files:
        d = _parse_file_date(fp)
        if d is None:
            continue
        if date_range == "Today":
            if d == today:
                result.append(fp)
        elif date_range == "This Week":
            week_start = today - datetime.timedelta(days=today.weekday())
            if d >= week_start:
                result.append(fp)
        elif date_range == "This Month":
            if d.month == today.month and d.year == today.year:
                result.append(fp)
        elif date_range == "This Year":
            if d.year == today.year:
                result.append(fp)
        elif date_range == "Custom Range":
            if custom_start and custom_end and custom_start <= d <= custom_end:
                result.append(fp)
    return result


def _card(title=""):
    f = QFrame()
    f.setStyleSheet(
        f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
    )
    lay = QVBoxLayout(f); lay.setContentsMargins(20,16,20,18); lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setStyleSheet(f"color:{Theme.TXT};font-size:13px;font-weight:600;")
        lay.addWidget(t)
        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div)
    return f, lay


class ExportReportPage(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        root = QVBoxLayout(inner)
        root.setContentsMargins(24,20,24,24); root.setSpacing(20)
        root.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Export Audit Report")
        title.setStyleSheet(f"color:{Theme.TXT};font-size:18px;font-weight:700;")
        hdr.addWidget(title); hdr.addStretch()
        root.addLayout(hdr)

        sub = QLabel(
            "Generates a formatted multi-sheet Excel workbook. "
            "Pick a date range to scope Discrepancy History and Cashier Risk Scores; "
            "session sheets (High Risk, Full Transactions) always reflect the current loaded report."
        )
        sub.setStyleSheet(f"color:{Theme.TXT_3};font-size:12px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # Sheet selection card
        sel_card, sel_lay = _card("Sheets to Include")
        self._checks = {}
        sheets = [
            ("summary",      "Summary",                     "Report overview, key findings, file info and totals",              True),
            ("high_risk",    "High Risk Transactions",       "All exact-duplicate rows flagged by Integrity Check",              True),
            ("risk_scores",  "Cashier Risk Scores",          "Weighted 0-100 score per cashier, sorted high to low",             True),
            ("disc_history", "Discrepancy History",          "All archived small discrepancy events from the database",          True),
            ("raw_data",     "Full Transaction Data",        "Complete cleaned transaction table from the loaded report",        False),
        ]
        grid = QHBoxLayout(); grid.setSpacing(8)
        for key, label, desc, default in sheets:
            tile = QFrame()
            tile.setStyleSheet(
                f"QFrame{{background:{Theme.ELEVATED};border:1px solid {Theme.BORDER};"
                f"border-radius:7px;}}"
            )
            tl = QVBoxLayout(tile); tl.setContentsMargins(14,12,14,12); tl.setSpacing(4)
            cb = QCheckBox(label)
            cb.setChecked(default)
            cb.setStyleSheet(
                f"QCheckBox{{color:{Theme.TXT};font-size:12px;font-weight:600;}}"
                f"QCheckBox::indicator{{width:14px;height:14px;border:1px solid {Theme.BORDER};"
                f"border-radius:3px;background:{Theme.ELEVATED};}}"
                f"QCheckBox::indicator:checked{{background:{Theme.ACCENT};border-color:{Theme.ACCENT};}}"
            )
            dl = QLabel(desc)
            dl.setStyleSheet(f"color:{Theme.TXT_3};font-size:10px;")
            dl.setWordWrap(True)
            tl.addWidget(cb); tl.addWidget(dl)
            self._checks[key] = cb
            grid.addWidget(tile)
        sel_lay.addLayout(grid)
        root.addWidget(sel_card)

        # Date range card
        dr_card, dr_lay = _card("Date Range")
        dr_note = QLabel(
            "Scopes Discrepancy History and Cashier Risk Scores to the selected period."
        )
        dr_note.setStyleSheet(f"color:{Theme.TXT_3};font-size:10.5px;")
        dr_lay.addWidget(dr_note)

        self._dr_btns: dict[str, QPushButton] = {}
        self._dr_group = QButtonGroup(self)
        self._dr_group.setExclusive(True)
        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        for rng in DATE_RANGES:
            b = QPushButton(rng)
            b.setCheckable(True)
            b.setFixedHeight(26)
            b.setMinimumWidth(90)
            self._dr_btns[rng] = b
            self._dr_group.addButton(b)
            btn_row.addWidget(b)
            b.clicked.connect(lambda _=False, r=rng: self._on_date_range(r))
        btn_row.addStretch()
        dr_lay.addLayout(btn_row)
        root.addWidget(dr_card)

        # ── Date range state ──────────────────────────────────────────
        self._date_range = "All Time"
        self._custom_start: datetime.date | None = None
        self._custom_end:   datetime.date | None = None
        self._set_active_dr("All Time")

        # Status / preview card
        self._preview_card, self._preview_lay = _card("Report Preview")
        self._preview_lbl = QLabel("No report loaded. Import a report in Integrity Check first.")
        self._preview_lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:12px;")
        self._preview_lbl.setWordWrap(True)
        self._preview_lay.addWidget(self._preview_lbl)
        root.addWidget(self._preview_card)

        # Generate button
        gen_row = QHBoxLayout()
        self._gen_btn = QPushButton("Generate Excel Report")
        self._gen_btn.setObjectName("primary")
        self._gen_btn.setFixedHeight(42)
        self._gen_btn.setMinimumWidth(220)
        self._gen_btn.clicked.connect(self._generate)
        gen_row.addStretch(); gen_row.addWidget(self._gen_btn); gen_row.addStretch()
        root.addLayout(gen_row)

        self._status_lbl = QLabel("")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setStyleSheet(f"color:{Theme.OK};font-size:12px;font-weight:600;")
        root.addWidget(self._status_lbl)

    def _set_active_dr(self, active):
        for k, b in self._dr_btns.items():
            on = k == active
            b.setChecked(on)
            b.setStyleSheet(
                f"QPushButton{{background:{Theme.ACCENT if on else Theme.ELEVATED};"
                f"color:{'white' if on else Theme.TXT_3};"
                f"border:1px solid {Theme.ACCENT if on else Theme.BORDER};"
                f"border-radius:4px;font-size:10px;font-weight:600;padding:0 8px;}}"
                f"QPushButton:hover{{color:{'white' if on else Theme.TXT_2};}}"
            )

    def _on_date_range(self, rng):
        if rng == "Custom Range":
            from pages.discrepancies_tab import _DateRangeDialog
            dlg = _DateRangeDialog(self._custom_start, self._custom_end, self)
            if dlg.exec() != QDialog.Accepted:
                self._set_active_dr(self._date_range)
                return
            self._custom_start = dlg.start_date
            self._custom_end   = dlg.end_date
        self._date_range = rng
        self._set_active_dr(rng)
        self._update_preview()

    def showEvent(self, e):
        super().showEvent(e)
        self._update_preview()

    def _update_preview(self):
        df = getattr(self.app, "active_df", None)
        lines = []
        if df is not None and not df.empty:
            lines.append(f"✓  Transaction data loaded  —  {len(df):,} rows, "
                         f"€{df[AMOUNT].sum():,.2f} total value")
        else:
            lines.append("✗  No transaction data  (import a report in Integrity Check)")

        n_dup = len(getattr(self.app,"_exact_dup_rows",[]))
        n_sus = len(getattr(self.app,"_sus_rows",[]))
        if n_dup or n_sus:
            lines.append(f"✓  Anomaly data  —  {n_dup} high-risk, {n_sus} suspicious")
        else:
            lines.append("○  No anomaly data yet")

        all_files = glob.glob(os.path.join(DISCREPANCY_DB_PATH,"**","*.xlsx"), recursive=True)
        filtered  = _filter_archive_files(all_files, self._date_range, self._custom_start, self._custom_end)
        if all_files:
            if len(filtered) < len(all_files):
                lines.append(
                    f"✓  Discrepancy archive  —  {len(filtered)} of {len(all_files)} files in selected range"
                )
            else:
                lines.append(f"✓  Discrepancy archive  —  {len(all_files)} files found")
        else:
            lines.append("○  No discrepancy archive found")

        self._preview_lbl.setText("\n".join(lines))

    def _generate(self):
        try:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Audit Report", f"Spectre_Audit_{datetime.date.today():%Y%m%d}.xlsx",
                "Excel (*.xlsx)"
            )
            if not path:
                return

            self._gen_btn.setEnabled(False)
            self._status_lbl.setText("Generating…")

            import openpyxl
            from openpyxl.styles import (PatternFill, Font, Alignment,
                                         Border, Side)
            from openpyxl.utils import get_column_letter

            wb = openpyxl.Workbook()
            wb.remove(wb.active)  # remove default sheet

            # ── Resolve date range label and filtered archive files ────
            if (self._date_range == "Custom Range"
                    and self._custom_start and self._custom_end):
                period_label = f"{self._custom_start:%d/%m/%Y} – {self._custom_end:%d/%m/%Y}"
            elif self._date_range == "All Time":
                period_label = "All Time"
            else:
                period_label = self._date_range

            all_archive = glob.glob(
                os.path.join(DISCREPANCY_DB_PATH, "**", "*.xlsx"), recursive=True
            )
            archive_files = _filter_archive_files(
                all_archive, self._date_range, self._custom_start, self._custom_end
            )

            # ── Style helpers — print-friendly professional palette ────
            # Header: medium navy fill, white bold text
            def _hdr_font():   return Font(bold=True, color="FFFFFF", size=10,
                                           name="Calibri")
            def _hdr_fill():   return PatternFill("solid", fgColor="2B4A8A")
            # Titles / section headings
            def _title_font(): return Font(bold=True, color="1E3A70", size=13,
                                           name="Calibri")
            def _sub_font():   return Font(color="5A6E8A", size=10, name="Calibri")
            # Regular cell text — dark so it reads on white/light backgrounds
            def _val_font():   return Font(color="1A2A45", size=10, name="Calibri")
            # Alternating row fills: very light blue-tint / white
            def _hi_fill():    return PatternFill("solid", fgColor="EEF3FB")
            def _med_fill():   return PatternFill("solid", fgColor="FFFFFF")
            thin = Side(style="thin", color="C0CDE0")
            def _border(): return Border(
                bottom=thin, top=thin, left=thin, right=thin
            )

            def _auto_width(ws):
                for col in ws.columns:
                    max_len = 0
                    col_ltr = get_column_letter(col[0].column)
                    for cell in col:
                        try: max_len = max(max_len, len(str(cell.value or "")))
                        except: pass
                    # min 8, max 38, +3 padding
                    ws.column_dimensions[col_ltr].width = max(8, min(max_len + 3, 38))

            # ── 1. Summary sheet ───────────────────────────────────────
            if self._checks["summary"].isChecked():
                ws = wb.create_sheet("Summary")
                ws.sheet_view.showGridLines = False
                df = getattr(self.app, "active_df", None)

                ws["A1"] = APP_VERSION + " — Audit Intelligence Report"
                ws["A1"].font = _title_font()
                ws["A2"] = f"Generated: {datetime.datetime.now():%d/%m/%Y %H:%M}"
                ws["A2"].font = _sub_font()
                ws.row_dimensions[1].height = 26
                ws.row_dimensions[3].height = 16

                fields = [
                    ("Report File",   getattr(self.app,"_active_report_path","—")),
                    ("Report Period",  period_label),
                    ("Transactions",  f"{len(df):,}" if df is not None else "—"),
                    ("Total Value",   f"€{df[AMOUNT].sum():,.2f}" if df is not None and AMOUNT in df.columns else "—"),
                    ("Cashiers",      str(df['Cashier Name'].nunique()) if df is not None and 'Cashier Name' in df.columns else "—"),
                    ("High Risk",     str(len(getattr(self.app,"_exact_dup_rows",[])))),
                    ("Suspicious",    str(len(getattr(self.app,"_sus_rows",[])))),
                    ("Shared Wallets",str(len(getattr(self.app,"_shared_wallet_rows",[])))),
                ]
                for i, (k, v) in enumerate(fields, 4):
                    ws[f"A{i}"] = k
                    ws[f"A{i}"].font = Font(color="5A6E8A", bold=True, size=10, name="Calibri")
                    ws[f"B{i}"] = v
                    ws[f"B{i}"].font = _val_font()
                ws.column_dimensions["A"].width = 22
                ws.column_dimensions["B"].width = 40

                # Key findings narrative
                ws[f"A{len(fields)+6}"] = "KEY FINDINGS"
                ws[f"A{len(fields)+6}"].font = Font(bold=True, color="2B4A8A", size=10,
                                                    name="Calibri")
                n_hr = len(getattr(self.app,"_exact_dup_rows",[]))
                findings = [
                    f"{'⚠  ' if n_hr else '✓  '}{n_hr} high-risk duplicate transactions detected.",
                    f"{len(getattr(self.app,'_sus_rows',[]))} suspicious repeated-amount patterns identified.",
                    f"{len(getattr(self.app,'_shared_wallet_rows',[]))} shared wallet incidents found.",
                ]
                for j, txt in enumerate(findings, len(fields)+7):
                    ws[f"A{j}"] = txt
                    ws[f"A{j}"].font = Font(color="1A2A45", size=10, name="Calibri")

            # ── 2. High Risk sheet ─────────────────────────────────────
            if self._checks["high_risk"].isChecked():
                ws = wb.create_sheet("High Risk Transactions")
                ws.sheet_view.showGridLines = False
                rows = getattr(self.app,"_exact_dup_rows",[])
                if rows:
                    all_keys = [k for k in rows[0].keys() if not k.startswith("_")]
                    for ci, k in enumerate(all_keys, 1):
                        c = ws.cell(1, ci, k)
                        c.font = _hdr_font(); c.fill = _hdr_fill()
                        c.alignment = Alignment(horizontal="center", vertical="center")
                    ws.row_dimensions[1].height = 20
                    ws.freeze_panes = "A2"
                    for ri, rd in enumerate(rows, 2):
                        fill = _hi_fill() if ri % 2 == 0 else _med_fill()
                        ws.row_dimensions[ri].height = 16
                        for ci, k in enumerate(all_keys, 1):
                            c = ws.cell(ri, ci, str(rd.get(k,"")))
                            c.font = _val_font(); c.fill = fill
                            c.border = _border()
                            c.alignment = Alignment(vertical="center")
                else:
                    ws["A1"] = "No high-risk transactions in current session."
                    ws["A1"].font = _sub_font()
                _auto_width(ws)

            # ── 3. Risk Scores sheet ───────────────────────────────────
            if self._checks["risk_scores"].isChecked():
                ws = wb.create_sheet("Cashier Risk Scores")
                ws.sheet_view.showGridLines = False
                df = getattr(self.app, "active_df", None)
                if df is not None and "Cashier Name" in df.columns:
                    headers = ["Cashier", "Score", "Band", "Duplicates",
                               "Suspicious", "Shared", "Hist. Disc."]
                    for ci, h in enumerate(headers, 1):
                        c = ws.cell(1, ci, h)
                        c.font = _hdr_font(); c.fill = _hdr_fill()
                        c.alignment = Alignment(horizontal="center", vertical="center")
                    ws.row_dimensions[1].height = 20
                    ws.freeze_panes = "A2"

                    dup_c = {}
                    for rd in getattr(self.app,"_exact_dup_rows",[]):
                        n = rd.get("Cashier Name",rd.get("Cashier",""))
                        dup_c[n] = dup_c.get(n,0)+1
                    sus_c = {}
                    for rd in getattr(self.app,"_sus_rows",[]):
                        n = rd.get("Cashier Name",rd.get("Cashier",""))
                        sus_c[n] = sus_c.get(n,0)+1
                    shr_c = {}
                    for rd in getattr(self.app,"_shared_wallet_rows",[]):
                        n = rd.get("Cashier Name",rd.get("Cashier",""))
                        shr_c[n] = shr_c.get(n,0)+1
                    hist_c = {}
                    try:
                        for fp in archive_files:
                            tmp = pd.read_excel(fp)
                            if "Cashier Name" in tmp.columns and "Small_Discrepancies" in tmp.columns:
                                for _, row in tmp.iterrows():
                                    n = str(row["Cashier Name"])
                                    hist_c[n] = hist_c.get(n,0)+int(row.get("Small_Discrepancies",0))
                    except Exception: pass

                    mx = lambda d: max(d.values(),default=1) or 1
                    # Weights: DUP=45, SUS=8, SHR=5, HIST=10 (slip not in export); sum=68
                    _EXP_MAX = 68
                    scores = []
                    for name in df["Cashier Name"].unique():
                        n = str(name)
                        raw = (45*(dup_c.get(n,0)/mx(dup_c)) +
                                8*(sus_c.get(n,0)/mx(sus_c)) +
                                5*(shr_c.get(n,0)/mx(shr_c)) +
                               10*(hist_c.get(n,0)/mx(hist_c)))
                        s = min(100, int(raw * 100 / _EXP_MAX))
                        band = "HIGH" if s>=61 else "MEDIUM" if s>=31 else "LOW"
                        scores.append((n,s,band,dup_c.get(n,0),sus_c.get(n,0),
                                       shr_c.get(n,0),hist_c.get(n,0)))
                    scores.sort(key=lambda x:x[1],reverse=True)

                    for ri, row in enumerate(scores, 2):
                        fill = _hi_fill() if ri%2==0 else _med_fill()
                        # Dark readable colors on light backgrounds
                        score_color = ("C0392B" if row[2]=="HIGH"
                                       else "1A5A8A" if row[2]=="MEDIUM"
                                       else "1E7A3A")
                        ws.row_dimensions[ri].height = 16
                        for ci, val in enumerate(row, 1):
                            c = ws.cell(ri, ci, val)
                            c.fill = fill; c.border = _border()
                            c.alignment = Alignment(vertical="center")
                            c.font = (Font(color=score_color, bold=True, size=10,
                                           name="Calibri")
                                      if ci==2 else _val_font())
                _auto_width(ws)

            # ── 4. Discrepancy History sheet ───────────────────────────
            if self._checks["disc_history"].isChecked():
                ws = wb.create_sheet("Discrepancy History")
                ws.sheet_view.showGridLines = False

                # Optional period banner
                hdr_row = 1
                if period_label != "All Time":
                    ws["A1"] = f"Period: {period_label}"
                    ws["A1"].font = Font(color="5A6E8A", italic=True, size=9, name="Calibri")
                    ws.row_dimensions[1].height = 13
                    hdr_row = 2

                all_rows = []
                for fp in archive_files:
                    try:
                        tmp = pd.read_excel(fp)
                        all_rows.append(tmp)
                    except Exception: pass
                if all_rows:
                    combined = pd.concat(all_rows, ignore_index=True)
                    cols = list(combined.columns)
                    for ci, h in enumerate(cols, 1):
                        c = ws.cell(hdr_row, ci, h)
                        c.font = _hdr_font(); c.fill = _hdr_fill()
                        c.alignment = Alignment(horizontal="center", vertical="center")
                    ws.row_dimensions[hdr_row].height = 20
                    ws.freeze_panes = f"A{hdr_row + 1}"
                    for ri, row in enumerate(combined.itertuples(index=False), hdr_row + 1):
                        fill = _hi_fill() if ri % 2 == 0 else _med_fill()
                        for ci, val in enumerate(row, 1):
                            c = ws.cell(ri, ci, str(val) if pd.notna(val) else "")
                            c.font = _val_font(); c.fill = fill; c.border = _border()
                else:
                    msg = ("No discrepancy archive found for the selected period."
                           if period_label != "All Time"
                           else "No discrepancy archive found.")
                    ws.cell(hdr_row, 1, msg).font = _sub_font()
                _auto_width(ws)

            # ── 5. Raw data ────────────────────────────────────────────
            if self._checks["raw_data"].isChecked():
                df = getattr(self.app,"active_df",None)
                ws = wb.create_sheet("Full Transaction Data")
                ws.sheet_view.showGridLines = False
                if df is not None and not df.empty:
                    cols = list(df.columns)
                    for ci, h in enumerate(cols,1):
                        c = ws.cell(1,ci,h)
                        c.font = _hdr_font(); c.fill = _hdr_fill()
                    for ri, row in enumerate(df.itertuples(index=False),2):
                        fill = _hi_fill() if ri%2==0 else _med_fill()
                        for ci, val in enumerate(row,1):
                            try:
                                cell_val = "" if pd.isna(val) else val
                            except (TypeError, ValueError):
                                cell_val = str(val)
                            c = ws.cell(ri, ci, cell_val)
                            c.font = _val_font(); c.fill = fill; c.border = _border()
                    _auto_width(ws)

            wb.save(path)
            self._status_lbl.setText(f"✓  Report saved to {os.path.basename(path)}")
            self._status_lbl.setStyleSheet(f"color:{Theme.OK};font-size:12px;font-weight:600;")

        except Exception as e:
            logging.exception("Unhandled exception")
            self._status_lbl.setText(f"Error: {e}")
            self._status_lbl.setStyleSheet(f"color:{Theme.DANGER};font-size:12px;")
        finally:
            self._gen_btn.setEnabled(True)

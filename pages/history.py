"""
pages/history — HistoryPage.
"""
import logging

import datetime
import glob
import os

import pandas as pd

from PySide6.QtCore import (
    QTimer, Qt
)
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QSplitter, QVBoxLayout, QWidget
)

from config import DISCREPANCY_DB_PATH, SLIP_HISTORY_DB

from theme import Theme

from utils import msg_err, msg_info, msg_warn, msg_yes, open_file_in_default_app

from widgets import Card, DataTable, FieldLabel





class HistoryPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        outer = QVBoxLayout(self); outer.setContentsMargins(20, 16, 20, 16); outer.setSpacing(14)

        # Two-column split
        split = QSplitter(Qt.Horizontal); split.setHandleWidth(8); split.setChildrenCollapsible(False)

        # ---- Discrepancies card ----
        dc = Card("◷  Small Discrepancies (≤€10)")
        dctrl = QHBoxLayout(); dctrl.setSpacing(10)
        dctrl.addWidget(FieldLabel("From"))
        self.hist_start = QLineEdit(); self.hist_start.setPlaceholderText("DD.MM.YYYY"); self.hist_start.setMaximumWidth(140)
        dctrl.addWidget(self.hist_start)
        dctrl.addWidget(FieldLabel("To"))
        self.hist_end = QLineEdit(); self.hist_end.setPlaceholderText("DD.MM.YYYY"); self.hist_end.setMaximumWidth(140)
        dctrl.addWidget(self.hist_end)
        sb = QPushButton("Search"); sb.setObjectName("primary")
        sb.clicked.connect(self.run_discrepancy_search); dctrl.addWidget(sb)
        dctrl.addStretch()
        dc.body.addLayout(dctrl)
        self.disc_table = DataTable(("Cashier", "Count"))
        self.disc_table.set_column_width("Cashier", 240)
        self.disc_table.set_column_width("Count", 80)
        dc.body.addWidget(self.disc_table)
        split.addWidget(dc)

        # ---- Slip history card ----
        sc = Card("▤  Slip Audit History")
        sctrl = QHBoxLayout(); sctrl.setSpacing(10)
        sctrl.addWidget(FieldLabel("Date"))
        self.date_combo = QComboBox(); self.date_combo.addItem("Select Date"); self.date_combo.setMinimumWidth(180)
        sctrl.addWidget(self.date_combo)
        vb = QPushButton("View"); vb.setObjectName("primary")
        vb.clicked.connect(self.view_slip_hist); sctrl.addWidget(vb)
        eb = QPushButton("Export")
        eb.clicked.connect(self.export_slip_audit); sctrl.addWidget(eb)
        sctrl.addStretch()
        sc.body.addLayout(sctrl)
        self.slip_hist_table = DataTable(("Cashier", "Sys", "Phy", "Diff"))
        self.slip_hist_table.set_column_width("Cashier", 220)
        for c in ("Sys", "Phy", "Diff"): self.slip_hist_table.set_column_width(c, 70)
        sc.body.addWidget(self.slip_hist_table)
        split.addWidget(sc)

        outer.addWidget(split, 1)

        QTimer.singleShot(50, self.refresh_slip_dates)

    def run_discrepancy_search(self):
        self.disc_table.clear()
        try:
            ss = self.hist_start.text().strip()
            es = self.hist_end.text().strip()
            if not ss or not es:
                msg_warn(self, "Missing", "Enter both dates"); return
            try:
                sd = datetime.datetime.strptime(ss, "%d.%m.%Y")
                ed = datetime.datetime.strptime(es, "%d.%m.%Y")
            except ValueError:
                msg_err(self, "Invalid", "Use DD.MM.YYYY"); return
            if sd > ed:
                msg_warn(self, "Invalid", "Start must be before end"); return
            files = glob.glob(os.path.join(DISCREPANCY_DB_PATH, "**", "*.xlsx"), recursive=True)
            vdfs = []
            for f in files:
                try:
                    fn = os.path.basename(f).replace(".xlsx", "")
                    fd = datetime.datetime.strptime(fn, "%d.%m.%Y")
                    if sd <= fd <= ed:
                        d = pd.read_excel(f)
                        if not d.empty: vdfs.append(d)
                except Exception:
                    continue
            if not vdfs:
                msg_info(self, "None", f"No records for {ss} - {es}"); return
            combined = pd.concat(vdfs, ignore_index=True)
            sm = (combined.groupby(['Cashier Name'])['Small_Discrepancies']
                  .sum().reset_index().sort_values('Small_Discrepancies', ascending=False))
            for _, r in sm.iterrows():
                self.disc_table.add_row({
                    "Cashier": str(r['Cashier Name'])[:30],
                    "Count":   int(r['Small_Discrepancies']),
                })
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

    def refresh_slip_dates(self):
        if not os.path.exists(SLIP_HISTORY_DB): return
        try:
            df = pd.read_csv(SLIP_HISTORY_DB)
            if 'Date' not in df.columns: return
            # Only show dates that have real slip audit rows (Physical Count present)
            if 'Physical Count' in df.columns:
                df = df[df['Physical Count'].notna()]
            dates = sorted(df['Date'].dropna().unique().tolist(),
                           key=lambda x: datetime.datetime.strptime(x, "%d.%m.%Y"),
                           reverse=True)
            if dates:
                self.date_combo.clear()
                for d in dates: self.date_combo.addItem(d)
        except Exception:
            pass

    def view_slip_hist(self):
        self.slip_hist_table.clear()
        if not os.path.exists(SLIP_HISTORY_DB):
            msg_warn(self, "No Data", "No history"); return
        try:
            sd = self.date_combo.currentText()
            if sd == "Select Date":
                msg_warn(self, "Select", "Pick a date"); return
            df = pd.read_csv(SLIP_HISTORY_DB)
            if 'Physical Count' not in df.columns or 'Difference' not in df.columns:
                msg_info(self, "No Slip Audits", "No slip audit records found.\n\nRun a Slip Audit first."); return
            filt = df[(df['Date'] == sd) & df['Physical Count'].notna()].sort_values('Name')
            if filt.empty:
                msg_info(self, "None", f"No slip audit records for {sd}"); return
            bc, uc = 0, 0
            for ridx, r in filt.iterrows():
                try:
                    d = int(float(r['Difference']))
                except (ValueError, TypeError):
                    d = 0
                if d == 0: bc += 1
                else: uc += 1
                meta = {"fg": Theme.POS if d == 0 else Theme.NEG}
                self.slip_hist_table.add_row({
                    "Cashier": str(r['Name'])[:25],
                    "Sys": int(float(r['System Count'])),
                    "Phy": int(float(r['Physical Count'])),
                    "Diff": f"{d:+d}" if d else "0",
                }, meta=meta)
            msg_info(self, "Summary",
                     f"Date: {sd}\n\n✓ Balanced: {bc}\n✕ Unbalanced: {uc}\nTotal: {bc+uc}")
        except Exception as e:
            logging.exception("Unhandled exception")

    def export_slip_audit(self):
        if not os.path.exists(SLIP_HISTORY_DB):
            msg_warn(self, "No Data", "No history"); return
        try:
            sd = self.date_combo.currentText()
            if sd == "Select Date":
                msg_warn(self, "Select", "Pick a date"); return
            df = pd.read_csv(SLIP_HISTORY_DB)
            if 'Physical Count' not in df.columns:
                msg_warn(self, "No Data", "No slip audit records found."); return
            # Export only slip audit rows with the clean set of columns
            audit_cols = [c for c in ["Date", "Name", "System Count", "Physical Count",
                                       "Difference", "Total Value"] if c in df.columns]
            edf = df[(df['Date'] == sd) & df['Physical Count'].notna()].copy().sort_values("Name")[audit_cols]
            if edf.empty:
                msg_warn(self, "No Data", f"No slip audit records for {sd}"); return
            fp, _ = QFileDialog.getSaveFileName(self, "Export", f"Slip_Audit_{sd.replace('.', '-')}.xlsx", "Excel (*.xlsx)")
            if not fp: return
            with pd.ExcelWriter(fp, engine='openpyxl') as w:
                edf.to_excel(w, sheet_name='Slip Audit', index=False)
                ws = w.sheets['Slip Audit']
                cols_list = list(edf.columns)
                for i, col in enumerate(cols_list):
                    ws.column_dimensions[chr(65+i)].width = max(edf[col].astype(str).map(len).max(), len(col)) + 2
                tr = len(edf) + 2
                ws.cell(row=tr, column=1, value="TOTALS:")
                for col_name in ("System Count", "Physical Count", "Difference"):
                    if col_name in cols_list:
                        ws.cell(row=tr, column=cols_list.index(col_name) + 1,
                                value=int(float(edf[col_name].sum())))
            msg_info(self, "Done", f"Exported to:\n{fp}")
            if msg_yes(self, "Open?", "Open file?"):
                open_file_in_default_app(fp)
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

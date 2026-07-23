"""
pages/discovery — AmountDiscoveryPage.
"""

import datetime
import logging
import os

from openpyxl import load_workbook

try:
    import xlrd
except ImportError:
    xlrd = None

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget
)

from config import NON_VMS_BASE_FOLDER, NON_VMS_CONFIG, XLRD_AVAILABLE

from utils import msg_err, msg_info, msg_warn

from widgets import Card, DataTable, DetailDialog, FieldLabel, StatusPill





class AmountDiscoveryPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        outer = QVBoxLayout(self); outer.setContentsMargins(20, 16, 20, 16); outer.setSpacing(14)

        # Config card
        cfg = Card("Search", "search IR reports by date range + optional Location ID / Name / Amount")
        # Row 1: Date range + year
        r1 = QHBoxLayout(); r1.setSpacing(10)
        r1.addWidget(FieldLabel("Start"))
        self.start = QLineEdit(); self.start.setPlaceholderText("DD/MM/YYYY"); self.start.setMaximumWidth(150)
        r1.addWidget(self.start)
        r1.addWidget(FieldLabel("End"))
        self.end = QLineEdit(); self.end.setPlaceholderText("DD/MM/YYYY"); self.end.setMaximumWidth(150)
        r1.addWidget(self.end)
        r1.addWidget(FieldLabel("Year"))
        cy = datetime.datetime.now().year
        self.year_combo = QComboBox()
        for y in range(cy - 2, cy + 2): self.year_combo.addItem(str(y))
        self.year_combo.setCurrentText(str(cy)); self.year_combo.setMaximumWidth(110)
        r1.addWidget(self.year_combo)
        r1.addStretch()
        cfg.body.addLayout(r1)

        # Row 2: filters
        r2 = QHBoxLayout(); r2.setSpacing(10)
        r2.addWidget(FieldLabel("Location ID"))
        self.f_id = QLineEdit(); self.f_id.setPlaceholderText("e.g. 12345 (exact)"); self.f_id.setMaximumWidth(180)
        r2.addWidget(self.f_id)
        r2.addWidget(FieldLabel("Loc Name"))
        self.f_name = QLineEdit(); self.f_name.setPlaceholderText("partial, case-insensitive"); self.f_name.setMaximumWidth(260)
        r2.addWidget(self.f_name)
        r2.addWidget(FieldLabel("Amount"))
        self.f_amount = QLineEdit(); self.f_amount.setPlaceholderText("exact"); self.f_amount.setMaximumWidth(140)
        r2.addWidget(self.f_amount)
        r2.addStretch()
        cfg.body.addLayout(r2)

        # Row 3: actions
        r3 = QHBoxLayout(); r3.setSpacing(10)
        sb = QPushButton("Search"); sb.setObjectName("primary"); sb.setMinimumHeight(36); sb.setMinimumWidth(140)
        sb.clicked.connect(self.run_discovery); r3.addWidget(sb)
        cb = QPushButton("Clear"); cb.setMinimumHeight(36); cb.setMinimumWidth(100)
        cb.clicked.connect(self.clear_results); r3.addWidget(cb)
        r3.addWidget(QLabel("  uses IR Path from NON-VMS tab"))
        r3.addStretch()
        self.status = StatusPill("Enter date range, optional filters, click Search", "muted")
        r3.addWidget(self.status)
        cfg.body.addLayout(r3)
        outer.addWidget(cfg)

        # Results
        rc = Card("Results", "double-click a row to view full Excel line")
        self.table = DataTable(("Date", "Location ID", "Location Name", "Amount", "Report Name", "Folder Path"))
        self.table.set_column_width("Date", 100)
        self.table.set_column_width("Location ID", 110)
        self.table.set_column_width("Location Name", 220)
        self.table.set_column_width("Amount", 110)
        self.table.set_column_width("Report Name", 280)
        self.table.rowDoubleClicked.connect(self._show_detail)
        rc.body.addWidget(self.table)
        outer.addWidget(rc, 1)

    # ---- Helpers ----
    def clear_results(self):
        self.table.clear(); self.app.nonvms_disc_results = []
        self.status.set("Cleared", "muted")

    @staticmethod
    def _parse_b2_date(value):
        if value is None or value == "": return None
        if isinstance(value, datetime.datetime): return value.date()
        if isinstance(value, datetime.date): return value
        if isinstance(value, (int, float)):
            try:
                base = datetime.datetime(1899, 12, 30)
                return (base + datetime.timedelta(days=float(value))).date()
            except Exception: return None
        s = str(value).strip()
        for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y",
                    "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%y", "%d.%m.%y"):
            try: return datetime.datetime.strptime(s, fmt).date()
            except ValueError: continue
        return None

    @staticmethod
    def _to_float(v):
        if v is None or v == "": return None
        if isinstance(v, (int, float)):
            try: return float(v)
            except Exception: return None
        s = str(v).strip()
        if not s: return None
        cleaned = (s.replace("\u20ac", "").replace("$", "").replace("\u00a3", "")
                    .replace(",", "").replace(" ", ""))
        try: return float(cleaned)
        except ValueError: return None

    def _read_xlsx(self, fp):
        try:
            wb = load_workbook(fp, data_only=True, read_only=True)
            ws = wb.worksheets[0]; b2 = ws["B2"].value
            rows = []
            for i, r in enumerate(ws.iter_rows(min_row=1, max_col=6, values_only=True), start=1):
                r = list(r) + [None] * (6 - len(r))
                rows.append((i, r[0], r[1], r[2], r[3], r[4], r[5]))
            try: wb.close()
            except Exception: pass
            return b2, rows
        except Exception as e:
            logging.warning(f"Discovery: cannot read xlsx {fp}: {e}")
            return None, []

    def _read_xls(self, fp):
        if not XLRD_AVAILABLE: return None, []
        try:
            wb = xlrd.open_workbook(fp); ws = wb.sheet_by_index(0)
            b2 = None
            if ws.nrows > 1 and ws.ncols > 1:
                cv = ws.cell_value(1, 1); ct = ws.cell_type(1, 1)
                if ct == 3:
                    try:
                        tup = xlrd.xldate_as_tuple(cv, wb.datemode)
                        b2 = datetime.datetime(*tup)
                    except Exception: b2 = cv
                else: b2 = cv
            rows = []
            for i in range(ws.nrows):
                vals = [ws.cell_value(i, c) if c < ws.ncols else None for c in range(6)]
                rows.append((i + 1, vals[0], vals[1], vals[2], vals[3], vals[4], vals[5]))
            return b2, rows
        except Exception as e:
            logging.warning(f"Discovery: cannot read xls {fp}: {e}")
            return None, []

    def run_discovery(self):
        self.table.clear(); self.app.nonvms_disc_results = []
        sd_str = self.start.text().strip()
        ed_str = self.end.text().strip()
        if not sd_str or not ed_str:
            msg_warn(self, "Missing", "Enter both Start and End Date"); return
        try:
            sd = datetime.datetime.strptime(sd_str, "%d/%m/%Y").date()
            ed = datetime.datetime.strptime(ed_str, "%d/%m/%Y").date()
        except ValueError:
            msg_err(self, "Invalid", "Use DD/MM/YYYY for both dates"); return
        if sd > ed:
            msg_err(self, "Invalid", "Start must be ≤ End"); return

        f_id = self.f_id.text().strip()
        f_name = self.f_name.text().strip().lower()
        f_amount_raw = self.f_amount.text().strip()
        f_amount_num = self._to_float(f_amount_raw) if f_amount_raw else None

        yr = self.year_combo.currentText()
        nonvms_page = self.app.pages.get('nonvms')
        ir_base = nonvms_page.ir_path.text().strip() if nonvms_page else NON_VMS_BASE_FOLDER
        if not ir_base or not os.path.exists(ir_base):
            msg_err(self, "Path", f"IR Path does not exist: {ir_base}"); return

        self.status.set(f"Scanning {yr} {sd_str}–{ed_str}...", "warning")
        QApplication.processEvents()

        files_seen = files_in_range = files_skipped = matches = 0
        try:
            for loc in NON_VMS_CONFIG.keys():
                lf = os.path.join(ir_base, loc, yr)
                if not os.path.exists(lf): continue
                for root, _, files in os.walk(lf):
                    for fname in files:
                        if fname.startswith("~$"): continue
                        low = fname.lower()
                        if not low.endswith((".xls", ".xlsx")): continue
                        fp = os.path.join(root, fname); files_seen += 1

                        b2_raw, rows = self._read_xls(fp) if low.endswith(".xls") else self._read_xlsx(fp)
                        if not rows:
                            files_skipped += 1; continue
                        b2_date = self._parse_b2_date(b2_raw)
                        if b2_date is None:
                            files_skipped += 1; continue
                        if not (sd <= b2_date <= ed): continue
                        files_in_range += 1

                        rep_date_str = b2_date.strftime("%d/%m/%Y")
                        for (row_idx, a, b, c_val, d, e, f) in rows:
                            amount_num = self._to_float(d)
                            if amount_num is None or amount_num <= 0: continue

                            if f_id:
                                a_str = "" if a is None else str(a).strip()
                                try:
                                    if isinstance(a, float) and a.is_integer():
                                        a_str = str(int(a))
                                except Exception: pass
                                if a_str != f_id: continue

                            if f_name:
                                b_str = "" if b is None else str(b).lower()
                                if f_name not in b_str: continue

                            if f_amount_raw:
                                if f_amount_num is not None:
                                    if amount_num != f_amount_num: continue
                                else:
                                    if str(d).strip() != f_amount_raw: continue

                            if isinstance(a, float) and a.is_integer():
                                loc_id_disp = str(int(a))
                            else:
                                loc_id_disp = "" if a is None else str(a)
                            loc_name_disp = "" if b is None else str(b)
                            amount_disp = d
                            if isinstance(d, float) and d.is_integer():
                                amount_disp = int(d)

                            rec = {
                                "Date": rep_date_str,
                                "Location ID": loc_id_disp,
                                "Location Name": loc_name_disp,
                                "Expected Notes": c_val,
                                "Actual Notes": d,
                                "Col E": e,
                                "Col F": f,
                                "Report Name": fname,
                                "Report Folder Path": root,
                                "Full Path": fp,
                                "IR Location": loc,
                                "_line": row_idx,
                            }
                            self.app.nonvms_disc_results.append(rec)
                            self.table.add_row({
                                "Date": rep_date_str,
                                "Location ID": loc_id_disp,
                                "Location Name": loc_name_disp,
                                "Amount": amount_disp,
                                "Report Name": fname,
                                "Folder Path": root,
                            }, meta={"_rd": rec})
                            matches += 1

            self.status.set(
                f"{matches} match(es) | {files_in_range}/{files_seen} files in range | "
                f"{files_skipped} skipped",
                "success" if matches else "warning")
            if matches == 0:
                msg_info(self, "No Matches",
                    f"No matching rows found.\n\n"
                    f"Files scanned: {files_seen}\nFiles in date range: {files_in_range}\n"
                    f"Files skipped: {files_skipped}")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))
            self.status.set(f"Error: {e}", "danger")

    def _show_detail(self, displayed):
        # Match by report name + line number to find the rec
        rep = displayed.get("Report Name"); date = displayed.get("Date")
        for rec in self.app.nonvms_disc_results:
            if rec.get("Report Name") == rep and rec.get("Date") == date:
                # Try also location id to pick the right line
                if displayed.get("Location ID") == rec.get("Location ID"):
                    title = (f"{rec.get('Location Name') or rec.get('Location ID') or 'Row'} · "
                             f"Line {rec.get('_line', '?')}")
                    ordered = {
                        "Date":               rec.get("Date", ""),
                        "Location ID (A)":    rec.get("Location ID", ""),
                        "Location Name (B)":  rec.get("Location Name", ""),
                        "Expected Notes (C)": rec.get("Expected Notes", ""),
                        "Actual Notes (D)":   rec.get("Actual Notes", ""),
                        "Col E":              rec.get("Col E", ""),
                        "Col F":              rec.get("Col F", ""),
                        "Report Name":        rec.get("Report Name", ""),
                        "Report Folder Path": rec.get("Report Folder Path", ""),
                        "Full Path":          rec.get("Full Path", ""),
                        "IR Location":        rec.get("IR Location", ""),
                        "_line":              rec.get("_line", ""),
                    }
                    DetailDialog.show_row(self.app, title, ordered)
                    return

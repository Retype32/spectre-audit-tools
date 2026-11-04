"""
pages/nonvms — NonVmsPage.
"""

import datetime
import logging
import os
import re
import shutil

from openpyxl import load_workbook

try:
    import xlrd
except ImportError:
    xlrd = None

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget
)

from config import (
    DBC_FOLDER, DUBLIN_DSC_AMOUNTS, JOLLYES_BASE, NON_VMS_BASE_FOLDER, NON_VMS_CONFIG,
    NON_VMS_TEXT_PREFIX, XLRD_AVAILABLE,
)

from utils import msg_err, msg_info, msg_warn, msg_yes, open_file_in_default_app

from widgets import Card, DataTable, FieldLabel, StatusPill





def _summary_text(location, tickets, date):
    """One clipboard line per report, prefixed by NON_VMS_TEXT_PREFIX if set."""
    parts = (NON_VMS_TEXT_PREFIX, location, f"({tickets})", date)
    return " ".join(p for p in parts if p)


class NonVmsPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        outer = QVBoxLayout(self); outer.setContentsMargins(20, 16, 20, 16); outer.setSpacing(14)

        # Config card
        cfg = Card("Scan Configuration")
        # Row 1: Scan date + Year + Scan
        r1 = QHBoxLayout(); r1.setSpacing(10)
        r1.addWidget(FieldLabel("Scan Date"))
        self.scan_date = QLineEdit(); self.scan_date.setPlaceholderText("DD/MM/YYYY"); self.scan_date.setMaximumWidth(140)
        r1.addWidget(self.scan_date)
        r1.addWidget(FieldLabel("Year"))
        cy = datetime.datetime.now().year
        self.year_combo = QComboBox()
        for y in range(cy - 2, cy + 2): self.year_combo.addItem(str(y))
        self.year_combo.setCurrentText(str(cy)); self.year_combo.setMaximumWidth(110)
        r1.addWidget(self.year_combo)
        r1.addWidget(FieldLabel("DBC Date"))
        self.dbc_date = QLineEdit(); self.dbc_date.setPlaceholderText("DD/MM/YYYY"); self.dbc_date.setMaximumWidth(140)
        r1.addWidget(self.dbc_date)
        r1.addStretch()
        scan_btn = QPushButton("Scan Files"); scan_btn.setObjectName("primary"); scan_btn.setMinimumWidth(140)
        scan_btn.clicked.connect(self.scan_nonvms_files); r1.addWidget(scan_btn)
        cfg.body.addLayout(r1)

        # Path rows
        def _path_row(label, default):
            lay = QHBoxLayout(); lay.setSpacing(8)
            lay.addWidget(FieldLabel(label))
            ent = QLineEdit(); ent.setText(default); ent.setMinimumWidth(420)
            lay.addWidget(ent, 1)
            br = QPushButton("..."); br.setMaximumWidth(40)
            br.clicked.connect(lambda: self._browse(ent))
            lay.addWidget(br)
            cfg.body.addLayout(lay)
            return ent

        self.ir_path     = _path_row("IR Path", NON_VMS_BASE_FOLDER)
        self.jollyes_path = _path_row("Jollyes", JOLLYES_BASE)
        DESKTOP_DEFAULT = os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')), 'Desktop')
        self.copy_path  = _path_row("Copy To", os.path.join(DESKTOP_DEFAULT, "NON VMS Reports"))

        # DBC row
        dbc_row = QHBoxLayout(); dbc_row.setSpacing(8)
        dbc_row.addWidget(FieldLabel("DBC Folder"))
        self.dbc_folder = QLineEdit(); self.dbc_folder.setText(DBC_FOLDER); self.dbc_folder.setMinimumWidth(280)
        dbc_row.addWidget(self.dbc_folder)
        dbc_row.addWidget(FieldLabel("Template"))
        self.dbc_template = QLineEdit(); self.dbc_template.setText("Brinks Mini Ledger Master Version.xlsx")
        self.dbc_template.setMinimumWidth(280)
        dbc_row.addWidget(self.dbc_template, 1)
        cfg.body.addLayout(dbc_row)
        outer.addWidget(cfg)

        # Results table
        results_card = Card("Scan Results", "")
        self.results_table = DataTable(("Location", "Tickets", "Date",
                                        "500", "200", "100", "50", "20", "10", "5", "Coins"))
        self.results_table.set_column_width("Location", 160)
        for c in ("Tickets", "Date"): self.results_table.set_column_width(c, 80)
        for c in ("500", "200", "100", "50", "20", "10", "5", "Coins"):
            self.results_table.set_column_width(c, 60)
        results_card.body.addWidget(self.results_table)
        outer.addWidget(results_card, 1)

        # Action bar
        action_card = Card()
        al = QHBoxLayout(); al.setSpacing(10)
        cb = QPushButton("Copy to Clipboard"); cb.clicked.connect(self.copy_nonvms_to_clipboard); al.addWidget(cb)
        db = QPushButton("Create DBC"); db.setObjectName("success"); db.clicked.connect(self.create_dbc); al.addWidget(db)
        al.addStretch()
        self.status = StatusPill("Enter date, select year, click Scan", "muted")
        al.addWidget(self.status)
        action_card.body.addLayout(al)
        outer.addWidget(action_card)

    def _browse(self, line_edit):
        d = QFileDialog.getExistingDirectory(self, "Select Folder")
        if d: line_edit.setText(d)

    def scan_nonvms_files(self):
        self.results_table.clear(); self.app.nonvms_results = []
        try:
            ds = self.scan_date.text().strip()
            if not ds:
                msg_warn(self, "Missing", "Enter scan date"); return
            try:
                scan_date = datetime.datetime.strptime(ds, "%d/%m/%Y").date()
            except ValueError:
                msg_err(self, "Invalid", "Use DD/MM/YYYY"); return
            yr = self.year_combo.currentText()
            self.status.set(f"Scanning {yr}...", "warning"); QApplication.processEvents()

            ir_base = self.ir_path.text().strip()
            jb = self.jollyes_path.text().strip()
            cdest = self.copy_path.text().strip()
            os.makedirs(cdest, exist_ok=True)

            ff, fc = 0, 0
            for loc, cfg in NON_VMS_CONFIG.items():
                lf = os.path.join(ir_base, loc, yr)
                if not os.path.exists(lf): continue
                for root, _, files in os.walk(lf):
                    for file in files:
                        if file.startswith("~$") or not file.lower().endswith((".xls", ".xlsx")): continue
                        fp = os.path.join(root, file)
                        try:
                            cd2 = datetime.datetime.fromtimestamp(os.path.getctime(fp)).date()
                        except Exception:
                            continue
                        if cd2 != scan_date: continue
                        ff += 1
                        # Copy
                        try:
                            nm = os.path.basename(fp); dst = os.path.join(cdest, nm)
                            base, ext = os.path.splitext(nm); i = 1
                            while os.path.exists(dst):
                                dst = os.path.join(cdest, f"{base} ({i}){ext}"); i += 1
                            shutil.copy2(fp, dst); fc += 1
                        except Exception:
                            pass

                        match = re.search(r"\d{2}\.\d{2}\.\d{4}", file)
                        fdate = match.group() if match else scan_date.strftime("%d.%m.%Y")
                        is_dsc = "DSC" in file.upper()
                        cl, st, en = cfg["tickets"]
                        if loc == "Dublin" and is_dsc:
                            amcfg = DUBLIN_DSC_AMOUNTS; dloc = "IR Dublin DSC"; st, en = 7, 39
                        else:
                            amcfg = cfg["amounts"]; dloc = f"IR {loc}"
                        dens = {k: 0 for k in amcfg}; tc = 0
                        try:
                            if file.lower().endswith(".xls") and XLRD_AVAILABLE:
                                wb = xlrd.open_workbook(fp); ws = wb.sheet_by_index(0)
                                ci = ord(cl) - 65
                                for r in range(st - 1, en):
                                    if r < ws.nrows and ws.cell_value(r, ci) not in ("", None):
                                        tc += 1
                                for d, cell in amcfg.items():
                                    if isinstance(cell, str):
                                        rr, cc2 = int(cell[1:]) - 1, ord(cell[0]) - 65
                                        if rr < ws.nrows: dens[d] = ws.cell_value(rr, cc2) or 0
                            else:
                                wb = load_workbook(fp, data_only=True); ws = wb.worksheets[0]
                                for r in range(st, en + 1):
                                    if ws[f"{cl}{r}"].value not in ("", None):
                                        tc += 1
                                for d, cell in amcfg.items():
                                    if isinstance(cell, str): dens[d] = ws[cell].value or 0
                        except Exception as e:
                            logging.error(f"Read error {fp}: {e}"); continue

                        res = {
                            "location": dloc, "tickets": tc, "date": fdate,
                            "amounts": [dens.get(d, 0) for d in ["500","200","100","50","20","10","5"]],
                            "coins": dens.get("Coins", ""),
                            "text": _summary_text(dloc, tc, fdate),
                        }
                        self.app.nonvms_results.append(res)
                        self.results_table.add_row({
                            "Location": dloc, "Tickets": tc, "Date": fdate,
                            "500":  dens.get("500", 0),  "200": dens.get("200", 0),
                            "100":  dens.get("100", 0),  "50":  dens.get("50", 0),
                            "20":   dens.get("20", 0),   "10":  dens.get("10", 0),
                            "5":    dens.get("5", 0),    "Coins": dens.get("Coins", ""),
                        })

            # Jollyes
            jy = os.path.join(jb, yr)
            if os.path.exists(jy):
                for root, _, files in os.walk(jy):
                    for file in files:
                        if file.startswith("~$") or not file.lower().endswith((".xls", ".xlsx")): continue
                        fp = os.path.join(root, file)
                        try:
                            cd2 = datetime.datetime.fromtimestamp(os.path.getctime(fp)).date()
                        except Exception:
                            continue
                        if cd2 != scan_date: continue
                        ff += 1
                        match = re.search(r"\d{2}\.\d{2}\.\d{4}", file)
                        fdate = match.group() if match else scan_date.strftime("%d.%m.%Y")
                        dens = {d: 0 for d in ["500","200","100","50","20","10","5"]}
                        coins = ""; tc = 0
                        try:
                            if file.lower().endswith(".xls") and XLRD_AVAILABLE:
                                wb = xlrd.open_workbook(fp); ws = wb.sheet_by_index(0)
                                for r in range(9, 48):
                                    if r < ws.nrows and ws.cell_value(r, 1) not in ("", None): tc += 1
                                if ws.nrows > 51:
                                    for idx2, d in enumerate(["500","200","100","50","20","10","5"]):
                                        dens[d] = ws.cell_value(51, 3 + idx2) or 0
                                    coins = ws.cell_value(51, 11) or ""
                            else:
                                wb = load_workbook(fp, data_only=True); ws = wb.worksheets[0]
                                for r in range(10, 49):
                                    if ws[f"B{r}"].value not in ("", None): tc += 1
                                for ch, d in zip("DEFGHIJ", ["500","200","100","50","20","10","5"]):
                                    dens[d] = ws[f"{ch}52"].value or 0
                                coins = ws["L52"].value or ""
                        except Exception as e:
                            logging.error(f"Jollyes error {fp}: {e}"); continue

                        res = {"location": "Jollyes", "tickets": tc, "date": fdate,
                               "amounts": [dens[d] for d in ["500","200","100","50","20","10","5"]],
                               "coins": coins,
                               "text": _summary_text("Jollyes", tc, fdate)}
                        self.app.nonvms_results.append(res)
                        self.results_table.add_row({
                            "Location": "Jollyes", "Tickets": tc, "Date": fdate,
                            "500": dens["500"], "200": dens["200"], "100": dens["100"],
                            "50": dens["50"], "20": dens["20"], "10": dens["10"],
                            "5": dens["5"], "Coins": coins,
                        })

            self.status.set(f"✓ {ff} files in {yr} ({fc} copied)", "success")
            if not self.app.nonvms_results:
                msg_info(self, "None", f"No files for {ds} in {yr}")
            else:
                msg_info(self, "Done", f"{len(self.app.nonvms_results)} entries · {fc} copied")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))
            self.status.set(f"Error: {e}", "danger")

    def copy_nonvms_to_clipboard(self):
        if not self.app.nonvms_results:
            msg_warn(self, "No Data", "Run scan first"); return
        lines = []
        for r in self.app.nonvms_results:
            lines.append(r["text"])
            lines.append("\t".join(str(a) for a in r["amounts"]))
            if r["coins"] != "":
                lines.append(f"Coins:\t{r['coins']}")
            lines.append("-" * 50)
        QApplication.clipboard().setText("\n".join(lines))
        msg_info(self, "Copied", "Copied to clipboard")

    def create_dbc(self):
        if not self.app.nonvms_results:
            msg_warn(self, "No Data", "Run scan first"); return
        try:
            dds = self.dbc_date.text().strip()
            if not dds:
                msg_warn(self, "Missing", "Enter DBC date"); return
            try:
                dd = datetime.datetime.strptime(dds, "%d/%m/%Y").date()
            except ValueError:
                msg_err(self, "Invalid", "Use DD/MM/YYYY"); return
            db = self.dbc_folder.text().strip()
            tn = self.dbc_template.text().strip()
            yf = os.path.join(db, str(dd.year))
            mf = os.path.join(yf, f"{dd.month}. {dd.strftime('%B')} {dd.year}")
            os.makedirs(mf, exist_ok=True)
            dfn = f"Brinks Mini Ledger Master {dd.strftime('%d.%m.%Y')}.xlsx"
            dp = os.path.join(mf, dfn)
            if os.path.exists(dp) and not msg_yes(self, "Exists", f"Overwrite?\n{dp}"):
                return
            DESKTOP_DEFAULT = os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')), 'Desktop')
            tp = os.path.join(DESKTOP_DEFAULT, tn)
            if not os.path.exists(tp):
                tp, _ = QFileDialog.getOpenFileName(self, "Select Template", tn, "Excel (*.xlsx);;All (*.*)")
                if not tp: return
            shutil.copy2(tp, dp)
            wb = load_workbook(dp)
            dstr = dd.strftime("%d.%m.%Y")
            for tab in ("Strong Room COIN", "Strong Room NOTES"):
                if tab in wb.sheetnames:
                    wb[tab]["H3"] = dstr
            if len(wb.worksheets) > 6:
                ws = wb.worksheets[6]
                row = 16
                for r in self.app.nonvms_results:
                    ws[f"A{row}"] = r["text"]
                    for i, val in enumerate(r["amounts"], start=2):
                        if val and val != 0:
                            ws.cell(row=row, column=i, value=val)
                    if r["coins"] != "" and r["coins"] != 0:
                        ws[f"T{row}"] = r["coins"]
                    row += 1
            wb.save(dp)
            msg_info(self, "Created", f"DBC saved to:\n{dp}")
            if msg_yes(self, "Open?", "Open DBC?"):
                open_file_in_default_app(dp)
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

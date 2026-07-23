"""
pages/no3 — No3Page.
"""

import datetime
import logging
import re

from openpyxl import load_workbook

from openpyxl.styles import PatternFill

from pathlib import Path

from openpyxl import Workbook

from PySide6.QtCore import (
    Qt
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget
)

from config import NO3_ALLOWED_YEARS, NO3_DATABASE_PATH, NO3_OUTPUT_BASE, NO3_TEMPLATE_PATH, NO3_TRACKER_DIR

from theme import Theme

from utils import msg_err, msg_info, msg_warn, msg_yes

from widgets import Card, DataTable, FieldLabel, StatusPill





class No3Page(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        outer = QVBoxLayout(self); outer.setContentsMargins(20, 16, 20, 16); outer.setSpacing(14)

        # Config card
        cfg = Card("Configuration", "Auto-create SL79 forms from database")
        # Year
        r1 = QHBoxLayout(); r1.setSpacing(10)
        r1.addWidget(FieldLabel("Year"))
        self.year_combo = QComboBox()
        for y in NO3_ALLOWED_YEARS: self.year_combo.addItem(y)
        self.year_combo.setCurrentText(NO3_ALLOWED_YEARS[0])
        self.year_combo.setMaximumWidth(140)
        r1.addWidget(self.year_combo)
        r1.addWidget(QLabel("Select the year for SL79 processing (2026-2030)"))
        r1.addStretch()
        cfg.body.addLayout(r1)

        # Database row
        r2 = QHBoxLayout(); r2.setSpacing(8)
        r2.addWidget(FieldLabel("Database"))
        self.db_path = QLineEdit(); self.db_path.setText(str(NO3_DATABASE_PATH))
        self.db_path.setMinimumWidth(560)
        r2.addWidget(self.db_path, 1)
        b1 = QPushButton("..."); b1.setMaximumWidth(40)
        b1.clicked.connect(lambda: self._pick_file(self.db_path, "Excel Database (*.xlsx)"))
        r2.addWidget(b1)
        cfg.body.addLayout(r2)

        # Template row
        r3 = QHBoxLayout(); r3.setSpacing(8)
        r3.addWidget(FieldLabel("Template"))
        self.tmpl_path = QLineEdit(); self.tmpl_path.setText(str(NO3_TEMPLATE_PATH))
        self.tmpl_path.setMinimumWidth(560)
        r3.addWidget(self.tmpl_path, 1)
        b2 = QPushButton("..."); b2.setMaximumWidth(40)
        b2.clicked.connect(lambda: self._pick_file(self.tmpl_path, "Excel Template (*.xlsx)"))
        r3.addWidget(b2)
        cfg.body.addLayout(r3)
        outer.addWidget(cfg)

        # Info card
        info = Card("Status")
        ig = QGridLayout(); ig.setHorizontalSpacing(28)
        self.info_lbls = {}
        for col, (k, v) in enumerate([("Tracker", "Auto-detected by Year"),
                                      ("Output Folder", str(NO3_OUTPUT_BASE)),
                                      ("Status", "Ready")]):
            lbl = QLabel(k); lbl.setObjectName("sectionLabel")
            val = QLabel(v); val.setStyleSheet(f"color:{Theme.TXT}; font-size:12px;")
            ig.addWidget(lbl, 0, col); ig.addWidget(val, 1, col)
            self.info_lbls[k] = val
        info.body.addLayout(ig)
        outer.addWidget(info)

        # Action button
        action = Card()
        ac = QHBoxLayout(); ac.addStretch()
        bigbtn = QPushButton("⚡  Scan Database & Create Forms")
        bigbtn.setObjectName("success"); bigbtn.setMinimumHeight(48); bigbtn.setMinimumWidth(320)
        bigbtn.setStyleSheet(f"font-size:14px; font-weight:600;")
        bigbtn.clicked.connect(self.scan_and_create)
        ac.addWidget(bigbtn); ac.addStretch()
        action.body.addLayout(ac)
        sub = QLabel("Scans database, shows transactions, collects slip numbers, creates SL79 forms")
        sub.setStyleSheet(f"color:{Theme.TXT_3}; font-size:11px;"); sub.setAlignment(Qt.AlignCenter)
        action.body.addWidget(sub)
        outer.addWidget(action)

        # Preview table
        prev = Card("Transaction Preview", "first 20 valid transactions")
        self.table = DataTable(("Row", "Line", "Date", "Customer", "Value", "Details"))
        self.table.set_column_width("Row", 70); self.table.set_column_width("Line", 90)
        self.table.set_column_width("Date", 110); self.table.set_column_width("Customer", 240)
        self.table.set_column_width("Value", 110)
        prev.body.addWidget(self.table)
        outer.addWidget(prev, 1)

        # Status pill
        self.status = StatusPill("Ready to process. Select year, verify paths, click Scan.", "muted")
        outer.addWidget(self.status)

    def _pick_file(self, line_edit, filt):
        fp, _ = QFileDialog.getOpenFileName(self, "Select file", "", filt)
        if fp: line_edit.setText(fp)

    # ---- ported helpers ----
    def _tracker_path(self, year: int) -> Path:
        return NO3_TRACKER_DIR / f"Master Template {year}.xlsx"

    def _month_folder(self, year: int, d: datetime.date) -> Path:
        root = NO3_OUTPUT_BASE / f"SL79 {year}"
        root.mkdir(parents=True, exist_ok=True)
        m = root / f"{d.month}. {d.strftime('%B')} {year}"
        m.mkdir(parents=True, exist_ok=True)
        return m

    def _sanitize_filename(self, name: str) -> str:
        s = re.sub(r'[<>:"/\\|?*]', ' ', name).strip()
        s = re.sub(r'\s+', ' ', s)
        return s[:180]

    def _load_database(self, db_path: Path):
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")
        if db_path.suffix.lower() != ".xlsx":
            raise ValueError("Database must be .xlsx")
        wb = load_workbook(db_path)
        ws = wb["Sheet1"] if "Sheet1" in wb.sheetnames else wb.worksheets[0]
        out = []
        for r in range(2, ws.max_row + 1):
            line = ws[f"A{r}"].value
            b = ws[f"B{r}"].value
            customer = (ws[f"C{r}"].value or "")
            total = ws[f"E{r}"].value
            orig_bag = (ws[f"F{r}"].value or "")
            details = (ws[f"G{r}"].value or "")
            new_bag = (ws[f"H{r}"].value or "")

            customer = str(customer).strip()
            details = str(details).strip()
            try:
                val = float(total) if total not in (None, "") else 0.0
            except Exception:
                val = 0.0

            if isinstance(b, (datetime.datetime, datetime.date)):
                db_date = b.date() if isinstance(b, datetime.datetime) else b
            elif b is None or str(b).strip() == "":
                logging.warning(f"Row {r}: Column B (date) is empty - skipping")
                continue
            else:
                db_date = None
                b_str = str(b).strip()
                try:
                    db_date = datetime.datetime.fromordinal(
                        datetime.date(1899, 12, 30).toordinal() + int(float(b))).date()
                except Exception: pass
                if db_date is None:
                    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d-%m-%Y"):
                        try:
                            db_date = datetime.datetime.strptime(b_str, fmt).date(); break
                        except Exception: continue
                if db_date is None:
                    logging.error(f"Row {r}: Could not parse date '{b}' - skipping")
                    continue

            if customer and val > 0 and details:
                out.append({
                    "row": r, "line": str(line).strip() if line else "",
                    "date": db_date, "customer": customer,
                    "value": round(val, 2), "details": details,
                    "orig_bag": str(orig_bag).strip(), "new_bag": str(new_bag).strip(),
                })
        return out, wb, ws

    def _parse_denoms(self, text: str) -> dict:
        res = {k: 0.0 for k in ('500','200','100','50','20','10','5','coins')}
        if not text: return res
        s = text.strip().replace("’", "'").replace("€ ", "€")
        parts = re.split(r",\s*", s)
        for p in parts:
            m_coins = re.search(r"€\s*([\d\.,]+)\s+in\s+coins?", p, re.IGNORECASE)
            m_note  = re.search(r"€\s*([\d\.,]+)\s+in\s+(\d{1,3})'?s?", p, re.IGNORECASE)
            if m_coins:
                amt = float(m_coins.group(1).replace(",", "."))
                res["coins"] += round(amt, 2)
            elif m_note:
                amt = float(m_note.group(1).replace(",", "."))
                d = m_note.group(2)
                if d in res or d in ('500','200','100','50','20','10','5'):
                    res[d] += round(amt, 2)
        return res

    def _color_row(self, ws, row_idx: int, ok: bool):
        fill = PatternFill(start_color=("C6EFCE" if ok else "FFC7CE"),
                           end_color=("C6EFCE" if ok else "FFC7CE"),
                           fill_type="solid")
        for c in range(1, 12):
            ws.cell(row=row_idx, column=c).fill = fill

    def _update_tracker(self, tracker_path: Path, created_file: Path, slip_no: str, amount: float):
        from openpyxl import Workbook
        if tracker_path.exists():
            if tracker_path.suffix.lower() != ".xlsx":
                raise ValueError("Tracker must be .xlsx")
            wb = load_workbook(tracker_path)
        else:
            wb = Workbook()
        ws = wb["Sheet1"] if "Sheet1" in wb.sheetnames else wb.worksheets[0]
        r = 1
        while ws.cell(row=r, column=3).value not in (None, ""): r += 1
        today = datetime.date.today().strftime("%d.%m.%Y")
        ws.cell(row=r, column=3, value=today)
        dcell = ws.cell(row=r, column=4, value=slip_no)
        try:
            file_path = str(created_file.resolve())
            dcell.hyperlink = file_path
            dcell.style = "Hyperlink"
        except Exception as e:
            logging.warning(f"Hyperlink fail: {e}")
            dcell.value = f"{slip_no} -> {created_file}"
        ws.cell(row=r, column=5, value=float(f"{amount:.2f}"))
        ws.cell(row=r, column=6, value=None)
        ws.cell(row=r, column=7, value=created_file.stem)
        wb.save(tracker_path)

    def _create_file(self, template_xlsx: Path, out_dir: Path, tx: dict, slip: str, tracker_path: Path):
        try:
            if template_xlsx.suffix.lower() != ".xlsx":
                return None, "Template must be .xlsx"
            den = self._parse_denoms(tx["details"])
            total = round(sum(den.values()), 2)
            if total != round(tx["value"], 2):
                return None, f"Denomination sum (€{total:.2f}) != Total (€{tx['value']:.2f})"
            db_date_str = tx["date"].strftime("%d.%m.%Y")
            line_code = tx["line"] if tx["line"] else f"R{tx['row']:04d}"
            today = datetime.date.today().strftime("%d.%m.%Y")
            safe_cust = self._sanitize_filename(tx["customer"])
            fname = f"{slip} €{tx['value']:.2f} {safe_cust} {db_date_str} {line_code} {today}.xlsx"
            target = out_dir / fname
            if target.exists():
                if not msg_yes(self, "Exists", f"File exists:\n{target}\n\nOverwrite?"):
                    return None, "User aborted overwrite"

            wb = load_workbook(template_xlsx); ws = wb.worksheets[0]
            ws["F5"] = slip
            mapping = {"500":"E8","200":"E9","100":"E10","50":"E11","20":"E12","10":"E13","5":"E14"}
            for k, cell in mapping.items():
                v = den.get(k, 0.0)
                ws[cell] = float(f"{v:.2f}") if v else None
            ws["G16"] = float(f"{den.get('coins', 0.0):.2f}") if den.get('coins', 0.0) else None
            ws["D28"] = f"€{tx['value']:.2f} {tx['customer']} {line_code} {db_date_str}"
            ws["D32"] = tx["orig_bag"] or None
            ws["D34"] = today
            ws["D36"] = tx["new_bag"] or None
            wb.save(target)
            self._update_tracker(tracker_path, target, slip, tx["value"])
            return target, None
        except Exception as ex:
            logging.exception("Unhandled exception")
            return None, str(ex)

    def _show_slip_input(self, rows20):
        if not rows20: return {}
        dlg = QDialog(self)
        dlg.setWindowTitle("No. 3 Lodgments · Slip Numbers")
        dlg.resize(940, 540)
        outer = QVBoxLayout(dlg); outer.setContentsMargins(16, 16, 16, 16); outer.setSpacing(10)

        head = QLabel(f"{len(rows20)} transactions found. Enter Lodgment Slip Numbers.")
        head.setStyleSheet(f"color:{Theme.TXT}; font-size:14px; font-weight:600;")
        outer.addWidget(head)

        # Subtle hint so users know how Enter behaves with a barcode scanner.
        hint = QLabel(
            "Tip: pressing Enter (or scanning a barcode) moves to the next "
            "field. Click Create only when all slip numbers are filled in."
        )
        hint.setStyleSheet(f"color:{Theme.TXT_3}; font-size:11px;")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        # Header row
        hdr = QFrame(); hdr.setStyleSheet(f"background:{Theme.ELEVATED};")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(14, 8, 14, 8)
        for txt, w in [("Amount", 130), ("Customer", 420), ("Slip Number", 200)]:
            l = QLabel(txt); l.setObjectName("sectionLabel"); l.setMinimumWidth(w)
            hl.addWidget(l)
        hl.addStretch()
        outer.addWidget(hdr)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget(); bl = QVBoxLayout(body); bl.setSpacing(2); bl.setContentsMargins(0, 0, 0, 0)
        entries = {}
        entry_list = []  # ordered list so Enter can advance to the next one
        for tx in rows20:
            row = QFrame()
            row.setStyleSheet(f"background:{Theme.SURFACE}; border:1px solid {Theme.BORDER_S};")
            rl = QHBoxLayout(row); rl.setContentsMargins(14, 6, 14, 6)
            amt = QLabel(f"€{tx['value']:.2f}"); amt.setMinimumWidth(130)
            amt.setStyleSheet(f"color:{Theme.ACCENT}; font-weight:600; font-size:13px;")
            rl.addWidget(amt)
            cu = QLabel(tx['customer'][:60]); cu.setMinimumWidth(420); cu.setStyleSheet(f"color:{Theme.TXT};")
            rl.addWidget(cu)
            ent = QLineEdit(); ent.setMaximumWidth(200); ent.setAlignment(Qt.AlignCenter)
            rl.addWidget(ent); rl.addStretch()
            entries[tx["row"]] = ent
            entry_list.append(ent)
            bl.addWidget(row)
        bl.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # ----- Barcode-scanner / Enter handling -----
        # Barcode scanners type the code as keystrokes followed by Enter. In
        # a QDialog, Enter triggers the default QPushButton -> the dialog
        # would close as soon as the user scans a single slip. To prevent
        # this we (1) advance focus to the next field on returnPressed,
        # and (2) mark Create/Cancel as non-default so neither receives
        # the implicit Enter activation.
        def _make_advance(idx):
            def _advance():
                # Stop here if the cursor field is the last one — leave
                # focus where it is so scanning the final slip does not
                # trigger button activation either.
                if idx + 1 < len(entry_list):
                    entry_list[idx + 1].setFocus()
                    entry_list[idx + 1].selectAll()
            return _advance

        for i, ent in enumerate(entry_list):
            ent.returnPressed.connect(_make_advance(i))

        # Buttons
        result = {"ok": False, "vals": {}}
        bf = QHBoxLayout(); bf.addStretch()
        cb = QPushButton("Cancel"); cb.setMinimumWidth(120); cb.clicked.connect(dlg.reject); bf.addWidget(cb)
        ok = QPushButton("Create"); ok.setObjectName("success"); ok.setMinimumWidth(120)
        def _on_ok():
            slips = []; out = {}
            for r, ent in entries.items():
                v = ent.text().strip()
                if not v or not v.isdigit():
                    msg_err(dlg, "Invalid Slip", f"Row {r}: Slip number must be numeric and not empty.")
                    return
                slips.append(v); out[r] = v
            if len(slips) != len(set(slips)):
                msg_err(dlg, "Duplicate", "Duplicate slip numbers in current batch."); return
            result["ok"] = True; result["vals"] = out
            dlg.accept()
        ok.clicked.connect(_on_ok); bf.addWidget(ok)

        # Critical: prevent Enter (from scanner OR keyboard) from triggering
        # these buttons as the dialog default. The user must explicitly
        # click Create or Cancel.
        for btn in (cb, ok):
            btn.setAutoDefault(False)
            btn.setDefault(False)

        outer.addLayout(bf)

        # Focus the first slip-number field so scanning starts there.
        if entry_list:
            entry_list[0].setFocus()

        dlg.exec()
        return result["vals"] if result["ok"] else None

    def scan_and_create(self):
        try:
            self.status.set("Scanning database...", "warning"); QApplication.processEvents()
            year = int(self.year_combo.currentText())
            db_path = Path(self.db_path.text().strip())
            template_path = Path(self.tmpl_path.text().strip())
            tracker_path = self._tracker_path(year)

            rows, wb, ws = self._load_database(db_path)
            rows20 = rows[:20]
            self.table.clear()
            for tx in rows20:
                self.table.add_row({
                    "Row": tx["row"],
                    "Line": tx["line"] or f"R{tx['row']:04d}",
                    "Date": tx["date"].strftime("%d.%m.%Y"),
                    "Customer": tx["customer"],
                    "Value": f"{tx['value']:.2f}",
                    "Details": tx["details"][:120],
                })
            if not rows20:
                self.status.set("No valid transactions", "warning")
                self.info_lbls["Status"].setText("No transactions"); return

            slips = self._show_slip_input(rows20)
            if slips is None:
                self.status.set("Cancelled", "muted")
                self.info_lbls["Status"].setText("Cancelled"); return

            created, failed = [], []
            for tx in rows20:
                ridx = tx["row"]
                slip = slips.get(ridx, "")
                if not slip:
                    failed.append((tx, "Missing slip number"))
                    self._color_row(ws, ridx, False); continue
                out_dir = self._month_folder(year, tx["date"])
                created_path, err = self._create_file(template_path, out_dir, tx, slip, tracker_path)
                if created_path:
                    created.append(created_path)
                    self._color_row(ws, ridx, True)
                else:
                    failed.append((tx, err or "Unknown error"))
                    self._color_row(ws, ridx, False)

            try:
                wb.save(db_path)
            except Exception as ex:
                msg_warn(self, "Warning", f"Could not save colored database:\n{ex}")

            parts = []
            if created:
                parts.append("Created:\n" + "\n".join(str(p) for p in created))
            if failed:
                parts.append("\nFailed:\n" + "\n".join(
                    [f"Row {t[0]['row']} | {t[0]['customer']} | €{t[0]['value']:.2f} -> {t[1]}" for t in failed]))
            if not parts: parts = ["Nothing created."]
            msg_info(self, "No. 3 Summary", "\n\n".join(parts))

            self.info_lbls["Tracker"].setText(self._tracker_path(year).name)
            self.info_lbls["Status"].setText(f"{len(created)} created, {len(failed)} failed")
            self.status.set(f"✓ {len(created)} created, {len(failed)} failed", "success")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))
            self.status.set(f"Error: {e}", "danger")

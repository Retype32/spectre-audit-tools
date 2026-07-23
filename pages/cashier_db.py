"""
pages/cashier_db — CashierDbPage.
"""
import logging

import os

import pandas as pd

from PySide6.QtCore import (
    Qt, QTimer
)
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QInputDialog, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget
)

from config import DATABASE_FILE, DISCREPANCY_DB_PATH, SLIP_HISTORY_DB

from utils import msg_err, msg_info, msg_warn, msg_yes

from widgets import Card, DataTable, FieldLabel





class CashierDbPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        outer = QVBoxLayout(self); outer.setContentsMargins(20, 16, 20, 16); outer.setSpacing(14)

        # Add row
        add_card = Card("Add Cashier")
        ag = QHBoxLayout(); ag.setSpacing(12)
        ag.addWidget(FieldLabel("ID"))
        self.db_num = QLineEdit(); self.db_num.setPlaceholderText("Cashier ID"); self.db_num.setMaximumWidth(140)
        ag.addWidget(self.db_num)
        ag.addWidget(FieldLabel("Name"))
        self.db_name = QLineEdit(); self.db_name.setPlaceholderText("Cashier Name"); self.db_name.setMinimumWidth(280)
        ag.addWidget(self.db_name)
        addb = QPushButton("Add"); addb.setObjectName("success"); addb.setMinimumWidth(100)
        addb.clicked.connect(self.add_to_db); ag.addWidget(addb)
        ag.addStretch()
        add_card.body.addLayout(ag)
        outer.addWidget(add_card)

        # Bulk action row
        bulk_card = Card()
        bg = QHBoxLayout(); bg.setSpacing(8)
        ib = QPushButton("Import CSV"); ib.clicked.connect(self.import_cashiers_csv); bg.addWidget(ib)
        eb = QPushButton("Export CSV"); eb.clicked.connect(self.export_cashiers_csv); bg.addWidget(eb)
        bg.addStretch()
        for txt, fn in [("Delete Discrepancies", self.delete_all_discrepancies),
                        ("Delete Slip History", self.delete_all_slip_history),
                        ("Delete All Cashiers", self.delete_all_cashiers)]:
            b = QPushButton(txt); b.setObjectName("danger"); b.clicked.connect(fn); bg.addWidget(b)
        bulk_card.body.addLayout(bg)
        outer.addWidget(bulk_card)

        # Search + table
        list_card = Card("Cashiers", "double-click ID to copy")
        sl = QHBoxLayout()
        sl.addWidget(FieldLabel("Filter"))
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("type to filter by name or ID...")
        self.search_input.textChanged.connect(self._filter_changed)
        sl.addWidget(self.search_input)
        list_card.body.addLayout(sl)

        self.cashiers_table = DataTable(("ID", "Name", ""))
        self.cashiers_table.set_column_width("ID", 100)
        self.cashiers_table.set_column_width("Name", 320)
        self.cashiers_table.rowDoubleClicked.connect(self._row_action)
        # Default sort: Name A→Z
        self.cashiers_table.sortByColumn(1, Qt.AscendingOrder)
        list_card.body.addWidget(self.cashiers_table)
        outer.addWidget(list_card, 1)

        QTimer.singleShot(50, self.refresh_db_list)

    def _filter_changed(self, text):
        self.cashiers_table.set_filter(text)

    def _row_action(self, rd):
        # Show options: copy ID or delete
        n = rd.get("ID", "")
        name = rd.get("Name", "")
        choice = QMessageBox.question(self, "Action",
            f"{name}  ({n})\n\nDelete this entry?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if choice == QMessageBox.Yes:
            self.delete_from_db(n)

    def refresh_db_list(self):
        self.cashiers_table.clear()
        try:
            if not os.path.exists(DATABASE_FILE):
                pd.DataFrame(columns=["Number", "Name"]).to_csv(DATABASE_FILE, index=False)
            df = pd.read_csv(DATABASE_FILE, dtype=str)
            df['Number'] = df['Number'].fillna('').str.strip()
            df['Name']   = df['Name'].fillna('').str.strip()
            df = df[(df['Number'] != '') & (df['Name'] != '')].sort_values("Name")
            for _, row in df.iterrows():
                self.cashiers_table.add_row({"ID": row['Number'], "Name": row['Name'], "": ""})
        except Exception:
            logging.exception("Unhandled exception")

    def add_to_db(self):
        try:
            num = self.db_num.text().strip(); name = self.db_name.text().strip()
            if not num: msg_warn(self, "Missing", "Enter ID"); return
            if not name: msg_warn(self, "Missing", "Enter name"); return
            if num.endswith('.0'): num = num[:-2]
            try: num = str(int(float(num)))
            except Exception: pass

            if not os.path.exists(DATABASE_FILE):
                pd.DataFrame(columns=["Number", "Name"]).to_csv(DATABASE_FILE, index=False)
            df = pd.read_csv(DATABASE_FILE, dtype=str)
            df['Number'] = df['Number'].fillna('').str.strip()
            existing = set()
            for n in df['Number'].values:
                nn = n
                if nn.endswith('.0'): nn = nn[:-2]
                try: nn = str(int(float(nn)))
                except Exception: pass
                existing.add(nn)
            if num in existing:
                msg_warn(self, "Duplicate", f"ID '{num}' exists"); return

            df = pd.concat([df, pd.DataFrame([{"Number": num, "Name": name}])], ignore_index=True)
            df.to_csv(DATABASE_FILE, index=False)
            self.db_num.clear(); self.db_name.clear()
            self.refresh_db_list()
            msg_info(self, "Added", f"{name} ({num})")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

    def delete_from_db(self, num):
        if not msg_yes(self, "Confirm", f"Delete ID '{num}'?"): return
        try:
            df = pd.read_csv(DATABASE_FILE, dtype=str)
            df = df[df['Number'] != num]
            df.to_csv(DATABASE_FILE, index=False)
            self.refresh_db_list()
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

    def verify_password(self, action):
        pw, ok = QInputDialog.getText(self, "Password Required",
            f"Enter password to {action}:", QLineEdit.Password)
        if not ok: return False
        if pw == "7861": return True
        msg_err(self, "Denied", "Incorrect password"); return False

    def import_cashiers_csv(self):
        fp, _ = QFileDialog.getOpenFileName(self, "Select CSV", "", "CSV (*.csv);;All (*.*)")
        if not fp: return
        try:
            idf = pd.read_csv(fp, dtype=str)
            nc, nmc = None, None
            for col in idf.columns:
                cl = col.lower().strip()
                if cl in ('number', 'id', 'cashier id', 'operator id', 'num'): nc = col
                elif cl in ('name', 'cashier name', 'cashier', 'operator'): nmc = col
            if nc is None or nmc is None:
                msg_err(self, "Invalid",
                    f"Need ID and Name columns. Found: {', '.join(idf.columns.tolist())}"); return

            idf = idf[[nc, nmc]].copy()
            idf.columns = ['Number', 'Name']
            idf['Number'] = idf['Number'].fillna('').str.strip()
            idf['Name']   = idf['Name'].fillna('').str.strip()
            idf = idf[(idf['Number'] != '') & (idf['Name'] != '')]
            if idf.empty:
                msg_warn(self, "Empty", "No valid entries"); return

            if os.path.exists(DATABASE_FILE):
                edf = pd.read_csv(DATABASE_FILE, dtype=str)
                edf['Number'] = edf['Number'].fillna('').str.strip()
                new = idf[~idf['Number'].isin(set(edf['Number'].values))]
                if new.empty:
                    msg_info(self, "None", "All already exist"); return
                fdf = pd.concat([edf, new], ignore_index=True)
            else:
                fdf = idf; new = idf

            fdf.to_csv(DATABASE_FILE, index=False)
            self.refresh_db_list()
            msg_info(self, "Done", f"Imported {len(new)} new cashiers")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

    def export_cashiers_csv(self):
        if not os.path.exists(DATABASE_FILE):
            msg_warn(self, "No Data", "No database"); return
        try:
            fp, _ = QFileDialog.getSaveFileName(self, "Export", "Cashiers_Export.csv", "CSV (*.csv)")
            if not fp: return
            pd.read_csv(DATABASE_FILE, dtype=str).to_csv(fp, index=False)
            msg_info(self, "Done", f"Exported to:\n{fp}")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

    def delete_all_cashiers(self):
        if not self.verify_password("delete ALL cashiers"): return
        if not msg_yes(self, "Confirm", "DELETE ALL CASHIERS?"): return
        pd.DataFrame(columns=["Number", "Name"]).to_csv(DATABASE_FILE, index=False)
        self.refresh_db_list()
        msg_info(self, "Done", "Deleted")

    def delete_all_discrepancies(self):
        if not self.verify_password("delete ALL discrepancy data"): return
        if not msg_yes(self, "Confirm", "DELETE ALL DISCREPANCIES?"): return
        try:
            if os.path.exists(DISCREPANCY_DB_PATH):
                for root, dirs, files in os.walk(DISCREPANCY_DB_PATH, topdown=False):
                    for f in files: os.remove(os.path.join(root, f))
                    for d in dirs: os.rmdir(os.path.join(root, d))
                msg_info(self, "Done", "Deleted")
            else:
                msg_info(self, "None", "No data")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

    def delete_all_slip_history(self):
        if not self.verify_password("delete ALL slip history"): return
        if not msg_yes(self, "Confirm", "DELETE ALL SLIP HISTORY?"): return
        try:
            if os.path.exists(SLIP_HISTORY_DB):
                os.remove(SLIP_HISTORY_DB)
                hp = self.app.pages.get('history')
                if hp: hp.refresh_slip_dates()
                msg_info(self, "Done", "Deleted")
            else:
                msg_info(self, "None", "No history")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

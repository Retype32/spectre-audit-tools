"""
pages/search — SearchPage.
"""
import logging

from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget
)

from config import AMOUNT, WALLET

from utils import msg_err, msg_warn

from widgets import Card, DataTable, DetailDialog, FieldLabel





class SearchPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        outer = QVBoxLayout(self); outer.setContentsMargins(20, 16, 20, 16); outer.setSpacing(14)

        # Controls
        ctrl = Card()
        cl = QHBoxLayout(); cl.setSpacing(12)
        cl.addWidget(FieldLabel("Cashier"))
        self.cashier_combo = QComboBox(); self.cashier_combo.addItem("Import Data First")
        self.cashier_combo.setMinimumWidth(220)
        cl.addWidget(self.cashier_combo)
        cl.addSpacing(20)
        cl.addWidget(FieldLabel("Amount"))
        self.ent_amt = QLineEdit(); self.ent_amt.setPlaceholderText("€0.00"); self.ent_amt.setMaximumWidth(120)
        cl.addWidget(self.ent_amt)
        cl.addSpacing(20)
        cl.addWidget(FieldLabel("± Tolerance"))
        self.ent_tol = QLineEdit(); self.ent_tol.setText("0"); self.ent_tol.setMaximumWidth(80)
        cl.addWidget(self.ent_tol)
        cl.addSpacing(24)
        search_btn = QPushButton("Search"); search_btn.setObjectName("primary")
        search_btn.setMinimumHeight(34); search_btn.setMinimumWidth(120)
        search_btn.clicked.connect(self.run_search)
        cl.addWidget(search_btn)
        cl.addStretch()
        ctrl.body.addLayout(cl)
        outer.addWidget(ctrl)

        # 2x2 result grid
        grid = QGridLayout(); grid.setSpacing(10)
        self.exact_table  = self._make_table()
        self.tol_table    = self._make_table(diff_col=True)
        self.half_table   = self._make_table()
        self.double_table = self._make_table()

        configs = [
            (0, 0, "◎  Exact Matches", self.exact_table),
            (0, 1, "◧  Tolerance Range", self.tol_table),
            (1, 0, "÷  Halved Amount", self.half_table),
            (1, 1, "×  Doubled Amount", self.double_table),
        ]
        for r, c, t, tbl in configs:
            card = Card(t)
            card.body.addWidget(tbl)
            grid.addWidget(card, r, c)
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1); grid.setRowStretch(1, 1)
        outer.addLayout(grid, 1)

    def _make_table(self, diff_col=False):
        cols = ("Line", "Cashier", "Amount", "Diff" if diff_col else "Wallet")
        t = DataTable(cols)
        t.set_column_width("Line", 60)
        t.set_column_width("Cashier", 180)
        t.set_column_width("Amount", 110)
        t.rowDoubleClicked.connect(self._show_detail)
        return t

    def _show_detail(self, rd):
        DetailDialog.show_row(self.app,
            f"{rd.get('Cashier', rd.get('Cashier Name', 'Row'))}",
            rd)

    def refresh_cashier_list(self, names):
        self.cashier_combo.clear()
        self.cashier_combo.addItem("ALL")
        for n in names: self.cashier_combo.addItem(n)
        self.cashier_combo.setCurrentText("ALL")

    def run_search(self):
        if self.app.active_df is None:
            msg_warn(self, "No Data", "Import a report first."); return
        try:
            df = self.app.active_df.copy()
            sel = self.cashier_combo.currentText()
            if sel not in ("ALL", "Import Data First"):
                df = df[df['Cashier Name'] == sel]
            try:
                target = float(self.ent_amt.text().strip())
            except ValueError:
                msg_err(self, "Invalid", "Amount must be a number"); return
            try:
                tol = float(self.ent_tol.text().strip() or "0")
            except ValueError:
                msg_err(self, "Invalid", "Tolerance must be a number"); return
            if target <= 0:
                msg_warn(self, "Invalid", "Amount must be positive"); return

            for t in (self.exact_table, self.tol_table, self.half_table, self.double_table):
                t.clear()

            def _add(table, filt, has_diff):
                for idx, r in filt.iterrows():
                    cashier = str(r.get('Cashier Name', ''))[:22]
                    amt = f"€{float(r[AMOUNT]):,.2f}"
                    if has_diff:
                        last = f"{float(r[AMOUNT]) - target:+.2f}"
                        col_name = "Diff"
                    else:
                        last = str(r.get(WALLET, ''))[:14]
                        col_name = "Wallet"
                    table.add_row({"Line": idx + 2, "Cashier": cashier, "Amount": amt, col_name: last})

            _add(self.exact_table, df[df[AMOUNT] == target], False)
            if tol > 0:
                _add(self.tol_table,
                     df[(df[AMOUNT] >= target - tol) & (df[AMOUNT] <= target + tol) & (df[AMOUNT] != target)],
                     True)
            _add(self.half_table,   df[df[AMOUNT] == target / 2], False)
            _add(self.double_table, df[df[AMOUNT] == target * 2], False)
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

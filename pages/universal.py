"""
pages/universal — UniversalSearchPage.
"""
import logging

import os

import pandas as pd

try:
    import xlrd
except ImportError:
    xlrd = None

from PySide6.QtCore import (
    Qt
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget
)

from config import AMOUNT, LODGEMENT, OPERATOR, WALLET, XLRD_AVAILABLE

from theme import Theme

from utils import extract_report_date, load_db_map, msg_err, msg_info, msg_warn

from widgets import Card, DataTable, DetailDialog, FieldLabel, StatusPill





class UniversalSearchPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app

        # Internal state — independent of self.app.active_df so this page
        # doesn't fight with Integrity Check's loaded report.
        self.df = None              # the currently-loaded DataFrame
        self.source_path = None     # path of loaded file
        self.source_kind = None     # "VMS" or "ISA"
        self.report_date = None     # extracted display string

        outer = QVBoxLayout(self); outer.setContentsMargins(20, 16, 20, 16); outer.setSpacing(14)

        # ---- Top: Load + info ----
        load_card = Card("Source Report")
        lr = QHBoxLayout(); lr.setSpacing(12)
        load_btn = QPushButton("Load Report"); load_btn.setObjectName("primary")
        load_btn.setMinimumHeight(36); load_btn.setMinimumWidth(160)
        load_btn.clicked.connect(self.load_report)
        lr.addWidget(load_btn)

        self.info_lbl = QLabel("No file loaded")
        self.info_lbl.setStyleSheet(f"color:{Theme.TXT_2}; font-size:12px;")
        lr.addWidget(self.info_lbl, 1)
        load_card.body.addLayout(lr)
        outer.addWidget(load_card)

        # ---- Middle: search controls ----
        ctrl = Card("Search", "exact match — case-insensitive for text, numeric-aware for numbers")
        # Mode row
        mr = QHBoxLayout(); mr.setSpacing(20)
        mr.addWidget(FieldLabel("Mode"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["All Columns", "Specific Column"])
        self.mode_combo.setMinimumWidth(180)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        mr.addWidget(self.mode_combo)

        mr.addWidget(FieldLabel("Column"))
        self.col_combo = QComboBox()
        self.col_combo.addItem("(load a report first)")
        self.col_combo.setMinimumWidth(260)
        self.col_combo.setEnabled(False)
        mr.addWidget(self.col_combo)
        mr.addStretch()
        ctrl.body.addLayout(mr)

        # Query row
        qr = QHBoxLayout(); qr.setSpacing(12)
        qr.addWidget(FieldLabel("Query"))
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("e.g. 1234, ABC-9876, S100, €100.00 — exact match")
        self.query_input.returnPressed.connect(self.run_search)
        qr.addWidget(self.query_input, 1)

        sb = QPushButton("Search"); sb.setObjectName("primary")
        sb.setMinimumHeight(36); sb.setMinimumWidth(120)
        sb.clicked.connect(self.run_search)
        qr.addWidget(sb)

        cb = QPushButton("Clear")
        cb.setMinimumHeight(36); cb.setMinimumWidth(100)
        cb.clicked.connect(self.clear_results)
        qr.addWidget(cb)
        ctrl.body.addLayout(qr)
        outer.addWidget(ctrl)

        # ---- Results table ----
        # We use a deliberately-small set of columns for visibility and
        # stash the full row dict on each row so DetailDialog shows everything.
        rc = Card("Results", "double-click a row to inspect the full Excel line")
        self.table = DataTable(("Line", "Match", "Column", "Cashier / Operator", "Amount"))
        self.table.set_column_width("Line", 70)
        self.table.set_column_width("Match", 200)
        self.table.set_column_width("Column", 180)
        self.table.set_column_width("Cashier / Operator", 220)
        self.table.set_column_width("Amount", 120)
        self.table.rowDoubleClicked.connect(self._on_row_double)
        rc.body.addWidget(self.table)
        outer.addWidget(rc, 1)

        # Status pill at bottom
        self.status = StatusPill("Load a report to begin", "muted")
        outer.addWidget(self.status)

        # We keep a parallel list of full row dicts indexed by table row,
        # because the displayed columns are a summary view.
        self._result_records = []

    # ---------------------------------------------------------------- helpers
    def _mode_changed(self):
        self.col_combo.setEnabled(self.mode_combo.currentText() == "Specific Column"
                                  and self.df is not None)

    def clear_results(self):
        self.table.clear()
        self._result_records = []
        self.status.set("Cleared", "muted")

    def _populate_columns(self):
        """Fill the column dropdown from the FIRST cell of each column header.
        Per the user spec, the column header is the first cell of each column.
        """
        self.col_combo.clear()
        if self.df is None or self.df.empty:
            self.col_combo.addItem("(load a report first)")
            self.col_combo.setEnabled(False)
            return
        for c in self.df.columns:
            label = "" if c is None else str(c).strip()
            if not label:
                label = "(unnamed)"
            self.col_combo.addItem(label)
        self.col_combo.setEnabled(self.mode_combo.currentText() == "Specific Column")

    # -------------------------------------------------------------- load file
    def load_report(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Report File", "",
            "Excel/CSV files (*.xlsx *.xls *.csv);;All files (*.*)")
        if not path:
            return
        try:
            self.status.set("Loading...", "warning"); QApplication.processEvents()

            if path.lower().endswith('.csv'):
                raw_df = pd.read_csv(path, encoding='utf-8', low_memory=False)
            elif path.lower().endswith('.xls') and XLRD_AVAILABLE:
                raw_df = pd.read_excel(path, engine='xlrd')
            else:
                raw_df = pd.read_excel(path)

            if raw_df.empty:
                msg_err(self, "Error", "File is empty"); return

            # Same ISA-detection logic as Integrity Check, so this page can
            # search any report shape the rest of the app supports.
            is_isa = False
            df = None
            for i in range(min(15, len(raw_df))):
                rv = [str(x).strip() for x in raw_df.iloc[i].values]
                if any(ind in v for v in rv for ind in ("Container Seal", "Lodgement Number", "Seal")):
                    df = raw_df.iloc[i+1:].copy()
                    df.columns = raw_df.iloc[i].values
                    df = df.rename(columns={
                        "User": OPERATOR, "Seal": WALLET,
                        "Lodgement Number": LODGEMENT, "Counted": AMOUNT,
                    })
                    is_isa = True
                    break
            if df is None:
                df = raw_df.copy()

            # Reset index so the displayed "Line" matches Excel row numbers
            df = df.reset_index(drop=True)

            # Optional cashier-name lookup so search results can show real names
            if OPERATOR in df.columns:
                cmap = load_db_map()
                df['Cashier Name'] = (df[OPERATOR].astype(str).str.strip()
                                       .map(cmap)
                                       .fillna(df[OPERATOR].astype(str)))

            self.df = df
            self.source_path = path
            self.source_kind = "ISA" if is_isa else "VMS"
            self.report_date = extract_report_date(df)

            self._populate_columns()
            self.clear_results()

            self.info_lbl.setText(
                f"<b>{os.path.basename(path)}</b> "
                f"<span style='color:{Theme.TXT_3};'> · {self.source_kind} · "
                f"{len(df):,} rows · {len(df.columns)} cols · date {self.report_date}</span>"
            )
            self.info_lbl.setTextFormat(Qt.RichText)
            self.status.set(
                f"✓ Loaded {len(df):,} rows · {len(df.columns)} columns ({self.source_kind})",
                "success")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))
            self.status.set(f"Error: {e}", "danger")

    # --------------------------------------------------------------- matcher
    @staticmethod
    def _normalize(v):
        """Return a string form of a cell value, stripped, for comparison."""
        if v is None:
            return ""
        try:
            if pd.isna(v):
                return ""
        except (TypeError, ValueError):
            pass
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v).strip()

    @classmethod
    def _matches(cls, cell_value, query_str, query_num):
        """Exact match: case-insensitive string compare, with numeric-aware
        fallback so '100' matches 100, 100.0, '100.00', '€100.00', etc."""
        cell_str = cls._normalize(cell_value)
        if cell_str == "":
            return False

        # String exact match (case-insensitive)
        if cell_str.casefold() == query_str.casefold():
            return True

        # Numeric exact match — try to coerce the cell to a number and
        # compare to the query if the query is numeric. Tolerate common
        # number formatting like "€1,234.50", "1,234.5", " 100 ", etc.
        if query_num is not None:
            try:
                cleaned = (cell_str.replace("\u20ac", "")
                                   .replace("$", "")
                                   .replace("\u00a3", "")
                                   .replace(",", "")
                                   .replace(" ", ""))
                if cleaned == "":
                    return False
                cell_num = float(cleaned)
                # Use a tiny epsilon to absorb float rounding artefacts.
                return abs(cell_num - query_num) < 1e-9
            except (ValueError, TypeError):
                return False
        return False

    @staticmethod
    def _try_float(s):
        if s is None:
            return None
        s = str(s).strip()
        if s == "":
            return None
        cleaned = (s.replace("\u20ac", "")
                    .replace("$", "")
                    .replace("\u00a3", "")
                    .replace(",", "")
                    .replace(" ", ""))
        try:
            return float(cleaned)
        except ValueError:
            return None

    # -------------------------------------------------------------- search
    def run_search(self):
        if self.df is None or self.df.empty:
            msg_warn(self, "No Data", "Load a report first."); return
        query_str = self.query_input.text().strip()
        if query_str == "":
            msg_warn(self, "Missing", "Enter a search query."); return

        query_num = self._try_float(query_str)
        mode = self.mode_combo.currentText()

        if mode == "Specific Column":
            col_label = self.col_combo.currentText()
            if col_label in ("", "(load a report first)"):
                msg_warn(self, "Missing", "Pick a column."); return
            # Find the actual column object (handles unnamed/None header case)
            target_col = None
            for c in self.df.columns:
                lbl = "(unnamed)" if (c is None or str(c).strip() == "") else str(c).strip()
                if lbl == col_label:
                    target_col = c
                    break
            if target_col is None:
                msg_err(self, "Error", f"Column '{col_label}' not found."); return
            cols_to_search = [target_col]
        else:
            cols_to_search = list(self.df.columns)

        self.clear_results()
        self.status.set("Searching...", "warning"); QApplication.processEvents()

        # Walk rows. We deduplicate rows but keep track of the FIRST column
        # that matched so the result table can show users WHICH field hit.
        try:
            seen_rows = set()
            for ridx, row in self.df.iterrows():
                hit_col = None
                hit_val = None
                for col in cols_to_search:
                    if col not in row.index:
                        continue
                    if self._matches(row[col], query_str, query_num):
                        hit_col = col
                        hit_val = row[col]
                        break
                if hit_col is None:
                    continue
                if ridx in seen_rows:
                    continue
                seen_rows.add(ridx)

                # Build a full row dict for the DetailDialog (matches v1.6 shape)
                rd = {'_line': int(ridx) + 2}
                for c in row.index:
                    rd[c] = row[c]

                # Friendly summary fields for the visible table
                cashier = rd.get('Cashier Name') or rd.get(OPERATOR) or ""
                amount  = rd.get(AMOUNT, "")
                amount_disp = amount
                try:
                    amount_disp = f"€{float(amount):,.2f}"
                except (ValueError, TypeError):
                    pass

                # Display the matched value through the same normaliser so
                # the user sees what actually matched (e.g. integer not 1.0)
                match_disp = self._normalize(hit_val)
                # Cap very long match strings so the table stays readable
                if len(match_disp) > 60:
                    match_disp = match_disp[:57] + "…"

                self.table.add_row({
                    "Line": rd['_line'],
                    "Match": match_disp,
                    "Column": str(hit_col) if hit_col is not None else "",
                    "Cashier / Operator": str(cashier)[:40],
                    "Amount": amount_disp,
                })
                self._result_records.append(rd)

            n = len(self._result_records)
            scope = "all columns" if mode == "All Columns" else f"column '{cols_to_search[0]}'"
            self.status.set(f"✓ {n} match(es) in {scope}",
                            "success" if n else "warning")
            if n == 0:
                msg_info(self, "No Matches",
                    f"No rows matched '{query_str}' in {scope}.")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))
            self.status.set(f"Error: {e}", "danger")

    # ---------------------------------------------------------- row -> detail
    def _on_row_double(self, displayed):
        """Map the displayed summary row back to the full row dict."""
        try:
            line = int(displayed.get("Line"))
        except (TypeError, ValueError):
            return
        for rd in self._result_records:
            if rd.get('_line') == line:
                cashier = rd.get('Cashier Name') or rd.get(OPERATOR) or "Row"
                DetailDialog.show_row(self.app,
                    f"{cashier} · Line {line}",
                    rd)
                return

"""
pages/integrity — IntegrityPage + DuplicateReviewDialog.
"""

import datetime
import logging
import os

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSplitter, QVBoxLayout, QWidget,
)

from config import (ALL_DISC_DB, AMOUNT, COL_DISC, CUSTOMER_DISC_DB, CUSTOMER_ID,
                    CUSTOMER_LOC, DISCREPANCY_DB_PATH,
                    EXPECTED_TOTAL, LODGEMENT, OPERATOR, WALLET)

from verdicts import load_verdicts, save_verdict, verdict_key

from theme import Theme

from utils import extract_report_date, load_db_map, msg_err, msg_info, msg_warn

from widgets import Card, DataTable, DetailDialog, FilteredRowsDialog, StatCard


# =============================================================================
# DuplicateReviewDialog
# =============================================================================

class DuplicateReviewDialog(QDialog):
    """Modal dialog for reviewing each duplicate group and marking it as a
    confirmed true duplicate or a false positive."""

    def __init__(self, integrity_page, parent=None):
        super().__init__(parent)
        self.page = integrity_page
        self.setWindowTitle("Review Duplicate Transactions")
        self.setMinimumSize(720, 480)
        self.resize(780, 560)
        self._card_widgets = {}   # key → dict with UI refs
        self._build()
        self._populate()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # Header
        title = QLabel("Review Duplicate Transactions")
        title.setStyleSheet(
            f"color:{Theme.TXT};font-size:16px;font-weight:700;"
        )
        root.addWidget(title)

        info = QLabel(
            "Review each flagged duplicate group and mark it as a confirmed true duplicate "
            "or a false positive.  Only confirmed duplicates affect cashier performance scores."
        )
        info.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
        info.setWordWrap(True)
        root.addWidget(info)

        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};")
        root.addWidget(div)

        # Scroll area for group cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self._inner = QWidget()
        self._inner.setStyleSheet("background:transparent;")
        self._inner_lay = QVBoxLayout(self._inner)
        self._inner_lay.setContentsMargins(0, 0, 0, 0)
        self._inner_lay.setSpacing(8)
        scroll.setWidget(self._inner)
        root.addWidget(scroll, 1)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    def _populate(self):
        dup_rows  = getattr(self.page.app, "_exact_dup_rows", [])
        report_date = getattr(self.page.app, "_active_report_date", "unknown")
        verdicts  = load_verdicts()

        # Group rows by verdict key
        groups = {}   # key → {"cashier", "slip", "amount", "op_id", "count"}
        for rd in dup_rows:
            op_id  = str(rd.get(OPERATOR, "")).strip()
            slip   = str(rd.get(LODGEMENT, "")).strip()
            amount = rd.get(AMOUNT, 0)
            cashier = str(rd.get("Cashier Name", "")).strip()
            key = verdict_key(report_date, op_id, slip, amount)
            if key not in groups:
                groups[key] = {"cashier": cashier, "slip": slip,
                               "amount": amount, "op_id": op_id, "count": 0}
            groups[key]["count"] += 1

        if not groups:
            lbl = QLabel("No duplicate groups to review.")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:13px;padding:40px;")
            self._inner_lay.addWidget(lbl)
            return

        for key, g in groups.items():
            current = verdicts.get(key, "")
            card_w  = self._make_group_card(key, g, current)
            self._inner_lay.addWidget(card_w)
            self._card_widgets[key] = card_w

        self._inner_lay.addStretch()

    def _make_group_card(self, key, g, current_verdict):
        """Build one card widget for a duplicate group."""
        card = QFrame()
        card.setObjectName(f"dupcard_{key[:16]}")
        self._apply_card_style(card, current_verdict)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)

        # Top row: cashier + slip + amount + count
        top = QHBoxLayout()
        cashier_lbl = QLabel(g["cashier"])
        cashier_lbl.setStyleSheet(
            f"color:{Theme.TXT};font-size:13px;font-weight:600;"
        )
        slip_lbl = QLabel(
            f"Slip: {g['slip']}   ·   €{float(g['amount']):,.2f}   ·   "
            f"×{g['count']} rows"
        )
        slip_lbl.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;font-family:Consolas,monospace;")
        top.addWidget(cashier_lbl)
        top.addStretch()
        top.addWidget(slip_lbl)
        lay.addLayout(top)

        # Bottom row: verdict pill + action buttons
        bot = QHBoxLayout()
        bot.setSpacing(8)

        status_lbl = QLabel()
        status_lbl.setFixedWidth(130)
        self._update_status_lbl(status_lbl, current_verdict)

        confirm_btn = QPushButton("✓  Confirm True Duplicate")
        confirm_btn.setFixedHeight(28)
        clear_btn   = QPushButton("✗  Mark as False Positive")
        clear_btn.setFixedHeight(28)
        self._style_action_btns(confirm_btn, clear_btn, current_verdict)

        confirm_btn.clicked.connect(
            lambda _=False, k=key, c=g["cashier"],
            sl=status_lbl, cf=confirm_btn, cl=clear_btn, crd=card:
                self._set_verdict(k, c, "confirmed", sl, cf, cl, crd)
        )
        clear_btn.clicked.connect(
            lambda _=False, k=key, c=g["cashier"],
            sl=status_lbl, cf=confirm_btn, cl=clear_btn, crd=card:
                self._set_verdict(k, c, "cleared", sl, cf, cl, crd)
        )

        bot.addWidget(status_lbl)
        bot.addStretch()
        bot.addWidget(confirm_btn)
        bot.addWidget(clear_btn)
        lay.addLayout(bot)

        return card

    # ── card appearance helpers ───────────────────────────────────────────────

    @staticmethod
    def _apply_card_style(card, verdict):
        if verdict == "confirmed":
            bg, border = "#1e0a0a", Theme.DANGER
        elif verdict == "cleared":
            bg, border = "#0a1e0a", Theme.OK
        else:
            bg, border = Theme.ELEVATED, Theme.BORDER
        card.setStyleSheet(
            f"QFrame{{background:{bg};border:1px solid {border};border-radius:7px;}}"
        )

    @staticmethod
    def _update_status_lbl(lbl, verdict):
        if verdict == "confirmed":
            text  = "CONFIRMED  ✓"
            color = Theme.DANGER
        elif verdict == "cleared":
            text  = "FALSE POSITIVE  ✗"
            color = Theme.OK
        else:
            text  = "PENDING  ●"
            color = Theme.TXT_3
        lbl.setText(text)
        lbl.setStyleSheet(
            f"color:{color};font-size:10px;font-weight:700;letter-spacing:0.8px;"
        )

    @staticmethod
    def _style_action_btns(confirm_btn, clear_btn, verdict):
        active_conf = (verdict == "confirmed")
        active_clr  = (verdict == "cleared")
        confirm_btn.setStyleSheet(
            f"QPushButton{{background:{Theme.DANGER if active_conf else Theme.ELEVATED};"
            f"color:{'white' if active_conf else Theme.TXT_3};"
            f"border:1px solid {Theme.DANGER if active_conf else Theme.BORDER};"
            f"border-radius:4px;font-size:10px;font-weight:{'700' if active_conf else '400'};"
            f"padding:0 10px;}}"
            f"QPushButton:hover{{color:white;background:{Theme.DANGER};"
            f"border-color:{Theme.DANGER};}}"
        )
        clear_btn.setStyleSheet(
            f"QPushButton{{background:{Theme.OK if active_clr else Theme.ELEVATED};"
            f"color:{'white' if active_clr else Theme.TXT_3};"
            f"border:1px solid {Theme.OK if active_clr else Theme.BORDER};"
            f"border-radius:4px;font-size:10px;font-weight:{'700' if active_clr else '400'};"
            f"padding:0 10px;}}"
            f"QPushButton:hover{{color:white;background:{Theme.OK};"
            f"border-color:{Theme.OK};}}"
        )

    def _set_verdict(self, key, cashier, verdict, status_lbl,
                     confirm_btn, clear_btn, card):
        save_verdict(key, cashier, verdict)
        self._update_status_lbl(status_lbl, verdict)
        self._style_action_btns(confirm_btn, clear_btn, verdict)
        self._apply_card_style(card, verdict)
        # Refresh the parent dup_table so Status column updates live
        self.page._populate_dup_table()

    def closeEvent(self, e):
        self.page._populate_dup_table()
        super().closeEvent(e)


# =============================================================================
# IntegrityPage
# =============================================================================

class IntegrityPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16); outer.setSpacing(14)

        # Top action row: stats + import button
        top = QHBoxLayout(); top.setSpacing(10)

        self.stat_dups = StatCard("High Risk Duplicates", "0", Theme.DANGER, "⚠", clickable=True)
        self.stat_dups.clicked.connect(self._show_dups_panel)
        top.addWidget(self.stat_dups)

        self.stat_sus = StatCard("Suspicious Patterns", "0", Theme.WARN, "◎", clickable=True)
        self.stat_sus.clicked.connect(self._show_sus_panel)
        top.addWidget(self.stat_sus)

        self.stat_shared = StatCard("Shared Assets", "0", Theme.GOLD, "⚡", clickable=True)
        self.stat_shared.clicked.connect(self._show_shared_panel)
        top.addWidget(self.stat_shared)

        import_box = QVBoxLayout(); import_box.addStretch()
        import_btn = QPushButton("Import Report"); import_btn.setObjectName("primary")
        import_btn.setMinimumHeight(40); import_btn.setMinimumWidth(160)
        import_btn.clicked.connect(self.run_integrity_check)
        import_box.addWidget(import_btn); import_box.addStretch()
        top.addLayout(import_box)
        outer.addLayout(top)

        # Info card row
        info_card = Card()
        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(28); info_grid.setVerticalSpacing(4)
        self.info_labels = {}
        for col, (k, v) in enumerate([("File", "No file loaded"), ("Date", "—"),
                                      ("Rows", "0"), ("Cashiers", "0"), ("Value", "€0.00")]):
            lbl = QLabel(k); lbl.setObjectName("sectionLabel")
            val = QLabel(v); val.setStyleSheet(f"color:{Theme.TXT}; font-size:14px; font-weight:600;")
            info_grid.addWidget(lbl, 0, col)
            info_grid.addWidget(val, 1, col)
            self.info_labels[k] = val
        info_card.body.addLayout(info_grid)
        outer.addWidget(info_card)

        # Tables side by side
        tables_split = QSplitter(Qt.Horizontal)
        tables_split.setHandleWidth(8)
        tables_split.setChildrenCollapsible(False)

        # ── Duplicates card ───────────────────────────────────────────
        dup_card = Card("⚠  High Risk: Identical Duplicates", "click row to inspect")

        # "Review Duplicates" button (hidden until a report is loaded)
        rev_row = QHBoxLayout(); rev_row.setSpacing(8)
        self._review_btn = QPushButton("⚖  Review Duplicates")
        self._review_btn.setObjectName("primary")
        self._review_btn.setFixedHeight(30)
        self._review_btn.setMinimumWidth(160)
        self._review_btn.setVisible(False)
        self._review_btn.clicked.connect(self._open_review_dialog)
        rev_row.addWidget(self._review_btn); rev_row.addStretch()
        dup_card.body.addLayout(rev_row)

        self.dup_table = DataTable(("Line", "Cashier", "Amount", "Slip", "Status"))
        self.dup_table.set_column_width("Line",   60)
        self.dup_table.set_column_width("Cashier",180)
        self.dup_table.set_column_width("Amount", 100)
        self.dup_table.set_column_width("Slip",   120)
        self.dup_table.set_column_width("Status",  90)
        self.dup_table.rowDoubleClicked.connect(self._show_detail)
        dup_card.body.addWidget(self.dup_table)
        tables_split.addWidget(dup_card)

        sus_card = Card("◎  Suspicious: Repeated Amounts", "click row to inspect")
        self.sus_table = DataTable(("Line", "Cashier", "Amount", "Slip"))
        self.sus_table.set_column_width("Line", 60)
        self.sus_table.set_column_width("Cashier", 200)
        self.sus_table.set_column_width("Amount", 110)
        self.sus_table.rowDoubleClicked.connect(self._show_detail)
        sus_card.body.addWidget(self.sus_table)
        tables_split.addWidget(sus_card)

        outer.addWidget(tables_split, 1)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _row_dict(self, idx, row):
        d = {'_line': idx + 2}
        for col in row.index: d[col] = row[col]
        return d

    def _show_detail(self, rd):
        DetailDialog.show_row(self.app,
            f"{rd.get('Cashier Name', 'Unknown')} · Line {rd.get('_line', '?')}",
            rd)

    def _show_dups_panel(self):
        if not self.app._exact_dup_rows:
            msg_info(self, "No Data", "No high-risk duplicates. Import a report first."); return
        FilteredRowsDialog(self, "High Risk: All Identical Duplicates",
                           rows=self.app._exact_dup_rows).exec()

    def _show_sus_panel(self):
        if not self.app._sus_rows:
            msg_info(self, "No Data", "No suspicious patterns. Import a report first."); return
        FilteredRowsDialog(self, "Suspicious: All Repeated-Amount Entries",
                           rows=self.app._sus_rows).exec()

    def _show_shared_panel(self):
        if not self.app._shared_wallet_rows:
            msg_info(self, "No Data", "No shared assets. Import a report first."); return
        FilteredRowsDialog(self, "Shared Assets: Wallets Used by Multiple Operators",
                           rows=self.app._shared_wallet_rows).exec()

    # ── verdict helpers ───────────────────────────────────────────────────────

    def _rd_verdict_key(self, rd):
        report_date = getattr(self.app, "_active_report_date", "unknown")
        op_id  = str(rd.get(OPERATOR, "")).strip()
        slip   = str(rd.get(LODGEMENT, "")).strip()
        amount = rd.get(AMOUNT, 0)
        return verdict_key(report_date, op_id, slip, amount)

    def _open_review_dialog(self):
        dlg = DuplicateReviewDialog(self, self)
        dlg.exec()

    def _populate_dup_table(self):
        """Rebuild the dup_table from app._exact_dup_rows with current verdicts."""
        self.dup_table.clear()
        dup_rows = getattr(self.app, "_exact_dup_rows", [])
        verdicts = load_verdicts()

        for rd in dup_rows:
            key = self._rd_verdict_key(rd)
            v   = verdicts.get(key, "")
            if v == "confirmed":
                status = "CONFIRMED ✓"
                row_color = "#2a0a0a"
            elif v == "cleared":
                status = "CLEARED ✗"
                row_color = "#0a2a0a"
            else:
                status    = "PENDING"
                row_color = None

            meta = {}
            if row_color:
                meta["bg"] = row_color

            self.dup_table.add_row({
                "Line":   rd.get("_line", ""),
                "Cashier": str(rd.get("Cashier Name", ""))[:22],
                "Amount": f"€{float(rd.get(AMOUNT, 0)):,.2f}",
                "Slip":   str(rd.get(LODGEMENT, ""))[:18],
                "Status": status,
            }, meta=meta)

        has_dups = bool(dup_rows)
        self._review_btn.setVisible(has_dups)

        # Rewire double-click to use stored row dicts
        try: self.dup_table.rowDoubleClicked.disconnect()
        except Exception: pass

        def _on_dbl(displayed_row):
            line = displayed_row.get("Line")
            for rd in dup_rows:
                if rd.get('_line') == line:
                    self._show_detail(rd); return
        self.dup_table.rowDoubleClicked.connect(_on_dbl)

    # ── archiving ─────────────────────────────────────────────────────────────

    def archive_customer_discrepancies(self, df, report_date):
        if COL_DISC not in df.columns or CUSTOMER_ID not in df.columns:
            return
        try:
            df2 = df.copy()
            df2[COL_DISC] = pd.to_numeric(df2[COL_DISC], errors='coerce').fillna(0)
            df2[AMOUNT]   = pd.to_numeric(df2[AMOUNT],   errors='coerce').fillna(0)
            rows = []
            for cid, grp in df2.groupby(CUSTOMER_ID):
                loc = ''
                if CUSTOMER_LOC in grp.columns:
                    loc_series = grp[CUSTOMER_LOC].dropna().astype(str)
                    loc = loc_series.mode().iloc[0] if not loc_series.empty else ''
                small    = grp[(grp[COL_DISC].abs() > 0) & (grp[COL_DISC].abs() <= 10)]
                all_disc = grp[grp[COL_DISC].abs() > 0]
                not_decl = grp[(grp[AMOUNT] > 0) &
                               ((grp[COL_DISC].abs() - grp[AMOUNT].abs()).abs() < 0.01)]
                rows.append({
                    'Customer_Id':         str(cid),
                    'Customer_Location':   loc,
                    'Report_Date':         str(report_date),
                    'Total_Transactions':  len(grp),
                    'All_Discrepancies':   len(all_disc),
                    'Small_Disc_Count':    len(small),
                    'Small_Disc_Amount':   round(float(small[COL_DISC].abs().sum()), 2),
                    'Not_Declaring_Count': len(not_decl),
                })
            if not rows:
                return
            new_df = pd.DataFrame(rows).astype(str)
            if os.path.exists(CUSTOMER_DISC_DB):
                try:
                    existing = pd.read_csv(CUSTOMER_DISC_DB, dtype=str)
                    existing = existing[existing['Report_Date'] != str(report_date)]
                    combined = pd.concat([existing, new_df], ignore_index=True)
                except Exception:
                    combined = new_df
            else:
                combined = new_df
            combined.to_csv(CUSTOMER_DISC_DB, index=False)
        except Exception as e:
            logging.error(f"Customer disc archive error: {e}")

    def archive_discrepancies(self, df, report_date):
        if COL_DISC not in df.columns: return
        try:
            df = df.copy()
            df[COL_DISC] = pd.to_numeric(df[COL_DISC], errors='coerce').fillna(0)
            disc = df[(df[COL_DISC].abs() > 0) & (df[COL_DISC].abs() <= 10)].copy()
            if disc.empty: return
            try: pd_date = datetime.datetime.strptime(report_date, "%d.%m.%Y")
            except Exception: pd_date = datetime.datetime.now()
            folder = os.path.join(DISCREPANCY_DB_PATH, pd_date.strftime("%Y"), pd_date.strftime("%m"))
            os.makedirs(folder, exist_ok=True)
            fp = os.path.join(folder, f"{report_date.replace('/', '.')}.xlsx")
            sm = disc.groupby(['Cashier Name', OPERATOR]).size().reset_index(name='Small_Discrepancies')
            sm['Report_Date'] = report_date
            sm.to_excel(fp, index=False)
        except Exception as e:
            logging.error(f"Archive error: {e}")

    def archive_all_discrepancies(self, df, report_date):
        """Append every non-zero Discrepancy row from this report to ALL_DISC_DB.
        Rows for the same report_date are replaced (idempotent re-run)."""
        if COL_DISC not in df.columns:
            return
        try:
            disc_df = df.copy()
            disc_df[COL_DISC] = pd.to_numeric(disc_df[COL_DISC], errors='coerce').fillna(0)
            disc_df = disc_df[disc_df[COL_DISC] != 0].copy()
            if disc_df.empty:
                return

            exp_col = EXPECTED_TOTAL if EXPECTED_TOTAL in disc_df.columns else None

            def _clean_id(v):
                """Convert float IDs like 66856507.0 → '66856507'."""
                try:
                    f = float(v)
                    return str(int(f)) if not pd.isna(f) else str(v)
                except (ValueError, TypeError):
                    return str(v)

            rows = []
            for _, row in disc_df.iterrows():
                exp_val = pd.to_numeric(row.get(exp_col, 0), errors='coerce') if exp_col else 0
                exp_val = 0.0 if pd.isna(exp_val) else round(float(exp_val), 2)
                disc_type = "Blind Count" if exp_val == 0 else "Discrepancy"
                rows.append({
                    "Report Date":      str(report_date),
                    "Customer ID":      _clean_id(row.get(CUSTOMER_ID, "")),
                    "Customer Location":str(row.get(CUSTOMER_LOC, "")),
                    "Expected Total":   exp_val,
                    "Total Processed":  round(float(pd.to_numeric(row.get(AMOUNT, 0), errors='coerce') or 0), 2),
                    "Discrepancy":      round(float(row[COL_DISC]), 2),
                    "Operator ID":      _clean_id(row.get(OPERATOR, "")),
                    "Cashier Name":     str(row.get("Cashier Name", "")),
                    "Type":             disc_type,
                })

            new_df = pd.DataFrame(rows)
            if os.path.exists(ALL_DISC_DB):
                try:
                    existing = pd.read_csv(ALL_DISC_DB, dtype=str)
                    existing = existing[existing["Report Date"] != str(report_date)]
                    combined = pd.concat([existing, new_df], ignore_index=True)
                except Exception:
                    combined = new_df
            else:
                combined = new_df
            combined.to_csv(ALL_DISC_DB, index=False)
            logging.info(f"All-discrepancies archive: {len(rows)} rows for {report_date}")
        except Exception as e:
            logging.error(f"All-disc archive error: {e}")

    # ── main analysis ─────────────────────────────────────────────────────────

    def _save_performance_history(self, df, report_date):
        """
        Save per-cashier slip counts and total values for this report date
        into SLIP_HISTORY_DB.  Existing rows for the same date are replaced
        (idempotent: re-running the same report doesn't double-count).
        Date is extracted from Column A / Column B of the loaded dataframe.
        """
        try:
            from config import PERFORMANCE_HISTORY_DB, AMOUNT, OPERATOR

            if "Cashier Name" not in df.columns:
                return

            row_date = report_date  # already extracted at load time

            rows = []
            for name, grp in df.groupby("Cashier Name"):
                txn_count = len(grp)
                total_val = float(grp[AMOUNT].sum()) if AMOUNT in df.columns else 0.0
                op_id = ""
                if OPERATOR in grp.columns:
                    op = grp[OPERATOR].mode()
                    op_id = str(op.iloc[0]).strip() if not op.empty else ""
                rows.append({
                    "Date":         row_date,
                    "Name":         str(name),
                    "Operator_Id":  op_id,
                    "System Count": txn_count,
                    "Total Value":  round(total_val, 2),
                })

            if not rows:
                return

            new_df = pd.DataFrame(rows)

            if os.path.exists(PERFORMANCE_HISTORY_DB):
                try:
                    existing = pd.read_csv(PERFORMANCE_HISTORY_DB, dtype=str)
                    existing = existing[existing["Date"] != str(row_date)]
                    combined = pd.concat([existing, new_df.astype(str)], ignore_index=True)
                except Exception:
                    combined = new_df.astype(str)
            else:
                combined = new_df.astype(str)

            os.makedirs(os.path.dirname(PERFORMANCE_HISTORY_DB), exist_ok=True)
            combined.to_csv(PERFORMANCE_HISTORY_DB, index=False)
            logging.info(f"Performance history saved: {len(rows)} cashiers for {row_date}")

        except Exception:
            logging.exception("Unhandled exception")

    def run_integrity_check(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Report File", "",
            "Excel/CSV files (*.xlsx *.xls *.csv);;All files (*.*)")
        if not path: return
        try:
            self.app.top_status.set("Loading...", "warning")
            QApplication.processEvents()
            self.app._exact_dup_rows = []; self.app._sus_rows = []
            self.app._shared_wallet_rows = []
            self.sus_table.clear()

            raw_df = (pd.read_csv(path, encoding='utf-8', low_memory=False)
                      if path.lower().endswith('.csv') else pd.read_excel(path))
            if raw_df.empty:
                msg_err(self, "Error", "File is empty"); return

            is_isa = False; df = None
            for i in range(min(15, len(raw_df))):
                rv = [str(x).strip() for x in raw_df.iloc[i].values]
                if any(v in {"Container Seal", "Lodgement Number", "Seal"} for v in rv):
                    df = raw_df.iloc[i+1:].copy(); df.columns = raw_df.iloc[i].values
                    df = df.rename(columns={"User": OPERATOR, "Seal": WALLET,
                                            "Lodgement Number": LODGEMENT, "Counted": AMOUNT})
                    is_isa = True; break
            if df is None: df = raw_df.copy()

            if OPERATOR not in df.columns:
                msg_err(self, "Missing Column", f"'{OPERATOR}' not found"); return
            if AMOUNT not in df.columns:
                msg_err(self, "Missing Column", f"'{AMOUNT}' not found"); return

            report_date = extract_report_date(df)
            self.app._active_report_date = report_date   # used by verdict keys

            df = df.dropna(subset=[OPERATOR, AMOUNT])
            df[AMOUNT] = pd.to_numeric(df[AMOUNT], errors='coerce')
            df = df.dropna(subset=[AMOUNT]); df[AMOUNT] = df[AMOUNT].round(2)
            df = df[df[AMOUNT] >= 1.0]
            if df.empty:
                msg_warn(self, "No Data", "No valid data"); return

            denoms = [c for c in df.columns
                      if any(x in str(c).lower() for x in ['100','50','20','10','5','2','1','0.5','0.2'])]
            for col in denoms:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            df[OPERATOR] = df[OPERATOR].astype(str).str.strip()
            if WALLET in df.columns:
                df[WALLET] = df[WALLET].astype(str).str.strip().replace(['nan','None',''], '[EMPTY]')
            else:
                df[WALLET] = '[EMPTY]'
            df[LODGEMENT] = df[LODGEMENT].astype(str).str.strip() if LODGEMENT in df.columns else '[N/A]'

            cmap = load_db_map()
            df['Cashier Name'] = df[OPERATOR].map(cmap).fillna(df[OPERATOR])
            self.app.active_df = df.copy()
            self.app._active_report_path = os.path.basename(path)

            hr_keys = [k for k in [OPERATOR, WALLET, LODGEMENT, AMOUNT] + denoms if k in df.columns]
            exact   = df[df.duplicated(subset=hr_keys, keep=False)].copy()
            sus_keys = [OPERATOR, WALLET, AMOUNT]
            all_pot  = df[df.duplicated(subset=sus_keys, keep=False)].copy()
            sus      = all_pot[~all_pot.index.isin(exact.index)].copy()

            npd = len(exact) // 2 if len(exact) else 0
            nsp = len(sus)   // 2 if len(sus)   else 0
            self.stat_dups.set_value(npd)
            self.stat_sus.set_value(nsp)

            sw_count = 0
            if WALLET in df.columns:
                wc = df[df[WALLET] != '[EMPTY]'].groupby(WALLET)[OPERATOR].nunique()
                sw = wc[wc > 1]; sw_count = len(sw)
                self.stat_shared.set_value(sw_count)
                if sw_count:
                    self.app._shared_wallet_rows = [self._row_dict(i, r)
                        for i, r in df[df[WALLET].isin(sw.index)].iterrows()]

            rt = "ISA" if is_isa else "VMS"
            self.info_labels["File"].setText(f"{os.path.basename(path)} ({rt})")
            self.info_labels["Date"].setText(report_date)
            self.info_labels["Rows"].setText(f"{len(df):,}")
            self.info_labels["Cashiers"].setText(str(df['Cashier Name'].nunique()))
            self.info_labels["Value"].setText(f"€{df[AMOUNT].sum():,.2f}")

            # Collect exact duplicate rows
            if not exact.empty:
                for _, grp in exact.groupby(hr_keys, dropna=False):
                    if len(grp) < 2: continue
                    for idx, r in grp.iterrows():
                        self.app._exact_dup_rows.append(self._row_dict(idx, r))

            # Populate dup_table (with verdicts)
            self._populate_dup_table()

            # Collect suspicious rows
            if not sus.empty:
                for _, grp in sus.groupby(sus_keys, dropna=False):
                    if len(grp) < 2: continue
                    for idx, r in grp.iterrows():
                        rd = self._row_dict(idx, r)
                        self.app._sus_rows.append(rd)
                        self.sus_table.add_row({
                            "Line":    idx + 2,
                            "Cashier": str(r['Cashier Name'])[:22],
                            "Amount":  f"€{float(r[AMOUNT]):,.2f}",
                            "Slip":    str(r[LODGEMENT])[:15],
                        })

            # Wire sus table double-click
            sus_rows = self.app._sus_rows
            try: self.sus_table.rowDoubleClicked.disconnect()
            except Exception: pass
            def _on_sus_dbl(displayed_row):
                line = displayed_row.get("Line")
                for rd in sus_rows:
                    if rd.get('_line') == line:
                        self._show_detail(rd); return
            self.sus_table.rowDoubleClicked.connect(_on_sus_dbl)

            self.archive_discrepancies(df, report_date)
            self.archive_customer_discrepancies(df, report_date)
            self.archive_all_discrepancies(df, report_date)
            self._save_performance_history(df, report_date)

            search_page = self.app.pages.get('search')
            if search_page:
                cn = sorted(df['Cashier Name'].unique().tolist())
                search_page.refresh_cashier_list(cn)

            self.app.top_status.set(
                f"✓ {len(df):,} transactions | HR {npd} | Sus {nsp} | Shared {sw_count}", "success")
            msg_info(self, "Scan Complete",
                     f"Date: {report_date}\nRows: {len(df):,}\n\n"
                     f"High Risk: {npd}\nSuspicious: {nsp}\nShared: {sw_count}\n\n"
                     f"Click stat cards or rows to drill down.\n"
                     + (f"\nUse  ⚖ Review Duplicates  to judge each duplicate." if npd else ""))
        except Exception as e:
            logging.exception("Unhandled exception")
            msg_err(self, "Error", str(e))
            self.app.top_status.set(f"Error: {e}", "danger")

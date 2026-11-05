"""
pages/integrity — IntegrityPage + DuplicateReviewDialog.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSplitter, QVBoxLayout, QWidget,
)

from config import AMOUNT, LODGEMENT, OPERATOR

from engine import ReportError, archive_report, load_report, run_integrity_checks, summarise

from verdicts import load_verdicts, save_verdict, verdict_key

from theme import Theme

from utils import msg_err, msg_info, msg_warn

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

            try:
                report = load_report(path)
            except ReportError as e:
                if e.report_date:
                    # Kept from the original flow: the date updates even
                    # though the report had no usable rows.
                    self.app._active_report_date = e.report_date
                (msg_warn if e.level == "warning" else msg_err)(self, e.title, e.message)
                return

            df, report_date = report.df, report.report_date
            self.app._active_report_date = report_date   # used by verdict keys
            self.app._active_report_fmt = report.fmt      # "VMS" or "ISA"
            self.app.active_df = df.copy()
            self.app._active_report_path = report.filename

            result = run_integrity_checks(df, report.denom_cols)
            self.app._exact_dup_rows     = result.exact_rows
            self.app._sus_rows           = result.suspicious_rows
            self.app._shared_wallet_rows = result.shared_wallet_rows
            npd, nsp, sw_count = (result.high_risk_count, result.suspicious_count,
                                  result.shared_wallet_count)
            self.stat_dups.set_value(npd)
            self.stat_sus.set_value(nsp)
            self.stat_shared.set_value(sw_count)

            info = summarise(report)
            self.info_labels["File"].setText(f"{info['file']} ({info['format']})")
            self.info_labels["Date"].setText(info["date"])
            self.info_labels["Rows"].setText(f"{info['rows']:,}")
            self.info_labels["Cashiers"].setText(str(info["cashiers"]))
            self.info_labels["Value"].setText(f"€{info['total_value']:,.2f}")

            # Populate dup_table (with verdicts)
            self._populate_dup_table()

            # Suspicious rows table
            sus_rows = self.app._sus_rows
            for rd in sus_rows:
                self.sus_table.add_row({
                    "Line":    rd["_line"],
                    "Cashier": str(rd['Cashier Name'])[:22],
                    "Amount":  f"€{float(rd[AMOUNT]):,.2f}",
                    "Slip":    str(rd[LODGEMENT])[:15],
                })

            # Wire sus table double-click
            try: self.sus_table.rowDoubleClicked.disconnect()
            except Exception: pass
            def _on_sus_dbl(displayed_row):
                line = displayed_row.get("Line")
                for rd in sus_rows:
                    if rd.get('_line') == line:
                        self._show_detail(rd); return
            self.sus_table.rowDoubleClicked.connect(_on_sus_dbl)

            archive_report(df, report_date, fmt=report.fmt)

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

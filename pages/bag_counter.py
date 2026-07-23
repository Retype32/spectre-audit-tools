"""
pages/bag_counter — BagCounterPage.
"""
import datetime
import logging
import os

import pandas as pd

try:
    import xlrd
except ImportError:
    xlrd = None

from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
)

from config import XLRD_AVAILABLE

from theme import Theme

from utils import extract_report_date, msg_err

from widgets import Card, FieldLabel, StatCard





class BagCounterPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        outer = QVBoxLayout(self); outer.setContentsMargins(20, 16, 20, 16); outer.setSpacing(14)

        # Mode + load
        ctrl = Card()
        cl = QHBoxLayout(); cl.setSpacing(20)
        cl.addWidget(FieldLabel("Mode"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "VMS", "ESNF", "Pivotal", "BC", "BDS", "Tesco",
            "BOI Direct", "AIB Direct",
        ])
        self.mode_combo.setMinimumWidth(200)
        cl.addWidget(self.mode_combo)
        cl.addStretch()
        load_btn = QPushButton("Load Report"); load_btn.setObjectName("primary")
        load_btn.setMinimumHeight(36); load_btn.setMinimumWidth(140)
        load_btn.clicked.connect(self.run_bag_count); cl.addWidget(load_btn)
        ctrl.body.addLayout(cl)
        outer.addWidget(ctrl)

        # 4 stat tiles
        stats_row = QHBoxLayout(); stats_row.setSpacing(10)
        self.unique_card = StatCard("Unique Bags", "0", Theme.ACCENT)
        self.slips_card  = StatCard("Total Slips", "0", Theme.OK)
        self.coins_card  = StatCard("Total Coins", "€0.00", Theme.GOLD)
        self.total_card  = StatCard("Total Amount", "€0.00", Theme.TXT)
        for w in (self.unique_card, self.slips_card, self.coins_card, self.total_card):
            stats_row.addWidget(w)
        outer.addLayout(stats_row)

        # Info card
        info = Card("Report Info")
        ig = QGridLayout(); ig.setHorizontalSpacing(28)
        self.info_lbls = {}
        for col, (k, v) in enumerate([("File", "No file loaded"), ("Date", "—"), ("Mode", "—")]):
            lbl = QLabel(k); lbl.setObjectName("sectionLabel")
            val = QLabel(v); val.setStyleSheet(f"color:{Theme.TXT}; font-size:13px;")
            ig.addWidget(lbl, 0, col); ig.addWidget(val, 1, col)
            self.info_lbls[k] = val
        info.body.addLayout(ig)
        outer.addWidget(info)
        outer.addStretch(1)

    def run_bag_count(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Report", "",
            "Excel/CSV (*.xlsx *.xls *.csv);;All (*.*)")
        if not path: return
        try:
            mode = self.mode_combo.currentText()
            # AIB Direct and BOI Direct report the amount in column Y (index 24)
            direct_mode = mode in ("AIB Direct", "BOI Direct")

            self.app.top_status.set("Loading...", "warning"); QApplication.processEvents()

            if path.lower().endswith('.csv'):
                rdf = pd.read_csv(path, encoding='utf-8', low_memory=False)
            elif path.lower().endswith('.xls') and XLRD_AVAILABLE:
                rdf = pd.read_excel(path, engine='xlrd')
            else:
                rdf = pd.read_excel(path)
            if rdf.empty:
                msg_err(self, "Error", "Empty"); return

            df = rdf.copy(); hr = None
            for i in range(min(15, len(rdf))):
                rv = [str(x).strip().lower() for x in rdf.iloc[i].values]
                if any('seal' in v or 'wallet' in v or 'operator' in v for v in rv):
                    hr = i; df = rdf.iloc[i+1:].copy(); df.columns = rdf.iloc[i].values; break
            rd = extract_report_date(df) if hr is not None else datetime.datetime.now().strftime("%d.%m.%Y")

            seal_col = None
            if hr is not None:
                for col in df.columns:
                    if 'seal' in str(col).lower() or 'wallet' in str(col).lower():
                        seal_col = col; break
                if seal_col is None and len(df.columns) > 7:
                    seal_col = df.columns[7]
            elif len(rdf.columns) > 7:
                seal_col = rdf.columns[7]

            ts, ub = 0, 0
            if seal_col and seal_col in df.columns:
                sd = df[seal_col].dropna()
                sd = sd[sd.astype(str).str.strip() != '']
                sd = sd[sd.astype(str).str.lower() != 'nan']
                ts = len(sd); ub = sd.nunique()

            def _last(src, ci):
                if len(src.columns) <= ci: return 0
                d = src[src.columns[ci]].dropna() if hr is not None else src.iloc[:, ci].dropna()
                for v in reversed(d.values):
                    try:
                        f = float(v)
                        if f != 0: return f
                    except Exception: continue
                return 0

            src = df if hr is not None else rdf
            coins = _last(src, 21)
            # AIB Direct / BOI Direct: amount is in column Y (index 24)
            amount_col = 24 if direct_mode else 23
            total = _last(src, amount_col)

            self.unique_card.set_value(str(ub))
            self.slips_card.set_value(str(ts))
            self.coins_card.set_value(f"€{coins:,.2f}")
            self.total_card.set_value(f"€{total:,.2f}")

            self.info_lbls["File"].setText(os.path.basename(path))
            self.info_lbls["Date"].setText(rd)
            self.info_lbls["Mode"].setText(mode)
            self.app.top_status.set(f"✓ {ub} unique / {ts} slips / €{total:,.2f}", "success")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

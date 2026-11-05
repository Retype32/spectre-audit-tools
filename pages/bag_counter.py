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

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDateEdit, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QVBoxLayout, QWidget
)

from config import BAG_LOG_DB, XLRD_AVAILABLE
from engine.bags import BagLogError, day_status, load_bag_log, save_bag_day
from engine.targets import effective, load_targets

from theme import Theme

from utils import extract_report_date, msg_err

from widgets import Card, DataTable, FieldLabel, StatCard





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

        # Daily bag log: bags in and carried over, shared with the whole team
        bag_card = Card("Daily Bag Log",
                        "bags in and carried over — shows whether the day was cleared")
        br = QHBoxLayout(); br.setSpacing(10)
        br.addWidget(FieldLabel("Date"))
        self.bag_date = QDateEdit(QDate.currentDate())
        self.bag_date.setCalendarPopup(True)
        self.bag_date.setDisplayFormat("dd.MM.yyyy")
        self.bag_date.dateChanged.connect(self._show_bag_day)
        br.addWidget(self.bag_date)
        br.addWidget(FieldLabel("Bags in"))
        self.bags_in = QSpinBox(); self.bags_in.setRange(0, 100000); self.bags_in.setMinimumWidth(90)
        br.addWidget(self.bags_in)
        br.addWidget(FieldLabel("Carried over"))
        self.bags_carry = QSpinBox(); self.bags_carry.setRange(0, 100000); self.bags_carry.setMinimumWidth(90)
        br.addWidget(self.bags_carry)
        save_bag_btn = QPushButton("Save Day"); save_bag_btn.setObjectName("primary")
        save_bag_btn.clicked.connect(self.save_bag_day)
        br.addWidget(save_bag_btn)
        br.addStretch()
        bag_card.body.addLayout(br)
        self.bag_status = QLabel()
        self.bag_status.setStyleSheet(f"color:{Theme.TXT_3}; font-size:11px;")
        bag_card.body.addWidget(self.bag_status)
        self.bag_table = DataTable(("Date", "Bags in", "Carried over", "Processed",
                                    "Completion", "Cleared"))
        self.bag_table.setMinimumHeight(200)
        bag_card.body.addWidget(self.bag_table)
        outer.addWidget(bag_card, 1)
        self._refresh_bag_log()

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
            qd = QDate.fromString(rd, "dd.MM.yyyy")
            if qd.isValid():
                self.bag_date.setDate(qd)
            self.info_lbls["Mode"].setText(mode)
            self.app.top_status.set(f"✓ {ub} unique / {ts} slips / €{total:,.2f}", "success")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

    # ── Daily bag log ─────────────────────────────────────────────────────
    def _bag_date_str(self):
        return self.bag_date.date().toString("dd.MM.yyyy")

    def _refresh_bag_log(self):
        """Show the last 14 logged days and the selected day's numbers."""
        try:
            log = load_bag_log(BAG_LOG_DB)
            max_carry = effective(load_targets(), "max_carry_over_bags")
        except Exception as e:
            logging.exception("Bag log")
            self.bag_status.setText(f"Could not read the bag log: {e}")
            return
        self.bag_table.clear()
        dated = sorted(log.items(), key=lambda kv: datetime.datetime.strptime(kv[0], "%d.%m.%Y"),
                       reverse=True)
        for date, entry in dated[:14]:
            st = day_status(entry, max_carry)
            self.bag_table.add_row({
                "Date": date, "Bags in": st["bags"], "Carried over": st["carried_over"],
                "Processed": st["processed"], "Completion": f"{st['completion_pct']:.0f}%",
                "Cleared": "Yes" if st["cleared"] else "No",
            })
        self._log_cache = log
        self._show_bag_day()

    def _show_bag_day(self, *_):
        entry = getattr(self, "_log_cache", {}).get(self._bag_date_str())
        self.bags_in.setValue(entry["bags"] if entry else 0)
        self.bags_carry.setValue(entry["carried_over"] if entry else 0)
        self.bag_status.setText(
            f"{self._bag_date_str()}: saved — {entry['bags']} in, {entry['carried_over']} carried over."
            if entry else f"{self._bag_date_str()}: not logged yet.  Shared file: {BAG_LOG_DB}")

    def save_bag_day(self):
        date = self._bag_date_str()
        try:
            save_bag_day(date, self.bags_in.value(), self.bags_carry.value(), BAG_LOG_DB)
        except BagLogError as e:
            msg_err(self, "Bag Log", str(e)); return
        except Exception as e:
            logging.exception("Saving bag log"); msg_err(self, "Bag Log", str(e)); return
        logging.info(f"Bag log saved for {date}: {self.bags_in.value()} in, "
                     f"{self.bags_carry.value()} carried over")
        self._refresh_bag_log()

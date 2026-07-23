"""
pages/slip_audit — SlipAuditPage.
"""
import logging

import datetime
import os

import pandas as pd

from PySide6.QtCore import (
    Qt
)
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget
)

from config import AMOUNT, OPERATOR, SLIP_AUDIT_PATH, SLIP_HISTORY_DB

from theme import Theme

from utils import load_db_map, msg_err, msg_info, msg_warn

from widgets import Card




class SlipAuditPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._report_count = 0
        outer = QVBoxLayout(self); outer.setContentsMargins(20, 16, 20, 16); outer.setSpacing(14)

        # Action bar
        bar = Card()
        bl = QHBoxLayout(); bl.setSpacing(12); bl.addStretch()
        load_btn = QPushButton("Load Report"); load_btn.setMinimumHeight(36); load_btn.setMinimumWidth(140)
        load_btn.clicked.connect(self.load_slips); bl.addWidget(load_btn)
        save_btn = QPushButton("Save Audit"); save_btn.setObjectName("success")
        save_btn.setMinimumHeight(36); save_btn.setMinimumWidth(140)
        save_btn.clicked.connect(self.save_slips); bl.addWidget(save_btn)
        clear_btn = QPushButton("Clear Session"); clear_btn.setObjectName("danger")
        clear_btn.setMinimumHeight(36); clear_btn.setMinimumWidth(140)
        clear_btn.clicked.connect(self.clear_session); bl.addWidget(clear_btn)
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color:{Theme.TXT_2}; font-size:12px;")
        bl.addWidget(self._status_lbl)
        bl.addStretch()
        bar.body.addLayout(bl)
        outer.addWidget(bar)

        # Cashier table — System count + editable Physical count column
        self.table_card = Card("Cashiers", "enter physical slip counts; difference is computed on Save")
        self.entries_widget = QWidget()
        self.entries_layout = QVBoxLayout(self.entries_widget)
        self.entries_layout.setContentsMargins(0, 0, 0, 0); self.entries_layout.setSpacing(2)
        self.entries_layout.addStretch()

        scroll = QScrollArea(); scroll.setWidget(self.entries_widget); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background:transparent;")
        self.table_card.body.addWidget(scroll)
        outer.addWidget(self.table_card, 1)

    def _clear_entries(self):
        while self.entries_layout.count() > 1:
            it = self.entries_layout.takeAt(0)
            w = it.widget()
            if w is not None: w.deleteLater()

    def _find_entry_by_name(self, name):
        """Return (oid, dict) for the existing entry with this cashier name, or (None, None)."""
        for oid, d in self.app.slip_entries.items():
            if d['name'] == name:
                return oid, d
        return None, None

    def _get_today_saved(self):
        """Load today's already-saved physical counts from Audit_Database.csv."""
        ds = datetime.datetime.now().strftime("%d.%m.%Y")
        today_saved = {}
        if os.path.exists(SLIP_HISTORY_DB):
            try:
                hdf = pd.read_csv(SLIP_HISTORY_DB)
                today_rows = hdf[hdf['Date'] == ds]
                for _, row in today_rows.iterrows():
                    try:
                        today_saved[str(row['Name'])] = str(int(float(row['Physical Count'])))
                    except Exception:
                        pass
            except Exception:
                pass
        return today_saved

    def _rebuild_table(self, today_saved, preserved_phys):
        """Rebuild the cashier rows from self.app.slip_entries."""
        self._clear_entries()
        if not self.app.slip_entries:
            return

        # Header row
        hdr = QFrame(); hdr.setStyleSheet(f"background:{Theme.ELEVATED}; border-radius:4px;")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(14, 8, 14, 8)
        for txt, w in [("Cashier", 280), ("System", 90), ("", 1)]:
            l = QLabel(txt); l.setObjectName("sectionLabel")
            if w > 1: l.setMinimumWidth(w)
            hl.addWidget(l)
        hl.addStretch()
        phy_hdr = QLabel("Physical"); phy_hdr.setObjectName("sectionLabel")
        hl.addWidget(phy_hdr)
        self.entries_layout.insertWidget(self.entries_layout.count() - 1, hdr)

        for name in sorted(d['name'] for d in self.app.slip_entries.values()):
            oid, d = self._find_entry_by_name(name)
            if oid is None:
                continue
            cnt = d['sys']
            row = QFrame()
            row.setStyleSheet(f"background:{Theme.SURFACE}; border:1px solid {Theme.BORDER_S}; border-radius:4px;")
            rl = QHBoxLayout(row); rl.setContentsMargins(14, 6, 14, 6)
            nlbl = QLabel(name[:32]); nlbl.setMinimumWidth(280)
            nlbl.setStyleSheet(f"color:{Theme.TXT}; font-size:12px;")
            rl.addWidget(nlbl)
            clbl = QLabel(str(cnt)); clbl.setMinimumWidth(90)
            clbl.setStyleSheet(f"color:{Theme.ACCENT}; font-weight:600; font-size:13px;")
            rl.addWidget(clbl)
            rl.addStretch()
            ent = QLineEdit(); ent.setMaximumWidth(110); ent.setAlignment(Qt.AlignCenter)
            # Pre-fill: in-session value takes priority over today's saved CSV value
            pre = preserved_phys.get(name) or today_saved.get(name, '')
            ent.setText(pre)
            rl.addWidget(ent)
            self.app.slip_entries[oid]['ent'] = ent
            self.entries_layout.insertWidget(self.entries_layout.count() - 1, row)

    def load_slips(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Report", "",
            "Excel (*.xlsx *.xls);;CSV (*.csv);;All (*.*)")
        if not path: return
        try:
            raw = (pd.read_csv(path, encoding='utf-8', low_memory=False)
                   if path.lower().endswith('.csv') else pd.read_excel(path))
            if raw.empty:
                msg_err(self, "Error", "Empty file"); return
            fdf = None
            for i in range(min(15, len(raw))):
                rv = [str(x).strip() for x in raw.iloc[i].values]
                if OPERATOR in rv or "User" in rv:
                    fdf = raw.iloc[i+1:].copy(); fdf.columns = raw.iloc[i].values
                    if "User" in fdf.columns:
                        fdf = fdf.rename(columns={"User": OPERATOR})
                    break
            if fdf is None: fdf = raw.copy()
            if OPERATOR not in fdf.columns:
                msg_err(self, "Error", f"'{OPERATOR}' not found"); return

            df = fdf.dropna(subset=[OPERATOR])
            cmap = load_db_map(); ids = []
            for v in df[OPERATOR].astype(str):
                for p in v.replace('/', ',').replace(';', ',').replace('|', ',').split(','):
                    p = p.strip()
                    if p and p.lower() not in ('nan', 'none', ''):
                        if p.endswith('.0'): p = p[:-2]
                        try: p = str(int(float(p)))
                        except Exception: pass
                        ids.append(p)
            if not ids:
                msg_warn(self, "No Data", "No valid IDs"); return

            sc = pd.Series(ids).value_counts().to_dict()

            # Preserve physical counts currently entered in the UI
            preserved_phys = {}
            if hasattr(self.app, 'slip_entries') and self.app.slip_entries:
                for d in self.app.slip_entries.values():
                    v = d['ent'].text().strip() if d.get('ent') else ''
                    if v:
                        preserved_phys[d['name']] = v

            # Reset entries — each load shows exactly what's in the new report
            self.app.slip_entries = {}

            # Build name→count and name→[oids] maps for this report
            nc, nti = {}, {}
            for oid, cnt in sc.items():
                name = cmap.get(oid, oid)
                nc[name] = nc.get(name, 0) + cnt
                nti.setdefault(name, []).append(oid)

            # Value per cashier
            nv = {}
            if AMOUNT in df.columns:
                def _first_oid(v):
                    p = str(v).replace('/', ',').replace(';', ',').replace('|', ',').split(',')[0].strip()
                    if p.endswith('.0'): p = p[:-2]
                    try: p = str(int(float(p)))
                    except Exception: pass
                    return p
                dv = df.copy()
                dv[AMOUNT] = pd.to_numeric(dv[AMOUNT], errors='coerce').fillna(0)
                dv['_oid'] = dv[OPERATOR].apply(_first_oid)
                for norm_oid, grp in dv.groupby('_oid'):
                    n = cmap.get(norm_oid, norm_oid)
                    nv[n] = nv.get(n, 0.0) + float(grp[AMOUNT].sum())

            # Populate slip_entries from this report
            for name in nc:
                oids = nti[name]
                primary_oid = oids[0]
                self.app.slip_entries[primary_oid] = {
                    'name': name, 'sys': nc[name],
                    'ent': None, 'all_ids': oids,
                    'val': nv.get(name, 0.0)
                }

            self._report_count = 1
            today_saved = self._get_today_saved()
            self._rebuild_table(today_saved, preserved_phys)

            total_slips = sum(d['sys'] for d in self.app.slip_entries.values())
            n_cashiers = len(self.app.slip_entries)
            self._status_lbl.setText(
                f"{self._report_count} report{'s' if self._report_count > 1 else ''} loaded  —  "
                f"{n_cashiers} cashier{'s' if n_cashiers != 1 else ''},  {total_slips} total slips"
            )
            self.app.last_saved_audit = None
            msg_info(self, "Loaded",
                     f"Report {self._report_count} merged — "
                     f"{len(nc)} cashier{'s' if len(nc) != 1 else ''}, "
                     f"{sum(nc.values())} slips added")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

    def clear_session(self):
        """Reset the page for a fresh audit session."""
        self.app.slip_entries = {}
        self.app.last_saved_audit = None
        self._report_count = 0
        self._clear_entries()
        self._status_lbl.setText("")
        msg_info(self, "Cleared", "Session reset — ready to load a new report")

    def save_slips(self):
        if not self.app.slip_entries:
            msg_warn(self, "No Data", "Load a report first"); return
        try:
            ds = datetime.datetime.now().strftime("%d.%m.%Y"); recs = []
            for oid, d in self.app.slip_entries.items():
                v = d['ent'].text().strip() if d.get('ent') else ''
                try:
                    ph = int(float(v))
                except (ValueError, TypeError):
                    continue
                sy = int(d['sys'])
                recs.append({"Date": ds, "Cashier ID": oid, "Name": d['name'],
                             "System Count": sy, "Physical Count": ph,
                             "Difference": ph - sy,
                             "Total Value": round(d.get('val', 0.0), 2)})
            if not recs:
                msg_warn(self, "No Data", "Enter physical counts"); return

            os.makedirs(SLIP_AUDIT_PATH, exist_ok=True)
            ndf = pd.DataFrame(recs); self.app.last_saved_audit = ndf.copy()
            hdf = ndf[["Date", "Cashier ID", "Name", "System Count", "Physical Count", "Difference", "Total Value"]].copy()
            if os.path.exists(SLIP_HISTORY_DB):
                try:
                    edf = pd.read_csv(SLIP_HISTORY_DB)
                    edf = edf[~((edf['Date'] == ds) & (edf['Name'].isin([r['Name'] for r in recs])))]
                    fdf = pd.concat([edf, hdf], ignore_index=True)
                except Exception:
                    fdf = hdf
            else:
                fdf = hdf
            fdf.to_csv(SLIP_HISTORY_DB, index=False)

            # refresh history page dates
            hp = self.app.pages.get('history')
            if hp: hp.refresh_slip_dates()

            msg_info(self, "Saved", f"{len(recs)} records for {ds}")
        except Exception as e:
            logging.exception("Unhandled exception"); msg_err(self, "Error", str(e))

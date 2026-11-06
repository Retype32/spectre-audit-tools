"""
tests/test_engine_maintenance.py — repairing "1001.0"-style IDs in history files.

All data is fictional. Files are written to a temporary folder.
"""
import datetime
import glob
import os
import shutil
import tempfile
import unittest

import pandas as pd

from config import OPERATOR
from engine.maintenance import tidy_history_ids

CASHIERS = {"1001": "Alice Example", "1002": "Bob Example"}
NOW = datetime.datetime(2026, 11, 6, 9, 30)


class TestTidyHistoryIds(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        p = lambda name: os.path.join(self.dir, name)  # noqa: E731
        self.files = {k: p(f"{k}.csv") for k in
                      ("performance", "mistakes", "all_disc", "customer", "verdicts")}
        pd.DataFrame([("01.11.2026", "1001.0", "1001.0", "200", "500000.0"),
                      ("01.11.2026", "Bob Example", "1002", "150", "300000.0"),
                      ("01.11.2026", "1003.0", "1003.0", "100", "200000.0")],   # not in DB
                     columns=["Date", "Name", "Operator_Id", "System Count", "Total Value"]
                     ).to_csv(self.files["performance"], index=False)
        pd.DataFrame([("01.11.2026|1001.0|9001.0|250.0", "1001.0", "confirmed", "x")],
                     columns=["key", "cashier", "verdict", "reviewed_at"]
                     ).to_csv(self.files["verdicts"], index=False)
        pd.DataFrame([("01.11.2026", "1001.0", "", "small_mistake", "3", "", "x")],
                     columns=["date", "cashier", "operator_id", "type", "severity_points",
                              "notes", "logged_at"]).to_csv(self.files["mistakes"], index=False)
        pd.DataFrame([("C7.0", "x")], columns=["Customer_Id", "Customer_Location"]
                     ).to_csv(self.files["customer"], index=False)
        self.small_dir = os.path.join(self.dir, "disc")
        os.makedirs(os.path.join(self.small_dir, "2026", "11"))
        self.xlsx = os.path.join(self.small_dir, "2026", "11", "01.11.2026.xlsx")
        pd.DataFrame([("1002.0", "1002.0", 2, "01.11.2026")],
                     columns=["Cashier Name", OPERATOR, "Small_Discrepancies", "Report_Date"]
                     ).to_excel(self.xlsx, index=False)

    def run_tidy(self):
        return tidy_history_ids(cashier_map=CASHIERS, files=self.files,
                                small_disc_dir=self.small_dir, now=NOW)

    def test_ids_and_names_repaired(self):
        self.run_tidy()
        perf = pd.read_csv(self.files["performance"], dtype=str)
        self.assertEqual(perf["Name"].tolist(), ["Alice Example", "Bob Example", "1003"])
        self.assertEqual(perf["Operator_Id"].tolist(), ["1001", "1002", "1003"])
        v = pd.read_csv(self.files["verdicts"], dtype=str)
        self.assertEqual((v["key"][0], v["cashier"][0]),
                         ("01.11.2026|1001|9001|250.0", "Alice Example"))
        self.assertEqual(pd.read_csv(self.files["mistakes"], dtype=str)["cashier"][0], "Alice Example")
        x = pd.read_excel(self.xlsx, dtype=str)
        self.assertEqual((x["Cashier Name"][0], x[OPERATOR][0]), ("Bob Example", "1002"))

    def test_text_ids_left_alone(self):
        self.run_tidy()
        self.assertEqual(pd.read_csv(self.files["customer"], dtype=str)["Customer_Id"][0], "C7.0")

    def test_backups_and_report(self):
        report = self.run_tidy()
        changed = {os.path.basename(r["file"]): r["changed"] for r in report}
        self.assertEqual(changed, {"performance.csv": 4, "verdicts.csv": 2,
                                   "mistakes.csv": 1, "01.11.2026.xlsx": 2})
        for r in report:
            self.assertTrue(r["backup"].endswith(".bak-20261106-0930"))
            self.assertTrue(os.path.exists(r["backup"]))
        backup = pd.read_csv(self.files["performance"] + ".bak-20261106-0930", dtype=str)
        self.assertEqual(backup["Name"][0], "1001.0")            # original kept

    def test_second_run_changes_nothing(self):
        self.run_tidy()
        self.assertEqual(self.run_tidy(), [])
        self.assertEqual(len(glob.glob(os.path.join(self.dir, "*.bak-*"))), 3)

    def test_missing_files_are_skipped(self):
        report = tidy_history_ids(cashier_map=CASHIERS,
                                  files={k: os.path.join(self.dir, "none", k) for k in self.files},
                                  small_disc_dir=os.path.join(self.dir, "none"), now=NOW)
        self.assertEqual(report, [])


if __name__ == "__main__":
    unittest.main()

"""
tests/test_engine_archive.py — history files written after an Integrity Check.

All data is fictional. Files are written to a temporary folder.
"""
import os
import shutil
import tempfile
import unittest

import pandas as pd

from config import AMOUNT, COL_DISC, CUSTOMER_ID, CUSTOMER_LOC, EXPECTED_TOTAL, OPERATOR
from engine.archive import (archive_all_discrepancies, archive_customer_discrepancies,
                            archive_small_discrepancies, save_performance_history)


def _report(date_rows=None):
    return pd.DataFrame(date_rows or [
        # operator, name,     customer, location, expected, processed, discrepancy
        ("1001", "Alice",  "C1", "Shop A", 100.0, 95.0,  -5.0),
        ("1001", "Alice",  "C1", "Shop A", 200.0, 200.0,  0.0),
        ("1002", "Bob",    "C2", "Shop B",   0.0, 40.0,  40.0),   # blind count
        ("1002", "Bob",    "C2", "Shop B", 300.0, 300.0,  0.0),
    ], columns=[OPERATOR, "Cashier Name", CUSTOMER_ID, CUSTOMER_LOC,
                EXPECTED_TOTAL, AMOUNT, COL_DISC])


class _TempDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def path(self, name):
        return os.path.join(self.dir, name)


class TestAllDiscrepancies(_TempDir):
    def test_only_non_zero_rows_with_type(self):
        db = self.path("all.csv")
        archive_all_discrepancies(_report(), "15.06.2026", db_path=db)
        out = pd.read_csv(db, dtype=str)
        self.assertEqual(out["Discrepancy"].tolist(), ["-5.0", "40.0"])
        self.assertEqual(out["Type"].tolist(), ["Discrepancy", "Blind Count"])
        self.assertEqual(out["Operator ID"].tolist(), ["1001", "1002"])

    def test_rerun_same_date_replaces_rows(self):
        db = self.path("all.csv")
        archive_all_discrepancies(_report(), "15.06.2026", db_path=db)
        archive_all_discrepancies(_report(), "15.06.2026", db_path=db)
        archive_all_discrepancies(_report(), "16.06.2026", db_path=db)
        out = pd.read_csv(db, dtype=str)
        self.assertEqual(out["Report Date"].value_counts().to_dict(),
                         {"15.06.2026": 2, "16.06.2026": 2})

    def test_no_discrepancy_column_writes_nothing(self):
        db = self.path("all.csv")
        archive_all_discrepancies(_report().drop(columns=[COL_DISC]), "15.06.2026", db_path=db)
        self.assertFalse(os.path.exists(db))


class TestCustomerDiscrepancies(_TempDir):
    def test_counts_per_customer(self):
        db = self.path("cust.csv")
        archive_customer_discrepancies(_report(), "15.06.2026", db_path=db)
        out = pd.read_csv(db, dtype=str).set_index("Customer_Id")
        self.assertEqual(out.loc["C1", "Small_Disc_Count"], "1")       # €5 ≤ €10
        self.assertEqual(out.loc["C1", "Small_Disc_Amount"], "5.0")
        self.assertEqual(out.loc["C2", "All_Discrepancies"], "1")
        self.assertEqual(out.loc["C2", "Small_Disc_Count"], "0")       # €40 > €10
        self.assertEqual(out.loc["C2", "Not_Declaring_Count"], "1")    # disc == processed
        self.assertEqual(out.loc["C2", "Customer_Location"], "Shop B")


class TestSmallDiscrepancies(_TempDir):
    def test_written_to_year_month_folder(self):
        archive_small_discrepancies(_report(), "15.06.2026", base_dir=self.dir)
        fp = os.path.join(self.dir, "2026", "06", "15.06.2026.xlsx")
        out = pd.read_excel(fp, dtype=str)
        self.assertEqual(out[["Cashier Name", "Small_Discrepancies"]].values.tolist(),
                         [["Alice", "1"]])


class TestPerformanceHistory(_TempDir):
    def test_one_row_per_cashier_and_idempotent(self):
        db = self.path("perf.csv")
        save_performance_history(_report(), "15.06.2026", db_path=db)
        save_performance_history(_report(), "15.06.2026", db_path=db)
        out = pd.read_csv(db, dtype=str).set_index("Name")
        self.assertEqual(len(out), 2)
        self.assertEqual(out.loc["Alice", "System Count"], "2")
        self.assertEqual(out.loc["Alice", "Total Value"], "295.0")
        self.assertEqual(out.loc["Bob", "Operator_Id"], "1002")
        self.assertEqual(out.loc["Bob", "Format"], "VMS")

    def test_vms_and_isa_same_day_kept_apart(self):
        db = self.path("perf.csv")
        save_performance_history(_report(), "15.06.2026", db_path=db, fmt="VMS")
        save_performance_history(_report(), "15.06.2026", db_path=db, fmt="ISA")
        save_performance_history(_report(), "15.06.2026", db_path=db, fmt="ISA")
        out = pd.read_csv(db, dtype=str)
        self.assertEqual(out["Format"].value_counts().to_dict(), {"VMS": 2, "ISA": 2})

    def test_old_rows_without_format_count_as_vms(self):
        db = self.path("perf.csv")
        pd.DataFrame([("15.06.2026", "Alice", "1001", "9", "9.0")],
                     columns=["Date", "Name", "Operator_Id", "System Count", "Total Value"]
                     ).to_csv(db, index=False)
        save_performance_history(_report(), "15.06.2026", db_path=db, fmt="VMS")
        out = pd.read_csv(db, dtype=str)
        self.assertEqual(len(out), 2)                       # old VMS row replaced
        self.assertNotIn("9", out["System Count"].tolist())


if __name__ == "__main__":
    unittest.main()

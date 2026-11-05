"""
tests/test_engine_report.py — loading and cleaning VMS / ISA reports.

All data is fictional. Files are written to a temporary folder.
"""
import os
import shutil
import tempfile
import unittest

import pandas as pd

from config import AMOUNT, LODGEMENT, OPERATOR, WALLET
from engine.report import (EMPTY_WALLET, NO_LODGEMENT, ReportError, load_report,
                           summarise)

CASHIERS = {"1001": "Alice Example", "1002": "Bob Example"}


class _TempDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def path(self, name):
        return os.path.join(self.dir, name)

    def write_csv(self, text, name="report.csv"):
        p = self.path(name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p


VMS_CSV = (
    "Operator Id,Wallet Number,Lodgement Slip Number,Total Processed,€50 Notes,Processed Date\n"
    "1001,W1,S1,100.004,2,15/06/2026\n"
    "1001, ,S2,250,5,15/06/2026\n"      # blank wallet
    "1002,W2,S3,0.50,0,15/06/2026\n"    # below €1 → dropped
    "1003,W4,S5,abc,1,15/06/2026\n"     # non-numeric amount → dropped
    "1002,W2,S6,75,x,15/06/2026\n"      # bad denomination → 0
)


class TestVmsReport(_TempDir):
    def setUp(self):
        super().setUp()
        self.report = load_report(self.write_csv(VMS_CSV), cashier_map=CASHIERS)
        self.df = self.report.df

    def test_format_and_date(self):
        self.assertEqual(self.report.fmt, "VMS")
        self.assertEqual(self.report.report_date, "15.06.2026")
        self.assertEqual(self.report.filename, "report.csv")

    def test_invalid_rows_dropped(self):
        self.assertEqual(self.df[LODGEMENT].tolist(), ["S1", "S2", "S6"])

    def test_amounts_rounded(self):
        self.assertEqual(self.df[AMOUNT].tolist(), [100.0, 250.0, 75.0])

    def test_blank_wallet_marked_empty(self):
        self.assertEqual(self.df[WALLET].tolist(), ["W1", EMPTY_WALLET, "W2"])

    def test_denominations_are_ints(self):
        self.assertEqual(self.report.denom_cols, ["€50 Notes"])
        self.assertEqual(self.df["€50 Notes"].tolist(), [2, 5, 0])

    def test_cashier_names_mapped(self):
        self.assertEqual(self.df["Cashier Name"].tolist(),
                         ["Alice Example", "Alice Example", "Bob Example"])

    def test_unknown_operator_keeps_id_as_name(self):
        report = load_report(self.write_csv(VMS_CSV, "r2.csv"), cashier_map={})
        self.assertEqual(report.df["Cashier Name"].tolist(), ["1001", "1001", "1002"])

    def test_summary(self):
        s = summarise(self.report)
        self.assertEqual((s["rows"], s["cashiers"], s["total_value"], s["format"]),
                         (3, 2, 425.0, "VMS"))


class TestBlankOperatorCell(_TempDir):
    CSV = ("Operator Id,Total Processed,Processed Date\n"
           "1001,100,15/06/2026\n"
           ",80,15/06/2026\n"
           "1002,50,15/06/2026\n")

    def test_row_without_operator_is_dropped(self):
        df = load_report(self.write_csv(self.CSV), cashier_map={}).df
        self.assertEqual(df[AMOUNT].tolist(), [100.0, 50.0])

    @unittest.expectedFailure
    def test_ids_keep_integer_form(self):
        # KNOWN ISSUE: one blank Operator Id cell makes pandas read the column
        # as floats, so IDs become "1001.0" and no longer match the Cashier
        # Database. Remove @expectedFailure once this is fixed.
        df = load_report(self.write_csv(self.CSV), cashier_map=CASHIERS).df
        self.assertEqual(df[OPERATOR].tolist(), ["1001", "1002"])


class TestMissingColumns(_TempDir):
    def test_missing_lodgement_column_becomes_na(self):
        p = self.write_csv("Operator Id,Total Processed\n1001,10\n")
        df = load_report(p, cashier_map={}).df
        self.assertEqual(df[LODGEMENT].tolist(), [NO_LODGEMENT])
        self.assertEqual(df[WALLET].tolist(), [EMPTY_WALLET])

    def test_missing_operator_column(self):
        p = self.write_csv("User Id,Total Processed\n1001,10\n")
        with self.assertRaises(ReportError) as cm:
            load_report(p, cashier_map={})
        self.assertEqual((cm.exception.title, cm.exception.level), ("Missing Column", "error"))
        self.assertIn(OPERATOR, cm.exception.message)

    def test_missing_amount_column(self):
        p = self.write_csv("Operator Id,Amount\n1001,10\n")
        with self.assertRaises(ReportError) as cm:
            load_report(p, cashier_map={})
        self.assertIn(AMOUNT, cm.exception.message)

    def test_header_only_file_is_empty(self):
        p = self.write_csv("Operator Id,Total Processed\n")
        with self.assertRaises(ReportError) as cm:
            load_report(p, cashier_map={})
        self.assertEqual(cm.exception.message, "File is empty")

    def test_no_valid_rows_is_a_warning(self):
        p = self.write_csv("Operator Id,Total Processed,Processed Date\n"
                           "1001,0.5,17/06/2026\n1002,0.2,17/06/2026\n")
        with self.assertRaises(ReportError) as cm:
            load_report(p, cashier_map={})
        self.assertEqual((cm.exception.title, cm.exception.level), ("No Data", "warning"))
        self.assertEqual(cm.exception.report_date, "17.06.2026")   # UI still records it


class TestIsaReport(_TempDir):
    def test_preamble_skipped_and_columns_renamed(self):
        rows = [
            ["ISA Lodgement Report", None, None, None, None],
            ["Generated", "16/06/2026", None, None, None],
            ["User", "Seal", "Lodgement Number", "Counted", "Processed Date"],
            ["1001", "SEAL-1", "L1", 120.0, "16/06/2026"],
            ["1002", "SEAL-2", "L2", 80.0, "16/06/2026"],
        ]
        p = self.path("isa.xlsx")
        pd.DataFrame(rows[1:], columns=rows[0]).to_excel(p, index=False)

        report = load_report(p, cashier_map=CASHIERS)
        self.assertEqual(report.fmt, "ISA")
        self.assertEqual(report.report_date, "16.06.2026")
        df = report.df
        for col in (OPERATOR, WALLET, LODGEMENT, AMOUNT):
            self.assertIn(col, df.columns)
        self.assertEqual(df[WALLET].tolist(), ["SEAL-1", "SEAL-2"])
        self.assertEqual(df["Cashier Name"].tolist(), ["Alice Example", "Bob Example"])


if __name__ == "__main__":
    unittest.main()

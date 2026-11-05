"""
tests/test_engine_detection.py — the three Integrity Check detection rules.

All data is fictional.
"""
import unittest

import pandas as pd

from config import AMOUNT, LODGEMENT, OPERATOR, WALLET
from engine.detection import run_integrity_checks
from engine.report import EMPTY_WALLET

DENOM = "€50 Notes"   # a denomination column (name contains "50")


def _df(rows):
    """rows: (operator, wallet, slip, amount, notes_50) tuples."""
    df = pd.DataFrame(rows, columns=[OPERATOR, WALLET, LODGEMENT, AMOUNT, DENOM])
    df["Cashier Name"] = "Cashier " + df[OPERATOR]
    return df


def _check(rows):
    return run_integrity_checks(_df(rows), [DENOM])


def _lines(rows):
    return [r["_line"] for r in rows]


class TestCleanReport(unittest.TestCase):
    def test_no_flags_on_distinct_rows(self):
        r = _check([("1", "W1", "S1", 100.0, 2),
                    ("2", "W2", "S2", 200.0, 4)])
        self.assertEqual((r.high_risk_count, r.suspicious_count, r.shared_wallet_count), (0, 0, 0))
        self.assertEqual((r.exact_rows, r.suspicious_rows, r.shared_wallet_rows), ([], [], []))


class TestHighRiskDuplicates(unittest.TestCase):
    def test_identical_pair_is_high_risk(self):
        r = _check([("1", "W1", "S1", 100.0, 2),
                    ("1", "W1", "S1", 100.0, 2),
                    ("2", "W2", "S2", 300.0, 6)])
        self.assertEqual(r.high_risk_count, 1)
        self.assertEqual(_lines(r.exact_rows), [2, 3])     # index + 2 = spreadsheet line
        self.assertEqual(r.suspicious_count, 0)

    def test_different_denominations_are_not_high_risk(self):
        r = _check([("1", "W1", "S1", 100.0, 2),
                    ("1", "W1", "S1", 100.0, 1)])
        self.assertEqual(r.high_risk_count, 0)
        self.assertEqual(r.suspicious_count, 1)            # same op + wallet + amount

    def test_count_is_pairs_rounded_down(self):
        # Existing rule: count = flagged rows // 2, so a triplicate counts as 1
        r = _check([("1", "W1", "S1", 100.0, 2)] * 3)
        self.assertEqual(r.high_risk_count, 1)
        self.assertEqual(len(r.exact_rows), 3)

    def test_rows_are_returned_with_all_columns(self):
        r = _check([("1", "W1", "S1", 100.0, 2)] * 2)
        row = r.exact_rows[0]
        for col in (OPERATOR, WALLET, LODGEMENT, AMOUNT, DENOM, "Cashier Name", "_line"):
            self.assertIn(col, row)


class TestSuspiciousPatterns(unittest.TestCase):
    def test_same_operator_wallet_amount_different_slip(self):
        r = _check([("1", "W1", "S1", 100.0, 2),
                    ("1", "W1", "S2", 100.0, 2)])
        self.assertEqual(r.suspicious_count, 1)
        self.assertEqual(_lines(r.suspicious_rows), [2, 3])
        self.assertEqual(r.high_risk_count, 0)

    def test_different_operator_is_not_suspicious(self):
        r = _check([("1", "W1", "S1", 100.0, 2),
                    ("2", "W1", "S2", 100.0, 2)])
        self.assertEqual(r.suspicious_count, 0)

    def test_exact_duplicates_are_not_counted_again(self):
        # Pair of exact duplicates + a third row matching op/wallet/amount.
        # Only the third row is "suspicious", and a group of one is not listed.
        r = _check([("1", "W1", "S1", 100.0, 2),
                    ("1", "W1", "S1", 100.0, 2),
                    ("1", "W1", "S9", 100.0, 2)])
        self.assertEqual(r.high_risk_count, 1)
        self.assertEqual(r.suspicious_count, 0)
        self.assertEqual(r.suspicious_rows, [])


class TestSharedWallets(unittest.TestCase):
    def test_wallet_used_by_two_operators(self):
        r = _check([("1", "W1", "S1", 100.0, 2),
                    ("2", "W1", "S2", 250.0, 5),
                    ("3", "W3", "S3", 300.0, 6)])
        self.assertEqual(r.shared_wallet_count, 1)
        self.assertEqual(_lines(r.shared_wallet_rows), [2, 3])

    def test_same_operator_reusing_wallet_is_not_shared(self):
        r = _check([("1", "W1", "S1", 100.0, 2),
                    ("1", "W1", "S2", 250.0, 5)])
        self.assertEqual(r.shared_wallet_count, 0)

    def test_empty_wallets_are_ignored(self):
        r = _check([("1", EMPTY_WALLET, "S1", 100.0, 2),
                    ("2", EMPTY_WALLET, "S2", 250.0, 5)])
        self.assertEqual(r.shared_wallet_count, 0)
        self.assertEqual(r.shared_wallet_rows, [])


if __name__ == "__main__":
    unittest.main()

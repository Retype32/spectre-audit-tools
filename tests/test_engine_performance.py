"""
tests/test_engine_performance.py — cashier performance for a period.

All names and figures are fictional. Files are written to a temporary folder.
"""
import datetime
import os
import shutil
import tempfile
import unittest

import pandas as pd

from config import AMOUNT, OPERATOR
from engine.performance import (compute_performance, log_mistake, scope_cutoff, sort_rows,
                                team_summary)
from scoring import score_one_session

TODAY = datetime.date(2026, 6, 20)
ACTIVE = "20.06.2026"


def _report(rows):
    """rows: (cashier, operator, amount)."""
    return pd.DataFrame(rows, columns=["Cashier Name", OPERATOR, AMOUNT])


def _mistake(cashier, date, points=3, mtype="small_mistake"):
    return {"date": date, "cashier": cashier, "type": mtype, "points": points, "notes": ""}


class _TempDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.hist = os.path.join(self.dir, "Performance_History.csv")

    def write_history(self, rows):
        """rows: (date, name, operator, slips, value)."""
        pd.DataFrame(rows, columns=["Date", "Name", "Operator_Id", "System Count",
                                    "Total Value"]).to_csv(self.hist, index=False)

    def perf(self, df, scope, mistakes=None):
        return compute_performance(df, scope, active_date=ACTIVE, today=TODAY,
                                   history_path=self.hist, mistakes_by_c=mistakes or {})


class TestScopeCutoff(unittest.TestCase):
    def test_cutoffs(self):
        self.assertIsNone(scope_cutoff("This Report", TODAY))
        self.assertEqual(scope_cutoff("Today", TODAY), TODAY)
        self.assertEqual(scope_cutoff("This Week", TODAY), datetime.date(2026, 6, 13))
        self.assertEqual(scope_cutoff("This Month", TODAY), datetime.date(2026, 6, 1))
        self.assertEqual(scope_cutoff("3 Months", TODAY), datetime.date(2026, 3, 22))


class TestSingleReport(_TempDir):
    def setUp(self):
        super().setUp()
        self.write_history([("01.06.2026", "Alice", "1001", 100, 20000),
                            ("02.06.2026", "Alice", "1001", 300, 60000)])
        self.df = _report([("Alice", "1001", 100.0)] * 4 + [("Bob", "1002", 50.0)] * 2)

    def test_targets_are_history_average(self):
        r = self.perf(self.df, "This Report")
        self.assertEqual((r.target_slips, r.target_value), (200.0, 40000.0))

    def test_scores_match_session_formula(self):
        mistakes = {"Alice": [_mistake("Alice", ACTIVE), _mistake("Alice", "01.06.2026")]}
        r = self.perf(self.df, "This Report", mistakes)
        alice = next(x for x in r.rows if x["name"] == "Alice")
        expected = score_one_session(4, 400.0, "1001", [mistakes["Alice"][0]], 200.0, 40000.0)
        self.assertEqual(alice["score"], int(round(expected["total"])))
        self.assertEqual(alice["mistakes"], 1)            # only the report-date mistake
        self.assertEqual((alice["txn"], alice["value"], alice["sessions"]), (4, 400.0, 1))
        self.assertIsNone(alice["consistency"])

    def test_history_cashiers_not_added(self):
        df = _report([("Bob", "1002", 50.0)])
        r = self.perf(df, "This Report")
        self.assertEqual([x["name"] for x in r.rows], ["Bob"])

    def test_no_cashier_column_returns_none(self):
        self.assertIsNone(self.perf(self.df.drop(columns=["Cashier Name"]), "This Report"))


class TestMultiDay(_TempDir):
    def setUp(self):
        super().setUp()
        self.write_history([
            ("19.06.2026", "Alice", "1001", 200, 40000),   # in "This Week"
            ("20.06.2026", "Alice", "1001", 999, 99999),   # same date as report → skipped
            ("01.05.2026", "Alice", "1001", 200, 40000),   # outside "This Week"
            ("18.06.2026", "Carol", "1003", 150, 30000),   # history only
            ("bad date",   "Carol", "1003", 150, 30000),   # unparseable → skipped
        ])
        self.df = _report([("Alice", "1001", 100.0)] * 2)

    def test_week_includes_recent_history_and_session(self):
        r = self.perf(self.df, "This Week")
        rows = {x["name"]: x for x in r.rows}
        self.assertEqual(sorted(rows), ["Alice", "Carol"])
        self.assertEqual(rows["Alice"]["sessions"], 2)         # report + 19.06
        self.assertEqual(rows["Alice"]["txn"], 202)
        self.assertEqual(rows["Carol"]["sessions"], 1)
        self.assertEqual(rows["Carol"]["op_id"], "1003")       # backfilled from history

    def test_three_months_includes_older_history(self):
        r = self.perf(self.df, "3 Months")
        alice = next(x for x in r.rows if x["name"] == "Alice")
        self.assertEqual(alice["sessions"], 3)

    def test_period_penalty_counts_all_mistakes_in_period(self):
        m = {"Alice": [_mistake("Alice", "19.06.2026", 12, "miscredit"),
                       _mistake("Alice", ACTIVE, 3)]}
        r = self.perf(self.df, "This Week", m)
        alice = next(x for x in r.rows if x["name"] == "Alice")
        self.assertEqual((alice["mistakes"], alice["penalty"]), (2, 15))

    def test_score_stays_within_0_100(self):
        r = self.perf(self.df, "This Week")
        for row in r.rows:
            self.assertTrue(0 <= row["score"] <= 100)
            self.assertIn(row["grade"], "ABCDF")


class TestTeamSummaryAndSorting(unittest.TestCase):
    ROWS = [
        {"name": "bob", "score": 80, "grade": "B", "txn": 100, "value": 1000.0,
         "slips_per_hr": 12.0, "mistakes": 1, "penalty": 3, "accuracy": 19.0, "consistency": None},
        {"name": "Alice", "score": 91, "grade": "A", "txn": 200, "value": 3000.0,
         "slips_per_hr": 24.0, "mistakes": 0, "penalty": 0, "accuracy": 20.0, "consistency": 9.0},
        {"name": "Carol", "score": 50, "grade": "D", "txn": 50, "value": 500.0,
         "slips_per_hr": 6.0, "mistakes": 4, "penalty": 30, "accuracy": 12.0, "consistency": 2.0},
    ]

    def test_team_summary(self):
        t = team_summary(self.ROWS)
        self.assertEqual((t["cashiers"], t["total_txn"], t["total_value"]), (3, 350, 4500.0))
        self.assertEqual((t["team_score"], t["team_grade"]), (73, "C"))
        self.assertEqual((t["total_mistakes"], t["total_penalty"]), (5, 33))
        self.assertEqual(t["avg_rate"], 14.0)
        self.assertEqual(t["grade_counts"], {"A": 1, "B": 1, "C": 0, "D": 1, "F": 0})

    def test_sort_by_score_lowest_first(self):
        self.assertEqual([r["name"] for r in sort_rows(self.ROWS, "score", ascending=True)],
                         ["Carol", "bob", "Alice"])

    def test_sort_by_name_ignores_case(self):
        self.assertEqual([r["name"] for r in sort_rows(self.ROWS, "name", ascending=True)],
                         ["Alice", "bob", "Carol"])

    def test_missing_consistency_sorts_as_zero(self):
        self.assertEqual([r["name"] for r in sort_rows(self.ROWS, "consistency")],
                         ["Alice", "Carol", "bob"])


class TestLogMistake(_TempDir):
    def test_appends_rows_with_type_points(self):
        db = os.path.join(self.dir, "sub", "mistakes.csv")
        now = datetime.datetime(2026, 6, 20, 9, 30)
        log_mistake("20.06.2026", "Alice", "miscredit", "wrong account", db_path=db, now=now)
        log_mistake("20.06.2026", "Bob", "small_mistake", db_path=db, now=now)
        out = pd.read_csv(db, dtype=str)
        self.assertEqual(out["cashier"].tolist(), ["Alice", "Bob"])
        self.assertEqual(out["severity_points"].tolist(), ["12", "3"])
        self.assertEqual(out["logged_at"].tolist(), ["2026-06-20 09:30"] * 2)


if __name__ == "__main__":
    unittest.main()

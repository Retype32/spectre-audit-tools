"""
tests/test_engine_performance.py — cashier performance for a period.

All names and figures are fictional. Files are written to a temporary folder.
Every cashier here works an 8-hour shift (no 10-hour operators configured).
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

TODAY = datetime.date(2026, 6, 20)
ACTIVE = "20.06.2026"


def _report(rows):
    """rows: (cashier, operator, number of slips, amount per slip)."""
    out = []
    for name, op, n, amount in rows:
        out += [(name, op, amount)] * n
    return pd.DataFrame(out, columns=["Cashier Name", OPERATOR, AMOUNT])


# Alice: 200 slips (25/hr), €500k · Bob: 100 slips (12.5/hr), €250k
# Zed: 45 slips, ~€1.5m → 360 processing
TEAM = [("Alice", "1001", 200, 2500.0), ("Bob", "1002", 100, 2500.0),
        ("Zed", "1009", 45, 33000.0)]


def _mistake(cashier, date, points=3, mtype="small_mistake"):
    return {"date": date, "cashier": cashier, "type": mtype, "points": points, "notes": ""}


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.hist = os.path.join(self.dir, "Performance_History.csv")

    def write_history(self, rows):
        """rows: (date, name, operator, slips, value[, format])."""
        rows = [r if len(r) == 6 else r + ("VMS",) for r in rows]
        pd.DataFrame(rows, columns=["Date", "Name", "Operator_Id", "System Count",
                                    "Total Value", "Format"]).to_csv(self.hist, index=False)

    def perf(self, df, scope, mistakes=None, targets=None, bags=None, fmt="VMS",
             active=ACTIVE):
        return compute_performance(df, scope, active_date=active, today=TODAY,
                                   history_path=self.hist, mistakes_by_c=mistakes or {},
                                   targets=targets or {}, report_fmt=fmt, bag_log=bags or {})

    @staticmethod
    def by_name(result):
        return {r["name"]: r for r in result.rows}


class TestScopeCutoff(unittest.TestCase):
    def test_cutoffs(self):
        self.assertIsNone(scope_cutoff("This Report", TODAY))
        self.assertEqual(scope_cutoff("Today", TODAY), TODAY)
        self.assertEqual(scope_cutoff("This Week", TODAY), datetime.date(2026, 6, 13))
        self.assertEqual(scope_cutoff("This Month", TODAY), datetime.date(2026, 6, 1))
        self.assertEqual(scope_cutoff("3 Months", TODAY), datetime.date(2026, 3, 22))


class TestSingleReport(_Base):
    def setUp(self):
        super().setUp()
        self.result = self.perf(_report(TEAM), "This Report")
        self.rows = self.by_name(self.result)

    def test_360_processor_is_listed_not_scored(self):
        self.assertEqual(sorted(self.rows), ["Alice", "Bob"])
        self.assertEqual([(u["name"], u["kind"]) for u in self.result.unscored], [("Zed", "360")])

    def test_on_target_cashier_scores_90(self):
        alice = self.rows["Alice"]
        self.assertEqual((alice["score"], alice["grade"]), (90, "A"))
        self.assertEqual(alice["breakdown"]["rate_score"], 50.0)
        self.assertEqual(alice["throughput"], 1.0)

    def test_half_pace_cashier(self):
        bob = self.rows["Bob"]["breakdown"]
        self.assertEqual(bob["rate_score"], 25.0)
        # cash/hr €31,250 vs team €46,875 (Zed excluded) → 6.7 of 10
        self.assertEqual(bob["cash_score"], 6.7)
        self.assertEqual(self.rows["Bob"]["score"], 62)

    def test_default_target(self):
        self.assertEqual((self.result.target_per_hour, self.result.target_sources),
                         (25.0, {"per_hour": "default"}))

    def test_manager_rate_target(self):
        r = self.by_name(self.perf(_report(TEAM), "This Report", targets={"slips_per_hour": 20}))
        self.assertEqual(r["Bob"]["breakdown"]["rate_score"], 31.2)   # 12.5 / 20 × 50

    def test_360_rules_can_be_changed(self):
        r = self.perf(_report(TEAM), "This Report",
                      targets={"proc360_min_cash_per_slip": 50000})
        self.assertIn("Zed", self.by_name(r))                          # no longer 360

    def test_isa_report_is_not_scored(self):
        r = self.perf(_report(TEAM), "This Report", fmt="ISA")
        self.assertEqual(r.rows, [])
        self.assertEqual({u["kind"] for u in r.unscored}, {"other"})

    def test_no_cashier_column_returns_none(self):
        self.assertIsNone(self.perf(_report(TEAM).drop(columns=["Cashier Name"]), "This Report"))

    def test_report_date_mistakes_only(self):
        m = {"Bob": [_mistake("Bob", ACTIVE), _mistake("Bob", "01.06.2026")]}
        bob = self.by_name(self.perf(_report(TEAM), "This Report", mistakes=m))["Bob"]
        self.assertEqual((bob["mistakes"], bob["penalty"]), (1, 3))


class TestClearedDays(_Base):
    def test_cleared_day_lowers_the_target_to_the_team_pace(self):
        r = self.perf(_report(TEAM), "This Report", bags={ACTIVE: {"bags": 50, "carried_over": 0}})
        day = r.days[0]
        self.assertTrue(day["cleared"])
        self.assertEqual(day["achieved_rate"], 18.75)                 # 300 slips / 16 hours
        self.assertEqual(day["rate_target"], 18.75)
        rows = self.by_name(r)
        self.assertEqual(rows["Alice"]["breakdown"]["rate_score"], 50.0)
        self.assertEqual(rows["Bob"]["breakdown"]["rate_score"], 33.3)   # 12.5 / 18.75
        self.assertGreater(rows["Bob"]["score"], 62)

    def test_carry_over_keeps_the_normal_target(self):
        r = self.perf(_report(TEAM), "This Report", bags={ACTIVE: {"bags": 50, "carried_over": 5}})
        self.assertFalse(r.days[0]["cleared"])
        self.assertEqual(r.days[0]["rate_target"], 25.0)

    def test_allowed_carry_over(self):
        r = self.perf(_report(TEAM), "This Report", targets={"max_carry_over_bags": 5},
                      bags={ACTIVE: {"bags": 50, "carried_over": 5}})
        self.assertTrue(r.days[0]["cleared"])

    def test_day_without_bag_log(self):
        r = self.perf(_report(TEAM), "This Report")
        self.assertIsNone(r.days[0]["cleared"])
        self.assertEqual(r.days[0]["rate_target"], 25.0)


class TestMultiDay(_Base):
    def setUp(self):
        super().setUp()
        self.write_history([
            ("19.06.2026", "Alice", "1001", 200, 500000),
            ("19.06.2026", "Carol", "1003", 150, 300000),          # history only
            ("18.06.2026", "Carol", "1003", 40, 1600000),          # Carol on 360 that day
            ("17.06.2026", "Alice", "1001", 180, 450000, "ISA"),   # not VMS
            ("20.06.2026", "Alice", "1001", 999, 999999),          # same day as report → skipped
            ("20.06.2026", "Dan", "1004", 120, 200000, "ISA"),     # same day, other format → kept
            ("01.05.2026", "Alice", "1001", 200, 500000),          # outside "This Week"
            ("bad date", "Carol", "1003", 150, 300000),
        ])
        self.df = _report(TEAM[:2])

    def test_week(self):
        r = self.perf(self.df, "This Week")
        rows = self.by_name(r)
        self.assertEqual(sorted(rows), ["Alice", "Bob", "Carol"])
        self.assertEqual((rows["Alice"]["sessions"], rows["Alice"]["txn"]), (2, 400))
        self.assertEqual((rows["Carol"]["sessions"], rows["Carol"]["days_360"]), (1, 1))
        self.assertEqual(rows["Alice"]["days_other"], 1)
        self.assertEqual(rows["Carol"]["op_id"], "1003")
        kinds = sorted((u["name"], u["kind"]) for u in r.unscored)
        self.assertEqual(kinds, [("Alice", "other"), ("Carol", "360"), ("Dan", "other")])
        self.assertEqual(r.working_days, [datetime.date(2026, 6, 19), TODAY])

    def test_three_months_includes_older_history(self):
        alice = self.by_name(self.perf(self.df, "3 Months"))["Alice"]
        self.assertEqual(alice["sessions"], 3)

    def test_old_report_outside_period_is_left_out(self):
        r = self.perf(self.df, "This Week", active="01.05.2026")
        self.assertNotIn("Bob", self.by_name(r))

    def test_mistakes_on_unscored_days_still_cost_points(self):
        base = self.by_name(self.perf(self.df, "This Week"))["Alice"]
        m = {"Alice": [_mistake("Alice", "16.06.2026", 20, "duplicate_slip")]}
        alice = self.by_name(self.perf(self.df, "This Week", mistakes=m))["Alice"]
        self.assertEqual((alice["penalty"], alice["orphan_penalty"]), (20, 20))
        self.assertEqual(alice["score"], base["score"] - 20)

    def test_scores_stay_within_0_100(self):
        for row in self.perf(self.df, "This Week").rows:
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


class TestLogMistake(_Base):
    def test_appends_rows_with_type_points(self):
        db = os.path.join(self.dir, "sub", "mistakes.csv")
        now = datetime.datetime(2026, 6, 20, 9, 30)
        log_mistake("20.06.2026", "Alice", "duplicate_slip", "same bag twice", db_path=db, now=now)
        log_mistake("20.06.2026", "Bob", "small_mistake", db_path=db, now=now)
        out = pd.read_csv(db, dtype=str)
        self.assertEqual(out["cashier"].tolist(), ["Alice", "Bob"])
        self.assertEqual(out["severity_points"].tolist(), ["20", "3"])
        self.assertEqual(out["logged_at"].tolist(), ["2026-06-20 09:30"] * 2)


if __name__ == "__main__":
    unittest.main()

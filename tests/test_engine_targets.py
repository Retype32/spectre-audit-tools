"""
tests/test_engine_targets.py — team targets: validation, shared file, use in
the score, and actual-vs-target comparison.

All names and figures are fictional. Files are written to a temporary folder.
"""
import datetime
import json
import os
import shutil
import tempfile
import unittest

import pandas as pd

from config import AMOUNT, OPERATOR
from engine.detection import IntegrityResult
from engine.performance import compute_performance
from engine.targets import (BY_KEY, TARGETS, TargetError, clean_targets, compare,
                            integrity_progress, load_targets, parse_value,
                            performance_progress, read_targets_file, save_targets)

TODAY = datetime.date(2026, 6, 20)
ACTIVE = "20.06.2026"


class _TempDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.file = os.path.join(self.dir, "targets.json")


class TestDefinitions(unittest.TestCase):
    def test_keys_unique_and_well_formed(self):
        self.assertEqual(len(BY_KEY), len(TARGETS))
        for t in TARGETS:
            self.assertIn(t.better, ("higher", "lower"))
        self.assertEqual({t.key for t in TARGETS if t.in_score},
                         {"cashier_daily_slips", "cashier_daily_value", "slips_per_hour"})


class TestParsing(unittest.TestCase):
    def test_blank_means_no_target(self):
        for raw in (None, "", "   "):
            self.assertIsNone(parse_value(BY_KEY["team_score"], raw))

    def test_euro_and_thousands_separators(self):
        self.assertEqual(parse_value(BY_KEY["team_daily_value"], "€52,500"), 52500.0)
        self.assertEqual(parse_value(BY_KEY["max_error_rate"], "2.5%"), 2.5)

    def test_invalid_values(self):
        with self.assertRaises(ValueError):
            parse_value(BY_KEY["team_score"], "abc")
        with self.assertRaises(ValueError):
            parse_value(BY_KEY["max_shared_wallets"], "-1")
        with self.assertRaises(ValueError):
            parse_value(BY_KEY["team_score"], "101")          # points are 0–100
        with self.assertRaises(ValueError):
            parse_value(BY_KEY["slips_per_hour"], "0")        # scoring targets must be > 0

    def test_zero_allowed_for_maximums(self):
        self.assertEqual(parse_value(BY_KEY["max_high_risk_duplicates"], "0"), 0.0)

    def test_clean_collects_all_errors_and_drops_unknown(self):
        with self.assertRaises(TargetError) as cm:
            clean_targets({"team_score": "abc", "slips_per_hour": "0", "not_a_target": "5"})
        self.assertEqual(len(cm.exception.errors), 2)
        self.assertEqual(clean_targets({"team_score": "80", "not_a_target": "5", "min_cashier_score": ""}),
                         {"team_score": 80.0})


class TestSharedFile(_TempDir):
    def test_missing_file_means_no_targets(self):
        self.assertEqual(read_targets_file(self.file), ({}, None))
        self.assertEqual(load_targets(self.file), {})

    def test_save_and_read_back(self):
        now = datetime.datetime(2026, 6, 20, 14, 5)
        saved = save_targets({"team_score": "80", "slips_per_hour": "28", "team_daily_value": ""},
                             self.file, now=now)
        self.assertEqual(saved, {"team_score": 80.0, "slips_per_hour": 28.0})
        self.assertEqual(read_targets_file(self.file), (saved, None))
        with open(self.file, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual((data["version"], data["updated_at"]), (1, "2026-06-20 14:05"))
        self.assertFalse(os.path.exists(self.file + ".tmp"))

    def test_invalid_input_does_not_overwrite_file(self):
        save_targets({"team_score": "80"}, self.file)
        with self.assertRaises(TargetError):
            save_targets({"team_score": "200"}, self.file)
        self.assertEqual(load_targets(self.file), {"team_score": 80.0})

    def test_bad_values_in_file_are_skipped_and_reported(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump({"targets": {"team_score": 80, "slips_per_hour": -3}}, f)
        targets, problem = read_targets_file(self.file)
        self.assertEqual(targets, {"team_score": 80.0})
        self.assertIn("Slips per hour", problem)

    def test_unreadable_file(self):
        with open(self.file, "w", encoding="utf-8") as f:
            f.write("{not json")
        targets, problem = read_targets_file(self.file)
        self.assertEqual(targets, {})
        self.assertIn("Could not read", problem)


class TestCompare(unittest.TestCase):
    def test_higher_is_better(self):
        c = compare("team_score", 72, {"team_score": 80})
        self.assertEqual((c["gap"], round(c["gap_pct"], 1), c["met"]), (-8, -10.0, False))

    def test_lower_is_better(self):
        c = compare("max_shared_wallets", 1, {"max_shared_wallets": 2})
        self.assertEqual((c["gap"], c["met"]), (-1, True))

    def test_no_target_set(self):
        c = compare("team_score", 72, {})
        self.assertEqual((c["target"], c["gap"], c["met"]), (None, None, None))


class TestTargetsInScore(_TempDir):
    def setUp(self):
        super().setUp()
        self.hist = os.path.join(self.dir, "hist.csv")
        pd.DataFrame([("19.06.2026", "Alice", "1001", 100, 20000),
                      ("18.06.2026", "Bob", "1002", 300, 60000)],
                     columns=["Date", "Name", "Operator_Id", "System Count", "Total Value"]
                     ).to_csv(self.hist, index=False)
        self.df = pd.DataFrame([("Alice", "1001", 100.0)] * 160 + [("Bob", "1002", 50.0)] * 80,
                               columns=["Cashier Name", OPERATOR, AMOUNT])

    def perf(self, scope, targets):
        return compute_performance(self.df, scope, active_date=ACTIVE, today=TODAY,
                                   history_path=self.hist, mistakes_by_c={}, targets=targets)

    def test_without_targets_history_average_is_used(self):
        r = self.perf("This Report", {})
        self.assertEqual((r.target_slips, r.target_value, r.target_per_hour), (200.0, 40000.0, 25))
        self.assertEqual(r.target_sources, {"slips": "history", "value": "history", "per_hour": "default"})

    def test_manager_targets_replace_defaults_and_change_scores(self):
        base = {x["name"]: x for x in self.perf("This Report", {}).rows}
        r = self.perf("This Report", {"cashier_daily_slips": 100, "slips_per_hour": 10})
        self.assertEqual((r.target_slips, r.target_value, r.target_per_hour), (100.0, 40000.0, 10.0))
        self.assertEqual(r.target_sources, {"slips": "manager", "value": "history", "per_hour": "manager"})
        bob = {x["name"]: x for x in r.rows}["Bob"]
        self.assertGreater(bob["score"], base["Bob"]["score"])   # easier targets → higher score
        self.assertEqual(bob["throughput"], bob["slips_per_hr"] / 10.0)

    def test_working_days(self):
        self.assertEqual(self.perf("This Report", {}).working_days, [TODAY])
        self.assertEqual(self.perf("This Week", {}).working_days,
                         [datetime.date(2026, 6, 18), datetime.date(2026, 6, 19), TODAY])


class TestProgress(TestTargetsInScore):
    def test_performance_progress(self):
        targets = {"team_daily_slips": 300, "min_cashier_score": 70, "max_error_rate": 5}
        r = self.perf("This Report", targets)
        items = {i["key"]: i for i in performance_progress(r, targets)}
        self.assertEqual(items["team_daily_slips"]["actual"], 240)       # 160 + 80, one day
        self.assertEqual((items["team_daily_slips"]["gap"], items["team_daily_slips"]["met"]), (-60, False))
        scores = {x["name"]: x["score"] for x in r.rows}
        self.assertEqual(items["min_cashier_score"]["actual"], min(scores.values()))
        self.assertEqual(items["min_cashier_score"]["who"],
                         sorted(n for n, s in scores.items() if s < 70))
        self.assertTrue(items["max_error_rate"]["met"])                  # no mistakes
        self.assertIsNone(items["team_score"]["met"])                    # no target set
        self.assertIn("history", items["cashier_daily_slips"]["note"])

    def test_cashiers_below_daily_slips_target(self):
        targets = {"cashier_daily_slips": 100}
        r = self.perf("This Report", targets)
        item = next(i for i in performance_progress(r, targets) if i["key"] == "cashier_daily_slips")
        self.assertEqual(item["who"], ["Bob"])                            # 80 < 100

    def test_integrity_progress(self):
        res = IntegrityResult(high_risk_count=2, suspicious_count=0, shared_wallet_count=1)
        items = {i["key"]: i for i in integrity_progress(res, {"max_high_risk_duplicates": 0})}
        self.assertEqual((items["max_high_risk_duplicates"]["actual"],
                          items["max_high_risk_duplicates"]["met"]), (2, False))
        self.assertIsNone(items["max_shared_wallets"]["met"])


if __name__ == "__main__":
    unittest.main()

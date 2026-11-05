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
from engine.performance import compute_performance
from engine.targets import (BY_KEY, TARGETS, TargetError, clean_targets, compare, effective,
                            load_targets, parse_value, performance_progress,
                            read_targets_file, save_targets)

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
            self.assertIn(t.kind, ("target", "rule"))
        self.assertEqual({t.key for t in TARGETS if t.in_score},
                         {"slips_per_hour", "max_carry_over_bags",
                          "proc360_min_cash_per_slip", "proc360_max_slips"})

    def test_defaults(self):
        self.assertEqual(effective({}, "slips_per_hour"), 25)
        self.assertEqual(effective({}, "max_carry_over_bags"), 0)
        self.assertEqual(effective({}, "proc360_min_cash_per_slip"), 10_000)
        self.assertEqual(effective({}, "proc360_max_slips"), 100)
        self.assertIsNone(effective({}, "team_score"))
        self.assertEqual(effective({"slips_per_hour": 22}, "slips_per_hour"), 22)


class TestParsing(unittest.TestCase):
    def test_blank_means_no_target(self):
        for raw in (None, "", "   "):
            self.assertIsNone(parse_value(BY_KEY["team_score"], raw))

    def test_euro_and_thousands_separators(self):
        self.assertEqual(parse_value(BY_KEY["proc360_min_cash_per_slip"], "€12,500"), 12500.0)
        self.assertEqual(parse_value(BY_KEY["slips_per_hour"], "22.5"), 22.5)

    def test_invalid_values(self):
        with self.assertRaises(ValueError):
            parse_value(BY_KEY["team_score"], "abc")
        with self.assertRaises(ValueError):
            parse_value(BY_KEY["max_carry_over_bags"], "-1")
        with self.assertRaises(ValueError):
            parse_value(BY_KEY["team_score"], "101")          # points are 0–100
        with self.assertRaises(ValueError):
            parse_value(BY_KEY["slips_per_hour"], "0")        # scoring targets must be > 0

    def test_zero_allowed_for_maximums(self):
        self.assertEqual(parse_value(BY_KEY["max_carry_over_bags"], "0"), 0.0)

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
        saved = save_targets({"team_score": "80", "slips_per_hour": "28", "min_cashier_score": ""},
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
        c = compare("team_score", 72, 80)
        self.assertEqual((c["gap"], round(c["gap_pct"], 1), c["met"]), (-8, -10.0, False))

    def test_lower_is_better(self):
        c = compare("max_carry_over_bags", 1, 2)
        self.assertEqual((c["gap"], c["met"]), (-1, True))

    def test_no_target_set(self):
        c = compare("team_score", 72, None)
        self.assertEqual((c["target"], c["gap"], c["met"]), (None, None, None))


def _report(rows):
    out = []
    for name, op, n, amount in rows:
        out += [(name, op, amount)] * n
    return pd.DataFrame(out, columns=["Cashier Name", OPERATOR, AMOUNT])


class TestProgress(unittest.TestCase):
    """Alice 200 slips (25/hr), Bob 100 slips (12.5/hr), one 8-hour day."""

    def perf(self, targets, bags=None):
        df = _report([("Alice", "1001", 200, 2500.0), ("Bob", "1002", 100, 2500.0)])
        return compute_performance(df, "This Report", active_date=ACTIVE, today=TODAY,
                                   history_path=os.devnull, mistakes_by_c={},
                                   targets=targets, bag_log=bags or {})

    def items(self, targets, bags=None):
        return {i["key"]: i for i in performance_progress(self.perf(targets, bags), targets)}

    def test_slips_per_hour_against_default(self):
        item = self.items({})["slips_per_hour"]
        self.assertEqual((item["actual"], item["target"], item["met"]), (18.75, 25, False))
        self.assertEqual(item["who"], ["Bob"])

    def test_team_and_lowest_score(self):
        items = self.items({"team_score": 80, "min_cashier_score": 70})
        self.assertEqual((items["team_score"]["actual"], items["team_score"]["met"]), (76, False))
        self.assertEqual(items["min_cashier_score"]["who"], ["Bob"])

    def test_no_target_set(self):
        self.assertIsNone(self.items({})["team_score"]["met"])

    def test_carry_over_progress(self):
        items = self.items({}, bags={ACTIVE: {"bags": 40, "carried_over": 3}})
        carry = items["max_carry_over_bags"]
        self.assertEqual((carry["actual"], carry["target"], carry["met"]), (3, 0, False))
        self.assertEqual(carry["who"], [ACTIVE])

    def test_no_bag_log_no_carry_item(self):
        self.assertNotIn("max_carry_over_bags", self.items({}))


if __name__ == "__main__":
    unittest.main()

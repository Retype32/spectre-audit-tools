"""
tests/test_engine_bags.py — the daily bag log. Files go to a temporary folder.
"""
import datetime
import os
import shutil
import tempfile
import unittest

import pandas as pd

from engine.bags import BagLogError, day_status, load_bag_log, save_bag_day


class TestBagLog(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.path = os.path.join(self.dir, "Bag_Log.csv")
        self.now = datetime.datetime(2026, 6, 20, 17, 0)

    def test_missing_file_is_empty(self):
        self.assertEqual(load_bag_log(self.path), {})

    def test_save_replace_and_order(self):
        save_bag_day("20.06.2026", 120, 4, self.path, now=self.now)
        save_bag_day("19.06.2026", 90, 0, self.path, now=self.now)
        save_bag_day("20.06.2026", 120, 0, self.path, now=self.now)     # correction
        self.assertEqual(load_bag_log(self.path), {
            "19.06.2026": {"bags": 90, "carried_over": 0},
            "20.06.2026": {"bags": 120, "carried_over": 0},
        })
        self.assertEqual(pd.read_csv(self.path, dtype=str)["Date"].tolist(),
                         ["19.06.2026", "20.06.2026"])
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_invalid_input(self):
        for args in (("2026-06-20", 10, 0), ("20.06.2026", -1, 0),
                     ("20.06.2026", 10, 11), ("20.06.2026", "ten", 0), ("20.06.2026", 2.5, 0)):
            with self.assertRaises(BagLogError):
                save_bag_day(*args, path=self.path)
        self.assertFalse(os.path.exists(self.path))

    def test_bad_rows_in_file_are_skipped(self):
        pd.DataFrame([("20.06.2026", "100", "0", ""), ("bad", "5", "0", ""),
                      ("21.06.2026", "x", "0", "")],
                     columns=["Date", "Bags In", "Carried Over", "Updated"]).to_csv(self.path, index=False)
        self.assertEqual(list(load_bag_log(self.path)), ["20.06.2026"])

    def test_day_status(self):
        self.assertIsNone(day_status(None))
        st = day_status({"bags": 80, "carried_over": 6}, max_carry_over=0)
        self.assertEqual((st["processed"], st["completion_pct"], st["cleared"]), (74, 92.5, False))
        self.assertTrue(day_status({"bags": 80, "carried_over": 6}, max_carry_over=10)["cleared"])
        self.assertEqual(day_status({"bags": 0, "carried_over": 0})["completion_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()

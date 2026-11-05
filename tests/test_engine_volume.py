"""
tests/test_engine_volume.py — monthly cash volume per cashier.

All names and figures are fictional. Everyone works 8-hour shifts.
"""
import os
import shutil
import tempfile
import unittest

import pandas as pd

from engine.volume import available_months, monthly_volume


class TestMonthlyVolume(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.hist = os.path.join(self.dir, "Performance_History.csv")
        rows = [
            # Alice: fast, average lodgements
            ("02.06.2026", "Alice", "1001", 240, 480000, "VMS"),
            ("03.06.2026", "Alice", "1001", 240, 480000, "VMS"),
            # Bob: slower, but bigger lodgements
            ("02.06.2026", "Bob", "1002", 160, 640000, "VMS"),
            # Bob on 360 one day, and an ISA day
            ("03.06.2026", "Bob", "1002", 45, 1500000, "VMS"),
            ("04.06.2026", "Bob", "1002", 100, 100000, "ISA"),
            # Another month, and a row with no format (counts as VMS)
            ("30.05.2026", "Alice", "1001", 200, 400000, ""),
        ]
        pd.DataFrame(rows, columns=["Date", "Name", "Operator_Id", "System Count",
                                    "Total Value", "Format"]).to_csv(self.hist, index=False)

    def vol(self, month="2026-06"):
        return monthly_volume(month, history_path=self.hist, targets={})

    def test_months(self):
        self.assertEqual(available_months(self.hist), ["2026-06", "2026-05"])

    def test_rates_and_ranking(self):
        data = self.vol()
        rows = {r["name"]: r for r in data["rows"]}
        self.assertEqual([r["name"] for r in data["rows"]], ["Bob", "Alice"])   # cash/hr
        alice, bob = rows["Alice"], rows["Bob"]
        self.assertEqual((alice["days"], alice["slips"], alice["cash"]), (2, 480, 960000.0))
        self.assertEqual((alice["cash_per_hour"], alice["slips_per_hour"], alice["cash_per_slip"]),
                         (60000.0, 30.0, 2000.0))
        self.assertEqual((bob["cash_per_hour"], bob["slips_per_hour"], bob["cash_per_slip"]),
                         (80000.0, 20.0, 4000.0))

    def test_why_compared_with_team(self):
        bob = next(r for r in self.vol()["rows"] if r["name"] == "Bob")
        # team: 640 slips, €1.6m, 24 hours → 26.7 slips/hr, €2,500/slip
        self.assertLess(bob["slips_per_hour_vs_team_pct"], 0)      # slower than the team
        self.assertAlmostEqual(bob["cash_per_slip_vs_team_pct"], 60.0)   # bigger lodgements

    def test_360_and_other_days_kept_out_of_rates(self):
        data = self.vol()
        bob = next(r for r in data["rows"] if r["name"] == "Bob")
        self.assertEqual((bob["days"], bob["days_360"], bob["cash_360"], bob["days_other"]),
                         (1, 1, 1500000.0, 1))
        self.assertEqual((data["team"]["days_360"], data["team"]["working_days"]), (1, 2))

    def test_missing_format_counts_as_vms(self):
        alice = self.vol("2026-05")["rows"][0]
        self.assertEqual((alice["name"], alice["days"]), ("Alice", 1))

    def test_no_history(self):
        data = monthly_volume("2026-06", history_path=os.path.join(self.dir, "none.csv"), targets={})
        self.assertEqual((data["rows"], data["team"]["cashiers"]), ([], 0))


if __name__ == "__main__":
    unittest.main()

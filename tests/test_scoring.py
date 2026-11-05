"""
tests/test_scoring.py — Unit tests for cashier performance scoring logic.

Imports directly from scoring.py (pure Python, no PySide6 dependency).

Run with:
    python -m pytest tests/
  or
    python -m unittest tests.test_scoring
"""
import unittest
from unittest import mock

import scoring
from scoring import grade as _grade, is_360_day, score_day, shift_hours as _shift_hours

# Fictional operator IDs used in place of the real ones from local_settings.json
_FAKE_TEN_HOUR_IDS = frozenset({"10001", "10002"})


# =============================================================================
class TestGradeBoundaries(unittest.TestCase):
    """Grade thresholds are hard business rules — any regression here matters."""

    def test_grade_A_at_90(self):
        self.assertEqual(_grade(90), "A")

    def test_grade_A_at_100(self):
        self.assertEqual(_grade(100), "A")

    def test_grade_B_at_89(self):
        self.assertEqual(_grade(89), "B")

    def test_grade_B_at_75(self):
        self.assertEqual(_grade(75), "B")

    def test_grade_C_at_74(self):
        self.assertEqual(_grade(74), "C")

    def test_grade_C_at_60(self):
        self.assertEqual(_grade(60), "C")

    def test_grade_D_at_59(self):
        self.assertEqual(_grade(59), "D")

    def test_grade_D_at_45(self):
        self.assertEqual(_grade(45), "D")

    def test_grade_F_at_44(self):
        self.assertEqual(_grade(44), "F")

    def test_grade_F_at_zero(self):
        self.assertEqual(_grade(0), "F")


class TestShiftHours(unittest.TestCase):
    """Configured operator IDs must map to 10-hour shifts; everyone else is 8."""

    def setUp(self):
        patcher = mock.patch.object(scoring, "_TEN_HOUR_OP_IDS", _FAKE_TEN_HOUR_IDS)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_first_configured_operator_is_10h(self):
        self.assertEqual(_shift_hours("10001"), 10)

    def test_second_configured_operator_is_10h(self):
        self.assertEqual(_shift_hours("10002"), 10)

    def test_standard_operator_is_8h(self):
        self.assertEqual(_shift_hours("12345"), 8)

    def test_empty_op_id_is_8h(self):
        self.assertEqual(_shift_hours(""), 8)

    def test_op_id_with_whitespace_is_10h(self):
        self.assertEqual(_shift_hours(" 10001 "), 10)


class TestScoreDay(unittest.TestCase):
    """One working day: slips per hour (50) + cash (10) + accuracy (20) + clean (10)."""

    def _score(self, slips, value, op_id="99999", mistakes=None, rate=25, cash_base=60_000.0):
        return score_day(slips, value, op_id, mistakes or [], rate, cash_base)["total"]

    def test_on_target_scores_90(self):
        # 8h × 25/hr = 200 slips → 50; cash at team average (€60k/hr) → 10; 20 + 10
        self.assertEqual(self._score(200, 480_000), 90.0)

    def test_slips_above_target_are_capped(self):
        self.assertEqual(self._score(300, 480_000), 90.0)

    def test_cash_above_team_average_is_capped(self):
        self.assertEqual(self._score(200, 2_000_000), 90.0)

    def test_zero_work_keeps_accuracy_only(self):
        # no slips, no cash → 0 + 0 + 20 + 10
        self.assertEqual(self._score(0, 0), 30.0)

    def test_half_slips_and_half_cash(self):
        # 100 slips = 50% → 25; €240k = 50% of team cash/hr → 5; + 30 → 60 (C)
        score = self._score(100, 240_000)
        self.assertEqual(score, 60.0)
        self.assertEqual(_grade(score), "C")

    def test_slips_count_more_than_cash(self):
        # Balanced (95% slips, full cash) beats all-slips/half-cash a little...
        balanced = self._score(190, 480_000)
        slips_only = self._score(200, 240_000)
        self.assertGreater(balanced, slips_only)
        # ...but a big slips gap always beats cash
        self.assertGreater(self._score(200, 240_000), self._score(140, 2_000_000))

    def test_no_team_cash_to_compare_gives_full_cash_points(self):
        self.assertEqual(score_day(200, 0, "99999", [], 25, 0)["cash_score"], 10.0)

    def test_lower_rate_target_on_cleared_day(self):
        # Team ran out of work at 15/hr: 120 slips over 8h meets that target
        self.assertEqual(score_day(120, 480_000, "99999", [], 15, 60_000)["rate_score"], 50.0)

    def test_duplicate_penalty_applied(self):
        m = {"type": "duplicate_slip", "points": 20, "date": "", "cashier": "", "notes": ""}
        # error rate 1/200: accuracy 19.9 + clean 9.95 + 60 = 89.85 − 20 = 69.85
        self.assertAlmostEqual(self._score(200, 480_000, mistakes=[m]), 69.85, delta=0.051)

    def test_penalty_floored_at_zero(self):
        m = {"type": "duplicate_slip", "points": 20, "date": "", "cashier": "", "notes": ""}
        self.assertEqual(self._score(0, 0, mistakes=[m] * 5), 0.0)

    @mock.patch.object(scoring, "_TEN_HOUR_OP_IDS", _FAKE_TEN_HOUR_IDS)
    def test_10h_shift_needs_250_slips(self):
        self.assertEqual(self._score(250, 600_000, op_id="10001"), 90.0)
        self.assertLess(self._score(200, 600_000, op_id="10001"), 90.0)

    def test_grade_derived_from_score(self):
        self.assertEqual(_grade(90), "A")
        self.assertEqual(_grade(78), "B")


class TestIs360Day(unittest.TestCase):
    def test_few_slips_and_huge_cash(self):
        self.assertTrue(is_360_day(45, 1_500_000))           # ~€33k per slip

    def test_regular_day(self):
        self.assertFalse(is_360_day(200, 500_000))           # €2.5k per slip

    def test_many_slips_never_360(self):
        self.assertFalse(is_360_day(150, 3_000_000))         # over 100 slips

    def test_no_slips(self):
        self.assertFalse(is_360_day(0, 1_000_000))

    def test_custom_thresholds(self):
        self.assertTrue(is_360_day(60, 400_000, min_cash_per_slip=5_000, max_slips=80))


if __name__ == "__main__":
    unittest.main()

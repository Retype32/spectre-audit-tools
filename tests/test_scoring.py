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
from scoring import grade as _grade, shift_hours as _shift_hours, score_one_session

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


class TestScoreCalculation(unittest.TestCase):
    """End-to-end score formula tests against the 6-component model."""

    def _score(self, slips, value, op_id="99999", mistakes=None,
               target_slips=200, target_value=50_000.0):
        result = score_one_session(
            slips, value, op_id, mistakes or [], target_slips, target_value
        )
        return result["total"]

    def test_perfect_single_session_scores_90(self):
        # Perfect on all 5 metric components; consistency is N/A for a single session
        # thr=25, val=20, slip=15, acc=20, clean=10, penalty=0 → base=90, total=90
        score = self._score(200, 50_000)
        self.assertEqual(score, 90.0)

    def test_score_capped_at_100(self):
        # Well above all targets — should not exceed 100
        score = self._score(600, 200_000)
        self.assertLessEqual(score, 100.0)

    def test_zero_transactions_scores_30(self):
        # 0 slips → throughput=0, value=0, slip=0, but error_rate=0 so acc+clean = 30
        score = self._score(0, 0)
        self.assertEqual(score, 30.0)

    def test_duplicate_slip_penalty_applied(self):
        # Perfect session minus one duplicate slip (−12); error_rate affects acc/clean slightly
        m = {"type": "duplicate_slip", "points": 12, "date": "", "cashier": "", "notes": ""}
        score = self._score(200, 50_000, mistakes=[m])
        self.assertEqual(score, 77.9)

    def test_two_mistakes_penalty(self):
        # error_rate = 2/200 = 0.01; acc=19.8, clean=9.9 → base=89.7 − 24 = 65.7
        m = {"type": "duplicate_slip", "points": 12, "date": "", "cashier": "", "notes": ""}
        score = self._score(200, 50_000, mistakes=[m, m])
        self.assertEqual(score, 65.7)

    def test_penalty_floored_at_zero(self):
        # Heavy penalties on a zero-score session cannot go negative
        m = {"type": "money_lost", "points": 15, "date": "", "cashier": "", "notes": ""}
        score = self._score(0, 0, mistakes=[m, m, m, m, m, m, m, m])
        self.assertEqual(score, 0.0)

    @mock.patch.object(scoring, "_TEN_HOUR_OP_IDS", _FAKE_TEN_HOUR_IDS)
    def test_10h_shift_operator_gets_perfect_score(self):
        # op 10001 → 10h shift; 250 slips = 25/hr = target → thr=25
        # val=20, slip=15 (250 vs target 200, capped), acc=20, clean=10 → 90
        score = self._score(250, 50_000, op_id="10001")
        self.assertEqual(score, 90.0)

    def test_throughput_capped_at_1_2x_target(self):
        # 8h shift; 240 slips = 30/hr = 1.2× target → thr capped at 25 (max)
        # slip_score = min(15, (240/200)*15) = 15 (capped), everything else max → 90
        score = self._score(240, 50_000)
        self.assertEqual(score, 90.0)

    def test_half_throughput_and_half_value_reduces_score(self):
        # 8h; 100 slips = 12.5/hr = 0.5 of target → thr=12.5
        # slip_score = min(15, (100/200)*15) = 7.5
        # val_score = min(20, (25000/50000)*20) = 10
        # acc=20, clean=10, penalty=0 → base = 12.5+10+7.5+20+10 = 60 → grade C
        score = self._score(100, 25_000)
        self.assertEqual(score, 60.0)
        self.assertEqual(_grade(score), "C")

    def test_grade_derived_from_score(self):
        # score 90 → A
        self.assertEqual(_grade(90), "A")
        # score 78 → B
        self.assertEqual(_grade(78), "B")


if __name__ == "__main__":
    unittest.main()

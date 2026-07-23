"""
tests/test_utils.py — Unit tests for load_db_map and extract_report_date.

These functions live in utils_core.py (no Qt dependency) so they can be
tested in any environment, including headless CI.

Run with:
    python -m pytest tests/
  or
    python -m unittest tests.test_utils
"""
import datetime
import os
import sys
import tempfile
import textwrap
import unittest
import unittest.mock as mock

import pandas as pd

# Bootstrap path so we can import utils_core without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils_core import load_db_map, extract_report_date


# =============================================================================
# Helpers
# =============================================================================

def _write_csv(path: str, content: str):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(textwrap.dedent(content).strip() + "\n")


def _df_with_date_col(col_name: str, date_value: str) -> pd.DataFrame:
    return pd.DataFrame({col_name: [date_value, date_value]})


# =============================================================================
class TestLoadDbMap(unittest.TestCase):
    """load_db_map() behaviour across valid, edge-case, and broken inputs."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._db  = os.path.join(self._tmp.name, "Database.csv")

    def tearDown(self):
        self._tmp.cleanup()

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_basic_mapping(self):
        _write_csv(self._db, """
            Number,Name
            1001,Alice
            1002,Bob
        """)
        result = load_db_map(self._db)
        self.assertEqual(result["1001"], "Alice")
        self.assertEqual(result["1002"], "Bob")

    def test_float_id_normalised(self):
        # pandas sometimes writes "1001.0" for integer columns
        _write_csv(self._db, """
            Number,Name
            1001.0,Alice
        """)
        result = load_db_map(self._db)
        self.assertIn("1001", result)
        self.assertNotIn("1001.0", result)

    def test_whitespace_stripped_from_ids(self):
        _write_csv(self._db, 'Number,Name\n" 1001 ",Alice\n')
        result = load_db_map(self._db)
        self.assertIn("1001", result)

    def test_empty_rows_skipped(self):
        _write_csv(self._db, """
            Number,Name
            1001,Alice
            ,
            1002,Bob
        """)
        result = load_db_map(self._db)
        self.assertEqual(len(result), 2)

    def test_large_file_loads(self):
        rows = "\n".join(f"{i},Cashier{i}" for i in range(1, 501))
        _write_csv(self._db, "Number,Name\n" + rows)
        result = load_db_map(self._db)
        self.assertEqual(len(result), 500)

    # ── Missing / broken file ─────────────────────────────────────────────────

    def test_missing_file_returns_empty_dict(self):
        result = load_db_map("/nonexistent/path/Database.csv")
        self.assertEqual(result, {})

    def test_missing_number_column_raises(self):
        _write_csv(self._db, """
            ID,Name
            1001,Alice
        """)
        with self.assertRaises(ValueError) as ctx:
            load_db_map(self._db)
        self.assertIn("Number", str(ctx.exception))

    def test_missing_name_column_raises(self):
        _write_csv(self._db, """
            Number,Fullname
            1001,Alice
        """)
        with self.assertRaises(ValueError) as ctx:
            load_db_map(self._db)
        self.assertIn("Name", str(ctx.exception))

    def test_completely_empty_csv_raises(self):
        _write_csv(self._db, "")
        with self.assertRaises(Exception):
            load_db_map(self._db)


# =============================================================================
class TestExtractReportDate(unittest.TestCase):
    """extract_report_date() handles every expected real-world date format."""

    # ── Known good formats ────────────────────────────────────────────────────

    def test_dd_slash_mm_slash_yyyy(self):
        df = _df_with_date_col("Processed Date", "15/06/2024")
        self.assertEqual(extract_report_date(df), "15.06.2024")

    def test_yyyy_dash_mm_dash_dd(self):
        df = _df_with_date_col("Processed Date", "2024-06-15")
        self.assertEqual(extract_report_date(df), "15.06.2024")

    def test_dd_dot_mm_dot_yyyy(self):
        df = _df_with_date_col("Processed Date", "15.06.2024")
        self.assertEqual(extract_report_date(df), "15.06.2024")

    def test_dd_dash_mm_dash_yyyy(self):
        df = _df_with_date_col("Date", "15-06-2024")
        self.assertEqual(extract_report_date(df), "15.06.2024")

    def test_datetime_string_extracts_date_only(self):
        # Some reports include a time component — we only want the date part
        df = _df_with_date_col("Processed Date", "15/06/2024 09:45:00")
        self.assertEqual(extract_report_date(df), "15.06.2024")

    def test_pandas_timestamp_column(self):
        df = pd.DataFrame({"Processed Date": pd.to_datetime(["2024-06-15"])})
        self.assertEqual(extract_report_date(df), "15.06.2024")

    def test_transaction_date_column(self):
        df = _df_with_date_col("Transaction Date", "20/01/2025")
        self.assertEqual(extract_report_date(df), "20.01.2025")

    def test_created_date_column(self):
        df = _df_with_date_col("Created Date", "01/12/2023")
        self.assertEqual(extract_report_date(df), "01.12.2023")

    def test_plain_date_column(self):
        df = _df_with_date_col("Date", "07/03/2024")
        self.assertEqual(extract_report_date(df), "07.03.2024")

    # ── Fallback behaviour ────────────────────────────────────────────────────

    def test_no_date_column_returns_today(self):
        df = pd.DataFrame({"Amount": [100, 200], "Operator": ["A", "B"]})
        result = extract_report_date(df)
        today = datetime.datetime.now().strftime("%d.%m.%Y")
        self.assertEqual(result, today)

    def test_all_nulls_in_date_column_returns_today(self):
        df = pd.DataFrame({"Processed Date": [None, None]})
        result = extract_report_date(df)
        today = datetime.datetime.now().strftime("%d.%m.%Y")
        self.assertEqual(result, today)

    def test_unparseable_date_falls_back_to_today(self):
        df = _df_with_date_col("Processed Date", "NOT_A_DATE")
        result = extract_report_date(df)
        today = datetime.datetime.now().strftime("%d.%m.%Y")
        self.assertEqual(result, today)

    # ── Column priority ───────────────────────────────────────────────────────

    def test_primary_col_takes_priority(self):
        df = pd.DataFrame({
            "Processed Date": ["15/06/2024"],
            "Date":           ["01/01/2000"],
        })
        # Primary column "Processed Date" should win over "Date"
        self.assertEqual(extract_report_date(df, "Processed Date"), "15.06.2024")

    def test_fallback_col_used_when_primary_missing(self):
        df = pd.DataFrame({"Date": ["07/03/2024"]})
        # No "Processed Date" column → falls back to "Date"
        self.assertEqual(extract_report_date(df, "Processed Date"), "07.03.2024")


if __name__ == "__main__":
    unittest.main()

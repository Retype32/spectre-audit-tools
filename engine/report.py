"""
engine/report.py — load and normalise a VMS or ISA transaction report.

Pure pandas, no Qt. Used by the Integrity Check page and by anything else
that needs a report in Spectre's standard shape (tests, scripts, the agent).
"""
import os
from dataclasses import dataclass, field

import pandas as pd

from config import AMOUNT, DATABASE_FILE, DATE_COL, LODGEMENT, OPERATOR, WALLET
from utils_core import extract_report_date, load_db_map

# ISA reports have a preamble; the real header row contains one of these.
ISA_HEADER_MARKERS = {"Container Seal", "Lodgement Number", "Seal"}
ISA_COLUMN_MAP = {"User": OPERATOR, "Seal": WALLET,
                  "Lodgement Number": LODGEMENT, "Counted": AMOUNT}
HEADER_SCAN_ROWS = 15

# Any column whose (lower-cased) name contains one of these is treated as a
# denomination count column and coerced to int.
DENOM_MARKERS = ['100', '50', '20', '10', '5', '2', '1', '0.5', '0.2']

MIN_AMOUNT = 1.0          # rows below this are dropped
EMPTY_WALLET = "[EMPTY]"
NO_LODGEMENT = "[N/A]"
CASHIER_NAME = "Cashier Name"


class ReportError(Exception):
    """A report could not be used. `level` is "error" or "warning".
    `report_date` is set if the date was read before the report failed."""

    def __init__(self, title, message, level="error", report_date=None):
        super().__init__(message)
        self.title = title
        self.message = message
        self.level = level
        self.report_date = report_date


@dataclass
class Report:
    df: pd.DataFrame          # cleaned rows, with a "Cashier Name" column
    report_date: str          # DD.MM.YYYY
    fmt: str                  # "VMS" or "ISA"
    denom_cols: list = field(default_factory=list)
    path: str = ""

    @property
    def filename(self):
        return os.path.basename(self.path)


def read_raw(path):
    """Read a .csv / .xlsx / .xls file exactly as the Integrity Check does."""
    if path.lower().endswith('.csv'):
        return pd.read_csv(path, encoding='utf-8', low_memory=False)
    return pd.read_excel(path)


def detect_format(raw_df):
    """Return (df, is_isa). ISA files get their real header row and VMS
    column names; anything else is returned as a copy, unchanged."""
    for i in range(min(HEADER_SCAN_ROWS, len(raw_df))):
        rv = [str(x).strip() for x in raw_df.iloc[i].values]
        if any(v in ISA_HEADER_MARKERS for v in rv):
            df = raw_df.iloc[i + 1:].copy()
            df.columns = raw_df.iloc[i].values
            return df.rename(columns=ISA_COLUMN_MAP), True
    return raw_df.copy(), False


def denomination_columns(df):
    return [c for c in df.columns
            if any(x in str(c).lower() for x in DENOM_MARKERS)]


def clean(df):
    """Drop unusable rows and normalise key columns. Returns (df, denom_cols)."""
    df = df.dropna(subset=[OPERATOR, AMOUNT])
    df[AMOUNT] = pd.to_numeric(df[AMOUNT], errors='coerce')
    df = df.dropna(subset=[AMOUNT]); df[AMOUNT] = df[AMOUNT].round(2)
    df = df[df[AMOUNT] >= MIN_AMOUNT]
    if df.empty:
        return df, []

    denoms = denomination_columns(df)
    for col in denoms:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    df[OPERATOR] = df[OPERATOR].astype(str).str.strip()
    if WALLET in df.columns:
        df[WALLET] = df[WALLET].astype(str).str.strip().replace(['nan', 'None', ''], EMPTY_WALLET)
    else:
        df[WALLET] = EMPTY_WALLET
    df[LODGEMENT] = df[LODGEMENT].astype(str).str.strip() if LODGEMENT in df.columns else NO_LODGEMENT
    return df, denoms


def load_report(path, cashier_map=None):
    """Load, validate and clean a report file.

    cashier_map: {operator_id: name}. Defaults to the configured Cashier
    Database. Raises ReportError if the file can't be used.
    """
    raw_df = read_raw(path)
    if raw_df.empty:
        raise ReportError("Error", "File is empty")

    df, is_isa = detect_format(raw_df)
    for col in (OPERATOR, AMOUNT):
        if col not in df.columns:
            raise ReportError("Missing Column", f"'{col}' not found")

    report_date = extract_report_date(df, date_col_primary=DATE_COL)

    df, denoms = clean(df)
    if df.empty:
        raise ReportError("No Data", "No valid data", level="warning",
                          report_date=report_date)

    if cashier_map is None:
        cashier_map = load_db_map(DATABASE_FILE)
    df[CASHIER_NAME] = df[OPERATOR].map(cashier_map).fillna(df[OPERATOR])

    return Report(df=df, report_date=report_date, fmt="ISA" if is_isa else "VMS",
                  denom_cols=denoms, path=path)


def summarise(report):
    """Headline numbers shown in the Integrity Check info row."""
    df = report.df
    return {
        "file":        report.filename,
        "format":      report.fmt,
        "date":        report.report_date,
        "rows":        len(df),
        "cashiers":    int(df[CASHIER_NAME].nunique()),
        "total_value": float(df[AMOUNT].sum()),
    }

"""
utils_core.py — Pure-Python helpers with NO Qt dependency.

These functions are safe to import in headless / test environments.
utils.py re-exports them for backwards compatibility.
"""
import datetime
import logging
import os

import pandas as pd


def load_db_map(database_file: str) -> dict:
    """Load Cashier ID -> Name map from a Database.csv path.

    Returns an empty dict if the file is missing.
    Raises ValueError if the file exists but is missing required columns.
    Logs a warning for individual rows whose ID cannot be normalised.
    """
    if not os.path.exists(database_file):
        logging.debug(f"load_db_map: database file not found at {database_file!r}")
        return {}

    try:
        db = pd.read_csv(database_file, dtype=str)
    except Exception as exc:
        logging.error(f"load_db_map: could not read {database_file!r}: {exc}")
        raise

    missing = [c for c in ('Number', 'Name') if c not in db.columns]
    if missing:
        msg = (
            f"load_db_map: {database_file!r} is missing required "
            f"column(s): {missing}.  Found: {list(db.columns)}"
        )
        logging.error(msg)
        raise ValueError(msg)

    db['Number'] = db['Number'].fillna('').str.strip()
    db['Name']   = db['Name'].fillna('').str.strip()
    db = db[(db['Number'] != '') & (db['Name'] != '')]

    out = {}
    for _, r in db.iterrows():
        n = r['Number']
        if n.endswith('.0'):
            n = n[:-2]
        try:
            n = str(int(float(n)))
        except ValueError:
            logging.warning(
                f"load_db_map: could not normalise ID {r['Number']!r} — kept as-is"
            )
        out[n] = r['Name']

    logging.debug(f"load_db_map: loaded {len(out)} cashier mappings")
    return out


_DATE_COLS = ['Processed Date', 'Date', 'Transaction Date', 'Created Date']
_DATE_FMTS = ['%d/%m/%Y', '%Y-%m-%d', '%d.%m.%Y', '%d-%m-%Y', '%m/%d/%Y']


def extract_report_date(df, date_col_primary: str = "Processed Date") -> str:
    """Extract a representative date string (DD.MM.YYYY) from a report dataframe.

    Tries the primary column first, then fallback column names, and a
    prioritised list of date formats.  Falls back to today's date and logs a
    warning so the fallback is visible in the log.
    """
    date_cols = [date_col_primary] + [c for c in _DATE_COLS if c != date_col_primary]

    for col in date_cols:
        if col not in df.columns:
            continue
        dates = df[col].dropna()
        if dates.empty:
            continue
        dv = dates.iloc[0]
        if isinstance(dv, str):
            raw = dv.split()[0]
            for fmt in _DATE_FMTS:
                try:
                    return datetime.datetime.strptime(raw, fmt).strftime("%d.%m.%Y")
                except ValueError:
                    continue
            logging.warning(
                f"extract_report_date: value {dv!r} in column {col!r} "
                f"did not match any known format {_DATE_FMTS}"
            )
        elif hasattr(dv, 'strftime'):
            return dv.strftime("%d.%m.%Y")

    fallback = datetime.datetime.now().strftime("%d.%m.%Y")
    logging.warning(
        f"extract_report_date: no parseable date column found "
        f"(tried {date_cols}).  Falling back to today: {fallback}"
    )
    return fallback

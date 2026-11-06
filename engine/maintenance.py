"""
engine/maintenance.py — one-off tidy-up of history files.

Before the blank-Operator-Id fix, a report with one blank Operator Id cell
was saved with IDs like "1001.0", and those cashiers' names fell back to the
ID because nothing matched the Cashier Database. tidy_history_ids() repairs
the saved files:

* IDs ending in ".0" become plain IDs ("1001.0" → "1001");
* a name that is really an operator ID is replaced by the cashier's name
  from the Cashier Database, when it's there.

Each file that changes is first copied to "<file>.bak-YYYYMMDD-HHMM".
Running it again changes nothing. Pure pandas, no Qt.
"""
import datetime
import glob
import logging
import os
import shutil

import pandas as pd

from config import (ALL_DISC_DB, CUSTOMER_DISC_DB, DATABASE_FILE, DISCREPANCY_DB_PATH,
                    DUPLICATE_VERDICTS_DB, MISTAKES_DB, OPERATOR, PERFORMANCE_HISTORY_DB)
from engine.report import normalise_id
from utils_core import load_db_map

# file → (columns holding IDs, columns holding cashier names)
CSV_FILES = {
    "performance": (PERFORMANCE_HISTORY_DB, ["Operator_Id"], ["Name"]),
    "mistakes":    (MISTAKES_DB, ["operator_id"], ["cashier"]),
    "all_disc":    (ALL_DISC_DB, ["Operator ID"], ["Cashier Name"]),
    "customer":    (CUSTOMER_DISC_DB, ["Customer_Id"], []),
    "verdicts":    (DUPLICATE_VERDICTS_DB, [], ["cashier"]),
}


def _fix_name(value, cashier_map):
    text = str(value).strip()
    if text.lower() in ("", "nan", "none"):
        return value
    as_id = normalise_id(text)
    return cashier_map.get(as_id, as_id)


def _fix_verdict_key(key):
    """'date|op|slip|amount' with op/slip like '1001.0' → plain IDs."""
    parts = str(key).split("|")
    if len(parts) != 4:
        return key
    parts[1], parts[2] = normalise_id(parts[1]), normalise_id(parts[2])
    return "|".join(parts)


def _count_changes(old, new):
    """Cells that differ, treating blank → blank as unchanged."""
    a = old.astype(object).where(old.notna(), None)
    b = new.astype(object).where(new.notna(), None)
    return sum(1 for x, y in zip(a, b) if x != y)


def _tidy_frame(df, id_cols, name_cols, cashier_map, verdict_keys=False):
    """Return (tidied copy, number of changed cells)."""
    out = df.copy()
    changed = 0
    for col in id_cols:
        if col in out.columns:
            new = out[col].map(lambda v: v if pd.isna(v) else normalise_id(v))
            changed += _count_changes(out[col], new)
            out[col] = new
    for col in name_cols:
        if col in out.columns:
            new = out[col].map(lambda v: v if pd.isna(v) else _fix_name(v, cashier_map))
            changed += _count_changes(out[col], new)
            out[col] = new
    if verdict_keys and "key" in out.columns:
        new = out["key"].map(lambda v: v if pd.isna(v) else _fix_verdict_key(v))
        changed += _count_changes(out["key"], new)
        out["key"] = new
    return out, changed


def _backup(path, stamp):
    dest = f"{path}.bak-{stamp}"
    shutil.copy2(path, dest)
    return dest


def tidy_history_ids(cashier_map=None, files=None, small_disc_dir=DISCREPANCY_DB_PATH, now=None):
    """Repair "1001.0"-style IDs and ID-as-name entries in the history files.

    files: {kind: path} overrides for CSV_FILES (used by tests).
    Returns one {"file", "changed", "backup"} dict per file that was changed.
    """
    if cashier_map is None:
        cashier_map = load_db_map(DATABASE_FILE)
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M")
    files = files or {}
    report = []

    for kind, (default_path, id_cols, name_cols) in CSV_FILES.items():
        path = files.get(kind, default_path)
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path, dtype=str)
            new, changed = _tidy_frame(df, id_cols, name_cols, cashier_map,
                                       verdict_keys=(kind == "verdicts"))
            if changed:
                backup = _backup(path, stamp)
                new.to_csv(path, index=False)
                report.append({"file": path, "changed": changed, "backup": backup})
        except Exception as e:
            logging.exception(f"tidy_history_ids: {path}")
            report.append({"file": path, "changed": 0, "backup": None, "error": str(e)})

    # Per-day small-discrepancy workbooks: Discrepancies Database/YYYY/MM/*.xlsx
    for path in sorted(glob.glob(os.path.join(small_disc_dir, "*", "*", "*.xlsx"))):
        try:
            df = pd.read_excel(path, dtype=str)
            new, changed = _tidy_frame(df, [OPERATOR], ["Cashier Name"], cashier_map)
            if changed:
                backup = _backup(path, stamp)
                new.to_excel(path, index=False)
                report.append({"file": path, "changed": changed, "backup": backup})
        except Exception as e:
            logging.exception(f"tidy_history_ids: {path}")
            report.append({"file": path, "changed": 0, "backup": None, "error": str(e)})

    logging.info(f"tidy_history_ids: {sum(r['changed'] for r in report)} cells in "
                 f"{len(report)} file(s)")
    return report

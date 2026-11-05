"""
engine/bags.py — the daily bag log: how many bags came in and how many were
carried over (not processed) to the next day.

Entered in the Bag Counter tab and kept in one shared file (config.BAG_LOG_DB),
one row per date. A day is "cleared" when the carry-over is within the
allowed number (Settings → Team Targets; 0 when not set). On a cleared day
the team ran out of work, so the slips-per-hour target is lowered to the pace
the team actually managed (see engine.performance).

Pure Python, no Qt.
"""
import datetime
import os

import pandas as pd

from config import BAG_LOG_DB

DATE_FMT = "%d.%m.%Y"
COLUMNS = ["Date", "Bags In", "Carried Over", "Updated"]


class BagLogError(ValueError):
    pass


def _to_count(raw, label):
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        raise BagLogError(f"{label}: '{raw}' is not a number")
    if value < 0 or not value.is_integer():
        raise BagLogError(f"{label}: must be a whole number, 0 or more")
    return int(value)


def load_bag_log(path=BAG_LOG_DB):
    """{"DD.MM.YYYY": {"bags": int, "carried_over": int}} — {} if no file.
    Rows that can't be read are skipped."""
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path, dtype=str)
    out = {}
    for _, row in df.iterrows():
        date = str(row.get("Date", "")).strip()
        try:
            datetime.datetime.strptime(date, DATE_FMT)
            out[date] = {"bags": _to_count(row.get("Bags In"), "Bags In"),
                         "carried_over": _to_count(row.get("Carried Over"), "Carried Over")}
        except (ValueError, BagLogError):
            continue
    return out


def save_bag_day(date_str, bags, carried_over, path=BAG_LOG_DB, now=None):
    """Record one day's bags (replacing that date if it already exists).
    Raises BagLogError for invalid input."""
    try:
        datetime.datetime.strptime(str(date_str).strip(), DATE_FMT)
    except ValueError:
        raise BagLogError(f"Date: '{date_str}' is not DD.MM.YYYY")
    bags = _to_count(bags, "Bags in")
    carried_over = _to_count(carried_over, "Carried over")
    if carried_over > bags:
        raise BagLogError("Carried over can't be more than the bags that came in")
    if now is None:
        now = datetime.datetime.now()

    new_row = {"Date": str(date_str).strip(), "Bags In": bags,
               "Carried Over": carried_over, "Updated": now.strftime("%Y-%m-%d %H:%M")}
    if os.path.exists(path):
        df = pd.read_csv(path, dtype=str)
        df = df[df["Date"].astype(str).str.strip() != new_row["Date"]]
        df = pd.concat([df, pd.DataFrame([new_row]).astype(str)], ignore_index=True)
    else:
        df = pd.DataFrame([new_row], columns=COLUMNS).astype(str)
    df["_d"] = pd.to_datetime(df["Date"], format=DATE_FMT, errors="coerce")
    df = df.sort_values("_d").drop(columns="_d")

    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = f"{path}.tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)
    return {"bags": bags, "carried_over": carried_over}


def day_status(entry, max_carry_over=0):
    """Completion figures for one bag-log entry (or None if not logged)."""
    if entry is None:
        return None
    bags, carried = entry["bags"], entry["carried_over"]
    processed = bags - carried
    return {
        "bags": bags,
        "carried_over": carried,
        "processed": processed,
        "completion_pct": (processed / bags * 100) if bags else 100.0,
        "cleared": carried <= max_carry_over,
    }

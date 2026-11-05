"""
engine/volume.py — monthly cash volume per cashier.

Built from Performance_History.csv (one row per cashier per report date,
written by every Integrity Check). Answers "who handles the most cash per
hour this month, and why?":

    cash per hour = slips per hour × cash per slip

so a high cash rate comes from working faster (more slips per hour), from
handling bigger lodgements (more cash per slip), or both. Each cashier is
compared with the team on both.

360 processing days and non-VMS days are listed separately and left out of
the rates, so one huge 360 day doesn't distort a cashier's month.

Pure pandas, no Qt.
"""
import datetime
import os

import pandas as pd

from config import PERFORMANCE_HISTORY_DB
from engine.targets import effective, load_targets
from scoring import is_360_day, shift_hours

DATE_FMT = "%d.%m.%Y"


def _history(history_path):
    if not os.path.exists(history_path):
        empty = pd.DataFrame(columns=["Date", "Name", "Operator_Id", "System Count",
                                      "Total Value", "Format"])
        empty["_date"] = pd.to_datetime(pd.Series([], dtype=str))
        return empty
    h = pd.read_csv(history_path, dtype=str)
    for col in ("Name", "Operator_Id", "Format"):
        if col not in h.columns:
            h[col] = ""
    h["Name"] = h["Name"].fillna("").str.strip()
    h["Operator_Id"] = h["Operator_Id"].fillna("").str.strip()
    h["Format"] = h["Format"].fillna("").str.strip().str.upper().replace({"": "VMS", "NAN": "VMS"})
    h["System Count"] = pd.to_numeric(h.get("System Count"), errors="coerce").fillna(0)
    h["Total Value"] = pd.to_numeric(h.get("Total Value"), errors="coerce").fillna(0.0)
    h["_date"] = pd.to_datetime(h.get("Date"), format=DATE_FMT, errors="coerce")
    return h[(h["Name"] != "") & (h["Name"].str.lower() != "nan") & h["_date"].notna()]


def available_months(history_path=PERFORMANCE_HISTORY_DB):
    """Months with history, newest first, as "YYYY-MM"."""
    h = _history(history_path)
    return sorted({d.strftime("%Y-%m") for d in h["_date"]}, reverse=True)


def _pct_vs(value, team):
    return (value / team - 1) * 100 if team else None


def monthly_volume(month, history_path=PERFORMANCE_HISTORY_DB, targets=None):
    """Cash volume per cashier for `month` ("YYYY-MM").

    Returns {"month", "rows": [...], "team": {...}}. Rows are sorted by cash
    per hour, highest first. Rates cover regular VMS days only.
    """
    if targets is None:
        targets = load_targets()
    min_cps = effective(targets, "proc360_min_cash_per_slip")
    max_360 = effective(targets, "proc360_max_slips")

    h = _history(history_path)
    h = h[h["_date"].dt.strftime("%Y-%m") == month]

    cashiers = {}
    team = {"slips": 0.0, "cash": 0.0, "hours": 0.0, "dates": set(),
            "days_360": 0, "cash_360": 0.0, "days_other": 0}
    for name, grp in h.groupby("Name"):
        ops = grp["Operator_Id"][~grp["Operator_Id"].str.lower().isin(["", "nan", "none"])]
        op_id = ops.mode().iloc[0] if not ops.empty else ""
        hours = shift_hours(op_id)
        c = {"name": name, "op_id": op_id, "shift_hours": hours, "days": 0, "slips": 0,
             "cash": 0.0, "hours": 0, "days_360": 0, "slips_360": 0, "cash_360": 0.0,
             "days_other": 0, "cash_other": 0.0}
        for _, r in grp.iterrows():
            slips, cash = int(r["System Count"]), float(r["Total Value"])
            if r["Format"] != "VMS":
                c["days_other"] += 1; c["cash_other"] += cash
                team["days_other"] += 1
            elif is_360_day(slips, cash, min_cps, max_360):
                c["days_360"] += 1; c["slips_360"] += slips; c["cash_360"] += cash
                team["days_360"] += 1; team["cash_360"] += cash
            else:
                c["days"] += 1; c["slips"] += slips; c["cash"] += cash; c["hours"] += hours
                team["slips"] += slips; team["cash"] += cash; team["hours"] += hours
                team["dates"].add(r["_date"].date())
        cashiers[name] = c

    t_sph = team["slips"] / team["hours"] if team["hours"] else 0.0
    t_cps = team["cash"] / team["slips"] if team["slips"] else 0.0
    t_cph = team["cash"] / team["hours"] if team["hours"] else 0.0

    rows = []
    for c in cashiers.values():
        sph = c["slips"] / c["hours"] if c["hours"] else 0.0
        cps = c["cash"] / c["slips"] if c["slips"] else 0.0
        cph = c["cash"] / c["hours"] if c["hours"] else 0.0
        c.update({
            "cash_per_day": c["cash"] / c["days"] if c["days"] else 0.0,
            "cash_per_hour": cph, "cash_per_slip": cps, "slips_per_hour": sph,
            "cash_per_hour_vs_team_pct": _pct_vs(cph, t_cph) if c["days"] else None,
            "slips_per_hour_vs_team_pct": _pct_vs(sph, t_sph) if c["days"] else None,
            "cash_per_slip_vs_team_pct": _pct_vs(cps, t_cps) if c["days"] else None,
        })
        rows.append(c)
    rows.sort(key=lambda r: (r["days"] > 0, r["cash_per_hour"]), reverse=True)

    return {
        "month": month,
        "rows": rows,
        "team": {
            "cashiers": sum(1 for r in rows if r["days"]),
            "working_days": len(team["dates"]),
            "slips": int(team["slips"]), "cash": team["cash"],
            "cash_per_hour": t_cph, "cash_per_slip": t_cps, "slips_per_hour": t_sph,
            "days_360": team["days_360"], "cash_360": team["cash_360"],
            "days_other": team["days_other"],
        },
    }


def current_month(today=None):
    return (today or datetime.date.today()).strftime("%Y-%m")

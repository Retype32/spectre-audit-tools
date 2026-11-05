"""
engine/performance.py — cashier performance scores for a chosen period.

Pure pandas, no Qt. Used by the Cashier Performance tab, the tests and the
agent, so everyone gets the same numbers. The per-day scoring rules live in
scoring.py; this module decides which days count and what each day's
targets are:

* Each cashier's working day comes from the loaded report (the session) and,
  for multi-day periods, from Performance_History.csv.
* 360 processing days (few slips, very high cash per slip) and non-VMS days
  (e.g. ISA) are not scored and don't affect the team's averages. They are
  listed in PerformanceResult.unscored.
* Slips-per-hour target: the manager's target (25 by default). On a day when
  the bag log shows every bag was cleared, it is lowered to the pace the team
  actually managed, because there was no more work.
* Cash is compared with the team's average cash per hour on the same day.

A "row" is one cashier's result for the period, as a plain dict:
    name, op_id, txn, value, avg_val, slips_per_hr, throughput (share of
    slip target met), accuracy, consistency, score, grade, breakdown,
    mistakes, penalty, mistakes_list, sessions, days_360, days_other,
    period_base and orphan_penalty (multi-day scopes only)
"""
import datetime
import logging
import os
from dataclasses import dataclass, field

import pandas as pd

from config import AMOUNT, MISTAKE_TYPES, MISTAKES_DB, OPERATOR, PERFORMANCE_HISTORY_DB
from engine.bags import day_status, load_bag_log
from engine.targets import effective, load_targets
from scoring import (
    _RECENCY, _W_ACCURACY, _W_CLEAN_RATIO, SCOPES, consistency_score, grade, is_360_day,
    mistakes_by_cashier, recency_weighted_avg, score_day, shift_hours,
)

SESSION_SCOPE = "This Report"
DATE_FMT = "%d.%m.%Y"
SCORED_FORMAT = "VMS"     # the slips-per-hour target applies to VMS work only


@dataclass
class PerformanceResult:
    rows: list = field(default_factory=list)       # one dict per scored cashier
    scope: str = SESSION_SCOPE
    target_per_hour: float = 25.0                   # standard slips-per-hour target
    target_sources: dict = field(default_factory=dict)   # "manager" or "default"
    working_days: list = field(default_factory=list)     # dates with scored work
    days: list = field(default_factory=list)        # per-date team figures (see _day_info)
    unscored: list = field(default_factory=list)    # 360 / non-VMS cashier-days
    rules: dict = field(default_factory=dict)       # 360 and carry-over settings used


def scope_cutoff(scope, today):
    """First date included in `scope`, or None for no limit."""
    if scope == "Today":
        return today
    if scope == "This Week":
        return today - datetime.timedelta(days=7)
    if scope == "This Month":
        return datetime.date(today.year, today.month, 1)
    if scope == "3 Months":
        return today - datetime.timedelta(days=90)
    if scope == "6 Months":
        return today - datetime.timedelta(days=180)
    if scope == "12 Months":
        return today - datetime.timedelta(days=365)
    return None


def _parse_date(text):
    try:
        return datetime.datetime.strptime(str(text).strip(), DATE_FMT).date()
    except (TypeError, ValueError):
        return None


def _fmt_of(raw):
    text = str(raw).strip().upper() if raw is not None else ""
    return SCORED_FORMAT if text in ("", "NAN", "NONE") else text


def _collect_entries(df, scope, active_date, today, history_path, report_fmt, cutoff):
    """All cashier-days in the period: [{name, date, slips, value, fmt}], and
    {cashier: operator id}."""
    sess_date = _parse_date(active_date) or today
    ops, entries = {}, []

    if cutoff is None or sess_date >= cutoff:
        for name, grp in df.groupby("Cashier Name"):
            n = str(name)
            if OPERATOR in grp.columns:
                op = grp[OPERATOR].mode()
                ops[n] = str(op.iloc[0]).strip() if not op.empty else ""
            entries.append({
                "name": n, "date": sess_date, "slips": len(grp),
                "value": float(grp[AMOUNT].sum()) if AMOUNT in df.columns else 0.0,
                "fmt": _fmt_of(report_fmt),
            })

    if scope != SESSION_SCOPE and os.path.exists(history_path):
        try:
            hist = pd.read_csv(history_path, dtype=str)
        except Exception:
            logging.exception("compute: loading history")   # score the report alone
            hist = pd.DataFrame()
        if "Name" in hist.columns and "System Count" in hist.columns:
            hist["System Count"] = pd.to_numeric(hist["System Count"], errors="coerce").fillna(0)
            has_val = "Total Value" in hist.columns
            if has_val:
                hist["Total Value"] = pd.to_numeric(hist["Total Value"], errors="coerce").fillna(0)
            for _, row in hist.iterrows():
                n = str(row.get("Name", "")).strip()
                d = _parse_date(row.get("Date", ""))
                if not n or n.lower() == "nan" or d is None:
                    continue
                fmt = _fmt_of(row.get("Format"))
                if active_date and d == sess_date and fmt == _fmt_of(report_fmt):
                    continue  # the loaded report already covers this day
                if cutoff is not None and d < cutoff:
                    continue
                if n not in ops:
                    op = str(row.get("Operator_Id", "")).strip()
                    if op and op.lower() not in ("nan", "none"):
                        ops[n] = op
                entries.append({
                    "name": n, "date": d, "slips": int(row.get("System Count", 0)),
                    "value": float(row.get("Total Value", 0)) if has_val else 0.0,
                    "fmt": fmt,
                })
    return entries, ops


def compute_performance(df, scope, active_date=None, today=None,
                        history_path=PERFORMANCE_HISTORY_DB, mistakes_by_c=None,
                        targets=None, report_fmt=SCORED_FORMAT, bag_log=None):
    """Score every cashier for `scope` (one of scoring.SCOPES).

    df:            the loaded report (needs "Cashier Name")
    active_date:   that report's date (DD.MM.YYYY); report_fmt: "VMS" or "ISA"
    mistakes_by_c: {cashier: [mistake, ...]}; read from the mistake files if None
    targets:       manager targets/rules (engine.targets); shared file if None
    bag_log:       {date: {bags, carried_over}} (engine.bags); shared file if None

    Returns a PerformanceResult, or None if the report has no cashier column.
    """
    if "Cashier Name" not in df.columns:
        return None
    if today is None:
        today = datetime.date.today()
    if targets is None:
        targets = load_targets()
    if bag_log is None:
        bag_log = load_bag_log()

    session_only = (scope == SESSION_SCOPE)
    cutoff = scope_cutoff(scope, today)
    rate_std = float(effective(targets, "slips_per_hour"))
    max_carry = effective(targets, "max_carry_over_bags")
    min_cps = effective(targets, "proc360_min_cash_per_slip")
    max_360 = effective(targets, "proc360_max_slips")
    rules = {"min_cash_per_slip_360": min_cps, "max_slips_360": max_360,
             "max_carry_over_bags": max_carry}

    entries, ops = _collect_entries(df, scope, active_date, today, history_path,
                                    report_fmt, cutoff)

    # ── Sort cashier-days into scored / 360 / other formats ──────────────
    regular, unscored = [], []
    for e in entries:
        if e["fmt"] != SCORED_FORMAT:
            e["kind"] = "other"
        elif is_360_day(e["slips"], e["value"], min_cps, max_360):
            e["kind"] = "360"
        else:
            e["kind"] = "regular"
        (regular if e["kind"] == "regular" else unscored).append(e)

    # ── Team figures per date (regular cashiers only) ────────────────────
    per_date = {}
    for e in regular:
        hours = shift_hours(ops.get(e["name"], ""))
        t = per_date.setdefault(e["date"], {"slips": 0, "value": 0.0, "hours": 0, "names": set()})
        t["slips"] += e["slips"]; t["value"] += e["value"]; t["hours"] += hours
        t["names"].add(e["name"])

    # Days to report: every date with scored work, plus logged bag days in the period
    sess_date = _parse_date(active_date) or today
    day_dates = set(per_date)
    for ds in bag_log:
        d = _parse_date(ds)
        if d is None:
            continue
        in_period = (d == sess_date) if session_only else (
            (cutoff is None or d >= cutoff) and d <= today)
        if in_period:
            day_dates.add(d)

    days = {}
    for d in sorted(day_dates):
        t = per_date.get(d)
        status = day_status(bag_log.get(d.strftime(DATE_FMT)), max_carry)
        achieved = (t["slips"] / t["hours"]) if t and t["hours"] else None
        cleared = bool(status and status["cleared"])
        rate_target = min(rate_std, achieved) if (cleared and achieved) else rate_std
        days[d] = {
            "date": d.strftime(DATE_FMT),
            "regular_cashiers": len(t["names"]) if t else 0,
            "slips": t["slips"] if t else 0,
            "value": t["value"] if t else 0.0,
            "hours": t["hours"] if t else 0,
            "achieved_rate": achieved,
            "rate_target": rate_target,
            "cash_per_hour_baseline": (t["value"] / t["hours"]) if t and t["hours"] else None,
            "bags": status["bags"] if status else None,
            "carried_over": status["carried_over"] if status else None,
            "completion_pct": status["completion_pct"] if status else None,
            "cleared": status["cleared"] if status else None,
        }

    # ── Mistakes ──────────────────────────────────────────────────────────
    if mistakes_by_c is None:
        mistakes_by_c = mistakes_by_cashier(cutoff)

    # ── Score each cashier ────────────────────────────────────────────────
    by_cashier = {}
    for e in regular:
        by_cashier.setdefault(e["name"], []).append(e)
    excluded = {}
    for e in unscored:
        k = excluded.setdefault(e["name"], {"360": 0, "other": 0})
        k[e["kind"]] += 1

    raw_rows = []
    for name in sorted(by_cashier):
        op_id = ops.get(name, "")
        hours = shift_hours(op_id)
        days_worked = sorted(by_cashier[name], key=lambda x: x["date"])
        cashier_mistakes = mistakes_by_c.get(name, [])
        if session_only:
            cashier_mistakes = [m for m in cashier_mistakes
                                if active_date and m["date"] == active_date]
        by_date_m = {}
        for m in cashier_mistakes:
            by_date_m.setdefault(m["date"], []).append(m)

        daily, dated = [], []
        total_slips = total_value = expected_slips = 0.0
        for e in days_worked:
            info = days[e["date"]]
            day_m = by_date_m.get(e["date"].strftime(DATE_FMT), [])
            sc = score_day(e["slips"], e["value"], op_id, day_m,
                           info["rate_target"], info["cash_per_hour_baseline"])
            daily.append(sc)
            dated.append((e["date"], sc["total"]))
            total_slips += e["slips"]; total_value += e["value"]
            expected_slips += info["rate_target"] * hours

        scored_dates = {e["date"].strftime(DATE_FMT) for e in days_worked}
        orphans = [m for m in cashier_mistakes if m["date"] not in scored_dates]
        orphan_penalty = sum(m["points"] for m in orphans)
        sessions = len(daily)
        slips_per_hr = total_slips / (hours * sessions) if hours and sessions else 0.0
        throughput = total_slips / expected_slips if expected_slips else 0.0
        total_penalty = sum(m["points"] for m in cashier_mistakes)

        row = {
            "name": name, "op_id": op_id, "txn": int(total_slips), "value": total_value,
            "avg_val": total_value / total_slips if total_slips else 0.0,
            "slips_per_hr": round(slips_per_hr, 2), "throughput": throughput,
            "mistakes": len(cashier_mistakes), "penalty": total_penalty,
            "mistakes_list": cashier_mistakes, "sessions": sessions,
            "days_360": excluded.get(name, {}).get("360", 0),
            "days_other": excluded.get(name, {}).get("other", 0),
        }

        if session_only:
            sc = daily[0]
            sc["consistency"] = None  # explicitly N/A
            row.update({
                "accuracy": sc["acc_score"], "consistency": None,
                "score": int(round(sc["total"])), "grade": grade(sc["total"]),
                "breakdown": sc,
            })
        else:
            daily_totals = [sc["total"] for sc in daily]
            cons = consistency_score(daily_totals)
            if scope in _RECENCY:
                period_base = recency_weighted_avg(dated, scope, today)
            else:
                period_base = sum(daily_totals) / len(daily_totals)
            final_score = max(0.0, min(100.0, period_base + cons - orphan_penalty))

            per_err = len(cashier_mistakes) / total_slips if total_slips else 0.0
            d_rate = round(sum(sc["rate_score"] for sc in daily) / sessions, 1)
            d_cash = round(sum(sc["cash_score"] for sc in daily) / sessions, 1)
            d_acc = round(max(0.0, (1.0 - min(per_err, 1.0)) * _W_ACCURACY), 1)
            d_clean = round(max(0.0, (1.0 - min(per_err, 1.0)) * _W_CLEAN_RATIO), 1)
            breakdown = {
                "rate_score": d_rate, "cash_score": d_cash,
                "acc_score": d_acc, "clean_score": d_clean, "consistency": cons,
                "penalty": total_penalty, "base": round(d_rate + d_cash + d_acc + d_clean, 1),
                "total": round(final_score, 1), "slips_per_hr": row["slips_per_hr"],
                "cash_per_hr": round(total_value / (hours * sessions), 2) if hours else 0.0,
                "rate_target": round(expected_slips / (hours * sessions), 2) if hours else 0.0,
                "mistake_count": len(cashier_mistakes),
            }
            row.update({
                "accuracy": d_acc, "consistency": cons,
                "score": int(round(final_score)), "grade": grade(final_score),
                "breakdown": breakdown, "period_base": round(period_base, 1),
                "orphan_penalty": orphan_penalty,
            })
        raw_rows.append(row)

    unscored_list = sorted(
        ({"name": e["name"], "date": e["date"].strftime(DATE_FMT),
          "kind": e["kind"], "format": e["fmt"], "slips": e["slips"], "value": e["value"],
          "cash_per_slip": e["value"] / e["slips"] if e["slips"] else 0.0}
         for e in unscored),
        key=lambda x: (_parse_date(x["date"]), x["name"]))

    return PerformanceResult(
        rows=raw_rows, scope=scope, target_per_hour=rate_std,
        target_sources={"per_hour": "manager" if targets.get("slips_per_hour") else "default"},
        working_days=sorted(per_date), days=[days[d] for d in sorted(days)],
        unscored=unscored_list, rules=rules)


def team_summary(rows):
    """Team-level totals shown above the cashier list. `rows` must not be empty."""
    grades    = [r["grade"] for r in rows]
    avg_score = sum(r["score"] for r in rows) / len(rows)
    return {
        "cashiers":       len(rows),
        "total_txn":      sum(r["txn"] for r in rows),
        "total_value":    sum(r["value"] for r in rows),
        "avg_score":      avg_score,
        "team_score":     int(avg_score),
        "team_grade":     grade(int(avg_score)),
        "avg_rate":       sum(r["slips_per_hr"] for r in rows) / len(rows),
        "total_mistakes": sum(r["mistakes"] for r in rows),
        "total_penalty":  sum(r["penalty"] for r in rows),
        "grade_counts":   {g: grades.count(g) for g in "ABCDF"},
    }


def sort_rows(rows, key="score", ascending=False):
    """Order rows the way the Cashier Performance list does."""
    reverse = not ascending
    if key == "name":
        return sorted(rows, key=lambda r: str(r.get("name", "")).lower(), reverse=reverse)
    if key == "accuracy":
        return sorted(rows, key=lambda r: r.get("accuracy") or 0, reverse=reverse)
    if key == "consistency":
        return sorted(rows, key=lambda r: r.get("consistency") or 0, reverse=reverse)
    if key == "mistakes":
        return sorted(rows, key=lambda r: r.get("mistakes", 0), reverse=reverse)
    return sorted(rows, key=lambda r: r.get(key, 0), reverse=reverse)


def log_mistake(date_str, cashier, type_key, notes="", db_path=MISTAKES_DB, now=None):
    """Append one manually logged mistake to the mistakes file. Raises on failure."""
    if now is None:
        now = datetime.datetime.now()
    new_row = {
        "date":            date_str,
        "cashier":         cashier,
        "operator_id":     "",
        "type":            type_key,
        "severity_points": MISTAKE_TYPES[type_key]["points"],
        "notes":           notes,
        "logged_at":       now.strftime("%Y-%m-%d %H:%M"),
    }
    if os.path.exists(db_path):
        mdf = pd.read_csv(db_path, dtype=str)
    else:
        mdf = pd.DataFrame(columns=list(new_row.keys()))
    mdf = pd.concat([mdf, pd.DataFrame([new_row])], ignore_index=True)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    mdf.to_csv(db_path, index=False)


__all__ = ["SCOPES", "PerformanceResult", "scope_cutoff", "compute_performance",
           "team_summary", "sort_rows", "log_mistake"]

"""
engine/performance.py — cashier performance scores for a chosen period.

Pure pandas, no Qt. Moved from the Cashier Performance page so the page,
tests and the agent all use the same calculation. The scoring rules
themselves (components, weights, penalties, targets) live in scoring.py.

A "row" is one cashier's result for the period, as a plain dict:
    name, op_id, txn, value, avg_val, slips_per_hr, throughput, accuracy,
    consistency, score, grade, breakdown (component scores), mistakes,
    penalty, mistakes_list, sessions, period_base (multi-day scopes only)
"""
import datetime
import logging
import os
from dataclasses import dataclass, field

import pandas as pd

from config import AMOUNT, MISTAKE_TYPES, MISTAKES_DB, OPERATOR, PERFORMANCE_HISTORY_DB
from scoring import (
    _RECENCY, _TARGET_PER_HOUR, _W_ACCURACY, _W_CLEAN_RATIO, _W_SLIPS,
    _W_THROUGHPUT, _W_VALUE, SCOPES, compute_targets, consistency_score, grade,
    mistakes_by_cashier, recency_weighted_avg, score_one_session, shift_hours,
)

SESSION_SCOPE = "This Report"
DATE_FMT = "%d.%m.%Y"


@dataclass
class PerformanceResult:
    rows: list = field(default_factory=list)   # one dict per cashier
    target_slips: float = 0.0                  # daily targets (historical average)
    target_value: float = 0.0
    scope: str = SESSION_SCOPE


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


def compute_performance(df, scope, active_date=None, today=None,
                        history_path=PERFORMANCE_HISTORY_DB, mistakes_by_c=None):
    """Score every cashier for `scope` (one of scoring.SCOPES).

    df:            the loaded report (needs "Cashier Name")
    active_date:   that report's date (DD.MM.YYYY)
    mistakes_by_c: {cashier: [mistake, ...]}; read from the mistake files if None

    Returns a PerformanceResult, or None if the report has no cashier column.
    """
    if today is None:
        today = datetime.date.today()
    session_only = (scope == SESSION_SCOPE)
    cutoff       = scope_cutoff(scope, today)

    if "Cashier Name" not in df.columns:
        return None

    # ── Session data ──────────────────────────────────────────
    session_txn:    dict = {}
    session_val:    dict = {}
    cashier_op_ids: dict = {}

    for name, grp in df.groupby("Cashier Name"):
        n = str(name)
        session_txn[n] = len(grp)
        session_val[n] = float(grp[AMOUNT].sum()) if AMOUNT in df.columns else 0.0
        if OPERATOR in grp.columns:
            op = grp[OPERATOR].mode()
            cashier_op_ids[n] = str(op.iloc[0]).strip() if not op.empty else ""

    all_cashiers = set(session_txn.keys())

    # ── Historical data ───────────────────────────────────────
    # hist_daily: {cashier: [(date_obj_or_None, slips, value), ...]}
    hist_daily: dict = {}
    hist_df    = None

    if not session_only:
        try:
            if os.path.exists(history_path):
                hist_df = pd.read_csv(history_path, dtype=str)
                if "Name" in hist_df.columns and "System Count" in hist_df.columns:
                    hist_df["System Count"] = pd.to_numeric(
                        hist_df["System Count"], errors="coerce"
                    ).fillna(0)
                    has_val = "Total Value" in hist_df.columns
                    if has_val:
                        hist_df["Total Value"] = pd.to_numeric(
                            hist_df["Total Value"], errors="coerce"
                        ).fillna(0)

                    for _, row in hist_df.iterrows():
                        n        = str(row.get("Name", "")).strip()
                        date_str = str(row.get("Date", "")).strip()
                        if not n:
                            continue
                        if active_date and date_str == active_date:
                            continue  # already in session
                        if cutoff is not None and date_str:
                            try:
                                rd = datetime.datetime.strptime(date_str, DATE_FMT).date()
                                if rd < cutoff:
                                    continue
                            except Exception:
                                continue  # unparseable date — exclude when cutoff active
                        try:
                            d_obj = datetime.datetime.strptime(date_str, DATE_FMT).date()
                        except Exception:
                            d_obj = None

                        # Backfill op_id for cashiers not in the current session
                        if n not in cashier_op_ids:
                            op = str(row.get("Operator_Id", "")).strip()
                            if op and op.lower() not in ("nan", "none", ""):
                                cashier_op_ids[n] = op

                        slips = int(row.get("System Count", 0))
                        value = float(row.get("Total Value", 0)) if has_val else 0.0
                        all_cashiers.add(n)
                        hist_daily.setdefault(n, []).append((d_obj, slips, value))
        except Exception:
            logging.exception("compute: loading history")

    # ── Targets from full history (unfiltered) ────────────────
    full_hist_df = hist_df
    if hist_df is None and os.path.exists(history_path):
        try:
            full_hist_df = pd.read_csv(history_path, dtype=str)
        except Exception:
            pass
    target_slips, target_value = compute_targets(full_hist_df)

    # ── Mistakes ──────────────────────────────────────────────
    if mistakes_by_c is None:
        mistakes_by_c = mistakes_by_cashier(cutoff)

    # Group active-session mistakes by cashier (filter to report date)
    session_mistakes: dict = {}
    if active_date:
        for cashier, mlist in mistakes_by_c.items():
            day_m = [m for m in mlist if m["date"] == active_date]
            if day_m:
                session_mistakes[cashier] = day_m

    # ── Build result rows ─────────────────────────────────────
    raw_rows = []

    for name in sorted(all_cashiers):
        op_id = cashier_op_ids.get(name, "")

        if session_only:
            # ── Single session ────────────────────────────────
            slips    = session_txn.get(name, 0)
            value    = session_val.get(name, 0.0)
            mistakes = session_mistakes.get(name, [])

            sc = score_one_session(slips, value, op_id, mistakes, target_slips, target_value)
            sc["consistency"] = None  # explicitly N/A

            raw_rows.append({
                "name":          name,
                "txn":           slips,
                "value":         value,
                "avg_val":       value / slips if slips else 0.0,
                "slips_per_hr":  sc["slips_per_hr"],
                "throughput":    sc["slips_per_hr"] / _TARGET_PER_HOUR,
                "accuracy":      sc["acc_score"],
                "consistency":   None,
                "score":         int(round(sc["total"])),
                "grade":         grade(sc["total"]),
                "breakdown":     sc,
                "mistakes":      len(mistakes),
                "penalty":       sc["penalty"],
                "mistakes_list": mistakes,
                "op_id":         op_id,
                "sessions":      1,
            })

        else:
            # ── Multi-day ─────────────────────────────────────
            daily_entries = []

            # Add current session as one entry
            if name in session_txn:
                if active_date:
                    try:
                        sess_date = datetime.datetime.strptime(active_date, DATE_FMT).date()
                    except Exception:
                        sess_date = today
                else:
                    sess_date = today
                daily_entries.append((sess_date, session_txn[name], session_val.get(name, 0.0)))

            for entry in hist_daily.get(name, []):
                daily_entries.append(entry)

            if not daily_entries:
                continue

            # Group this cashier's mistakes by date string
            cashier_mistakes = mistakes_by_c.get(name, [])
            mistakes_by_date: dict = {}
            for m in cashier_mistakes:
                mistakes_by_date.setdefault(m["date"], []).append(m)

            # Compute a base score for every working day
            daily_scores = []
            dated_daily  = []   # (date, base_score) for recency weighting
            total_slips  = 0
            total_value  = 0.0
            all_mistakes_flat = list(cashier_mistakes)  # full period

            for entry_date, slips, value in daily_entries:
                date_str = entry_date.strftime(DATE_FMT) if entry_date else ""
                day_mist = mistakes_by_date.get(date_str, [])
                sc_day   = score_one_session(slips, value, op_id, day_mist,
                                             target_slips, target_value)
                daily_scores.append(sc_day["total"])
                if entry_date:
                    dated_daily.append((entry_date, sc_day["total"]))
                total_slips += slips
                total_value += value

            sessions = len(daily_entries)

            # Consistency from spread of daily base scores
            cons = consistency_score(daily_scores)

            # Period base score (recency-weighted for 3M/6M/12M)
            if scope in _RECENCY and dated_daily:
                period_base = recency_weighted_avg(dated_daily, scope, today)
            else:
                period_base = (
                    sum(daily_scores) / len(daily_scores)
                    if daily_scores else 0.0
                )

            final_score = max(0.0, min(100.0, period_base + cons))

            total_penalty = sum(m["points"] for m in all_mistakes_flat)

            # Build period-level display breakdown (correct rates, not inflated)
            hpd     = shift_hours(op_id)
            avg_spd = total_slips / sessions
            avg_vpd = total_value / sessions
            avg_sph = avg_spd / hpd if hpd else 0.0
            thr_r   = avg_sph / _TARGET_PER_HOUR
            per_err = len(all_mistakes_flat) / total_slips if total_slips else 0.0

            d_thr   = round(min(float(_W_THROUGHPUT), min(thr_r, 1.2) * _W_THROUGHPUT), 1)
            d_val   = round(min(float(_W_VALUE), (avg_vpd / target_value) * _W_VALUE if target_value else 0.0), 1)
            d_slip  = round(min(float(_W_SLIPS), (avg_spd / target_slips) * _W_SLIPS if target_slips else 0.0), 1)
            d_acc   = round(max(0.0, (1.0 - min(per_err, 1.0)) * _W_ACCURACY), 1)
            d_clean = round(max(0.0, (1.0 - min(per_err, 1.0)) * _W_CLEAN_RATIO), 1)

            sample_sc = {
                "thr_score":    d_thr,
                "val_score":    d_val,
                "slip_score":   d_slip,
                "acc_score":    d_acc,
                "clean_score":  d_clean,
                "consistency":  cons,
                "penalty":      total_penalty,
                "base":         round(d_thr + d_val + d_slip + d_acc + d_clean, 1),
                "total":        round(final_score, 1),
                "slips_per_hr": round(avg_sph, 2),
                "mistake_count": len(all_mistakes_flat),
            }

            raw_rows.append({
                "name":          name,
                "txn":           total_slips,
                "value":         total_value,
                "avg_val":       total_value / total_slips if total_slips else 0.0,
                "slips_per_hr":  sample_sc["slips_per_hr"],
                "throughput":    sample_sc["slips_per_hr"] / _TARGET_PER_HOUR,
                "accuracy":      sample_sc["acc_score"],
                "consistency":   cons,
                "score":         int(round(final_score)),
                "grade":         grade(final_score),
                "breakdown":     sample_sc,
                "mistakes":      len(all_mistakes_flat),
                "penalty":       total_penalty,
                "mistakes_list": all_mistakes_flat,
                "op_id":         op_id,
                "sessions":      sessions,
                "period_base":   round(period_base, 1),
            })

    return PerformanceResult(rows=raw_rows, target_slips=target_slips,
                             target_value=target_value, scope=scope)


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

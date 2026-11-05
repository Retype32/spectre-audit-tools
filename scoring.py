"""
scoring.py — Pure-Python cashier performance scoring logic.

No Qt dependency.  Safe to import in headless / test environments.

Score (0–100) per working day = positive components − mistake penalties.
Slips per hour is what matters most; cash volume only adds a small bonus.

Positive components (max 90 pts for one day, 100 pts over several days):
  Slips per hour  50 pts — slips/hr vs the day's target (25/hr for VMS).
                           Capped at 100% of target. On a day when every bag
                           was cleared, the target is lowered to the pace the
                           team actually managed (there was no more work).
  Cash volume     10 pts — cash per hour vs the team's average that day,
                           capped at 100%: keeping up with the team's cash
                           counts a little, but slips always count more.
  Accuracy        20 pts — (1 − mistake_rate) × 20
  Consistency     10 pts — score stability over time (multi-day scopes only)
  Clean Ratio     10 pts — % of slips untouched by any mistake

Not scored: 360 processing days (very high cash, few slips — see
is_360_day) and non-VMS (e.g. ISA) days. The slips-per-hour target applies
to VMS work only.

Mistake penalties (deducted from the above, floor at 0) are in
config.MISTAKE_TYPES. A confirmed duplicate is the most serious (−20).
"""
import datetime
import logging
import os
import statistics

import pandas as pd

from config import DUPLICATE_VERDICTS_DB, MISTAKES_DB, MISTAKE_TYPES, TEN_HOUR_OP_IDS


# ── Operator / shift constants ────────────────────────────────────────────────
_TEN_HOUR_OP_IDS    = TEN_HOUR_OP_IDS   # set in local_settings.json
_TARGET_PER_HOUR    = 25                # VMS slips per hour (manager can change)

# 360 processing: a cashier-day with very high cash per slip and few slips
DEFAULT_360_MIN_CASH_PER_SLIP = 10_000.0
DEFAULT_360_MAX_SLIPS         = 100

# ── Score component weights ───────────────────────────────────────────────────
_W_SLIP_RATE   = 50
_W_CASH        = 10
_W_ACCURACY    = 20
_W_CONSISTENCY = 10
_W_CLEAN_RATIO = 10

# ── Recency buckets per scope ─────────────────────────────────────────────────
# (cumulative_day_threshold, bucket_weight)
_RECENCY = {
    "3 Months":  [(30, 0.50), (60, 0.30), (90,  0.20)],
    "6 Months":  [(60, 0.50), (120, 0.30), (180, 0.20)],
    "12 Months": [(120, 0.50), (240, 0.30), (365, 0.20)],
}

# ── Available time scopes (used by the UI dropdown) ──────────────────────────
SCOPES = [
    "This Report",
    "Today",
    "This Week",
    "This Month",
    "3 Months",
    "6 Months",
    "12 Months",
]


# ── Grade + colour mapping ────────────────────────────────────────────────────

def grade(score) -> str:
    """Map a numeric score to an A–F grade string."""
    s = int(score)
    if s >= 90: return "A"
    if s >= 75: return "B"
    if s >= 60: return "C"
    if s >= 45: return "D"
    return "F"


# Kept as the private alias used throughout the codebase to avoid a rename cascade.
_grade = grade


def shift_hours(op_id: str) -> int:
    """Return the expected shift length (hours) for an operator ID."""
    return 10 if str(op_id).strip() in _TEN_HOUR_OP_IDS else 8


_shift_hours = shift_hours


# ── Target derivation ─────────────────────────────────────────────────────────

def is_360_day(slips, value, min_cash_per_slip=DEFAULT_360_MIN_CASH_PER_SLIP,
               max_slips=DEFAULT_360_MAX_SLIPS) -> bool:
    """True if one cashier's day looks like 360 processing: few slips with a
    very high average cash per slip (e.g. 45 slips and €1.5m)."""
    return 0 < slips <= max_slips and value / slips >= min_cash_per_slip


def score_day(slips, value, op_id, mistakes, rate_target, cash_per_hour_baseline) -> dict:
    """Score one cashier for one working day (0–90 before consistency).

    rate_target:            slips per hour expected that day (normally 25)
    cash_per_hour_baseline: the team's average cash per hour that day
    """
    hours        = shift_hours(op_id)
    slips_per_hr = slips / hours if hours else 0.0
    cash_per_hr  = value / hours if hours else 0.0

    rate_ratio = slips_per_hr / rate_target if rate_target else 0.0
    rate_score = _W_SLIP_RATE * min(rate_ratio, 1.0)

    if cash_per_hour_baseline and cash_per_hour_baseline > 0:
        cash_ratio = min(cash_per_hr / cash_per_hour_baseline, 1.0)
    else:
        cash_ratio = 1.0          # nothing to compare with — no penalty
    cash_score = _W_CASH * cash_ratio

    mistake_count = len(mistakes)
    error_rate    = mistake_count / slips if slips else 0.0
    acc_score     = max(0.0, (1.0 - min(error_rate, 1.0)) * _W_ACCURACY)
    clean_score   = max(0.0, (1.0 - min(error_rate, 1.0)) * _W_CLEAN_RATIO)

    penalty = sum(m["points"] for m in mistakes)

    base  = rate_score + cash_score + acc_score + clean_score
    total = max(0.0, min(100.0, base - penalty))

    return {
        "rate_score":    round(rate_score,  1),
        "cash_score":    round(cash_score,  1),
        "acc_score":     round(acc_score,   1),
        "clean_score":   round(clean_score, 1),
        "consistency":   0.0,
        "penalty":       penalty,
        "base":          round(base, 1),
        "total":         round(total, 1),
        "slips_per_hr":  round(slips_per_hr, 2),
        "cash_per_hr":   round(cash_per_hr, 2),
        "rate_target":   rate_target,
        "mistake_count": mistake_count,
    }


# ── Multi-day aggregation helpers ─────────────────────────────────────────────

def consistency_score(scores) -> float:
    """Score stability (0–10) from a list of daily scores.

    A single day has no variance → returns maximum 10.
    Perfectly flat daily scores → 10.  Wild swings → 0.
    """
    if len(scores) < 2:
        return 10.0
    mean = statistics.mean(scores)
    if mean == 0:
        return 0.0
    std = statistics.stdev(scores)
    raw = 1.0 - (std / mean)
    return round(max(0.0, min(float(_W_CONSISTENCY), raw * _W_CONSISTENCY)), 1)


_consistency_score = consistency_score


def recency_weighted_avg(dated_scores, scope, today) -> float:
    """Compute a recency-weighted average of (date, score) pairs.

    Scores in the most recent bucket get the highest weight.
    Falls back to a simple mean for scopes without a recency config.
    """
    if not dated_scores:
        return 0.0
    buckets_def = _RECENCY.get(scope)
    if not buckets_def:
        return sum(s for _, s in dated_scores) / len(dated_scores)

    thresholds    = [b[0] for b in buckets_def]
    bucket_scores = [[] for _ in buckets_def]

    for date, score in dated_scores:
        days_ago = (today - date).days
        placed   = False
        for i, thresh in enumerate(thresholds):
            if days_ago <= thresh:
                bucket_scores[i].append(score)
                placed = True
                break
        if not placed:
            bucket_scores[-1].append(score)

    weighted_sum = 0.0
    total_weight = 0.0
    for i, (_, weight) in enumerate(buckets_def):
        if bucket_scores[i]:
            avg = sum(bucket_scores[i]) / len(bucket_scores[i])
            weighted_sum += avg * weight
            total_weight += weight

    return weighted_sum / total_weight if total_weight else 0.0


_recency_weighted_avg = recency_weighted_avg


# ── Mistake data loaders ──────────────────────────────────────────────────────

def load_confirmed_dups_as_mistakes(cutoff=None) -> list:
    """Convert confirmed duplicate verdicts into mistake-format dicts."""
    result = []
    try:
        if not os.path.exists(DUPLICATE_VERDICTS_DB):
            return result
        vdf = pd.read_csv(DUPLICATE_VERDICTS_DB, dtype=str)
        for _, row in vdf.iterrows():
            if row.get("verdict", "") != "confirmed":
                continue
            key_parts = str(row.get("key", "")).split("|")
            date_str  = key_parts[0].strip() if key_parts else ""
            if cutoff is not None and date_str:
                try:
                    rd = datetime.datetime.strptime(date_str, "%d.%m.%Y").date()
                    if rd < cutoff:
                        continue
                except Exception:
                    continue
            result.append({
                "date":    date_str,
                "cashier": str(row.get("cashier", "")).strip(),
                "type":    "duplicate_slip",
                "points":  MISTAKE_TYPES["duplicate_slip"]["points"],
                "notes":   "Confirmed duplicate (auto)",
            })
    except Exception:
        logging.exception("load_confirmed_dups_as_mistakes")
    return result


_load_confirmed_dups_as_mistakes = load_confirmed_dups_as_mistakes


def load_manual_mistakes(cutoff=None) -> list:
    """Load rows from mistakes.csv, optionally filtered by cutoff date."""
    rows = []
    try:
        if not os.path.exists(MISTAKES_DB):
            return rows
        mdf = pd.read_csv(MISTAKES_DB, dtype=str)
        for _, row in mdf.iterrows():
            date_str = str(row.get("date", "")).strip()
            if cutoff is not None and date_str:
                try:
                    rd = datetime.datetime.strptime(date_str, "%d.%m.%Y").date()
                    if rd < cutoff:
                        continue
                except Exception:
                    continue
            cashier = str(row.get("cashier", "")).strip()
            mtype   = str(row.get("type", "small_mistake")).strip()
            pts_raw = str(row.get("severity_points", "0")).strip()
            try:
                pts = int(pts_raw)
            except ValueError:
                pts = MISTAKE_TYPES.get(mtype, {}).get("points", 3)
            rows.append({
                "date":    date_str,
                "cashier": cashier,
                "type":    mtype,
                "points":  pts,
                "notes":   str(row.get("notes", "")).strip(),
            })
    except Exception:
        logging.exception("load_manual_mistakes")
    return rows


_load_manual_mistakes = load_manual_mistakes


def all_mistakes(cutoff=None) -> list:
    """Union of manual mistakes + auto-converted confirmed duplicates."""
    return load_manual_mistakes(cutoff) + load_confirmed_dups_as_mistakes(cutoff)


_all_mistakes = all_mistakes


def mistakes_by_cashier(cutoff=None) -> dict:
    """Return {cashier_name: [mistake_dict, ...]}."""
    result = {}
    for m in all_mistakes(cutoff):
        c = m["cashier"]
        if c:
            result.setdefault(c, []).append(m)
    return result


_mistakes_by_cashier = mistakes_by_cashier


# ── Display helpers ───────────────────────────────────────────────────────────

def penalty_summary(mistakes) -> str:
    """Return a human-readable penalty breakdown string."""
    if not mistakes:
        return "None"
    counts = {}
    for m in mistakes:
        mtype = m["type"]
        label = MISTAKE_TYPES.get(mtype, {}).get("label", mtype.replace("_", " ").title())
        counts[label] = counts.get(label, {"n": 0, "pts": 0})
        counts[label]["n"]   += 1
        counts[label]["pts"] += m["points"]
    parts = []
    for label, info in sorted(counts.items(), key=lambda x: -x[1]["pts"]):
        parts.append(f"{info['n']}× {label}  −{info['pts']} pts")
    return "\n".join(parts)


_penalty_summary = penalty_summary

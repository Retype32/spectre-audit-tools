"""
engine/targets.py — team targets set by the manager.

Targets are kept in ONE shared file (config.TARGETS_FILE, under BASE_PATH —
the network drive in production) so everyone works to the same numbers.
They are edited in Settings → Team Targets.

Every target is optional. A blank target means "no target", except for the
three scoring targets, where blank keeps Spectre's built-in behaviour:
daily slips and daily value fall back to the team's historical average, and
slips per hour falls back to 25.

Pure Python, no Qt.
"""
import datetime
import json
import logging
import os
from dataclasses import dataclass

from config import TARGETS_FILE

FILE_VERSION = 1


@dataclass(frozen=True)
class TargetDef:
    key: str
    label: str          # shown in Settings and to the agent
    unit: str           # "slips", "€", "slips/hr", "points", "%", "count"
    better: str         # "higher" or "lower" is better
    group: str          # the Spectre tab the target belongs to
    description: str
    in_score: bool = False   # used by the cashier performance score
    positive: bool = False   # must be > 0 (not just >= 0)


TARGETS = [
    # ── Cashier Performance: used in every cashier's score ────────────────
    TargetDef("cashier_daily_slips", "Daily slips per cashier", "slips", "higher",
              "Cashier Performance",
              "Used in the score. Blank = the team's historical average.",
              in_score=True, positive=True),
    TargetDef("cashier_daily_value", "Daily value per cashier", "€", "higher",
              "Cashier Performance",
              "Used in the score. Blank = the team's historical average.",
              in_score=True, positive=True),
    TargetDef("slips_per_hour", "Slips per hour", "slips/hr", "higher",
              "Cashier Performance",
              "Used in the score. Blank = 25 per hour.",
              in_score=True, positive=True),
    # ── Cashier Performance: team goals ───────────────────────────────────
    TargetDef("team_score", "Team score", "points", "higher", "Cashier Performance",
              "Average cashier score for the period (0–100)."),
    TargetDef("min_cashier_score", "Lowest acceptable cashier score", "points", "higher",
              "Cashier Performance",
              "Every cashier should score at least this (0–100)."),
    TargetDef("team_daily_slips", "Team slips per day", "slips", "higher",
              "Cashier Performance", "All cashiers together, per working day."),
    TargetDef("team_daily_value", "Team value per day", "€", "higher",
              "Cashier Performance", "All cashiers together, per working day."),
    TargetDef("max_error_rate", "Mistakes per 100 slips", "%", "lower",
              "Cashier Performance", "Logged mistakes and confirmed duplicates, per 100 slips."),
    # ── Integrity Check: per report ───────────────────────────────────────
    TargetDef("max_high_risk_duplicates", "High-risk duplicates per report", "count", "lower",
              "Integrity Check", "Identical-duplicate pairs found in one report."),
    TargetDef("max_suspicious_patterns", "Suspicious patterns per report", "count", "lower",
              "Integrity Check", "Repeated-amount pairs found in one report."),
    TargetDef("max_shared_wallets", "Shared wallets per report", "count", "lower",
              "Integrity Check", "Wallets used by more than one operator in one report."),
    # ── Other tabs (compared once their figures are available to the agent) ─
    TargetDef("max_missing_slips", "Missing slips per audit", "slips", "lower",
              "Slip Audit", "Slips in the system but not found in the physical count, whole team."),
    TargetDef("max_discrepancies_per_day", "Discrepancies per day", "count", "lower",
              "Discrepancies", "Non-zero discrepancies per report date (blind counts excluded)."),
    TargetDef("max_discrepancy_value_per_day", "Discrepancy value per day", "€", "lower",
              "Discrepancies", "Total of shortages and overages per report date (blind counts excluded)."),
    TargetDef("max_high_risk_cashiers", "Cashiers in the high-risk band", "count", "lower",
              "Risk Scoring", "Cashiers with a risk score of 61 or more."),
    TargetDef("min_data_quality", "Data quality score", "points", "higher",
              "Data Quality", "Overall data quality score of a report (0–100)."),
]
BY_KEY = {t.key: t for t in TARGETS}
GROUPS = list(dict.fromkeys(t.group for t in TARGETS))


class TargetError(ValueError):
    """One or more target values are invalid. `errors` lists the messages."""

    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


# ── Reading and writing the shared file ───────────────────────────────────────

def parse_value(defn, raw):
    """Turn user input into a target value. Blank → None. Raises ValueError."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip().replace("€", "").replace(",", "").replace("%", "").strip()
        if raw == "":
            return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{defn.label}: '{raw}' is not a number")
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{defn.label}: '{raw}' is not a number")
    if value < 0 or (defn.positive and value == 0):
        raise ValueError(f"{defn.label}: must be {'more than' if defn.positive else 'at least'} 0")
    if defn.unit in ("points", "%") and value > 100:
        raise ValueError(f"{defn.label}: must be between 0 and 100")
    return value


def clean_targets(values):
    """Validate {key: raw value}. Unknown keys and blanks are dropped.
    Raises TargetError listing every invalid value."""
    out, errors = {}, []
    for key, raw in values.items():
        defn = BY_KEY.get(key)
        if defn is None:
            continue
        try:
            v = parse_value(defn, raw)
        except ValueError as e:
            errors.append(str(e))
            continue
        if v is not None:
            out[key] = v
    if errors:
        raise TargetError(errors)
    return out


def read_targets_file(path=TARGETS_FILE):
    """Return (targets, problem). `problem` is None or a message for the user.
    A missing file is not a problem: it just means no targets are set."""
    if not os.path.exists(path):
        return {}, None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("targets", {}) if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            return {}, f"{path} is not a valid targets file"
    except Exception as e:
        return {}, f"Could not read {path}: {e}"
    out, bad = {}, []
    for key, value in raw.items():
        defn = BY_KEY.get(key)
        if defn is None:
            continue
        try:
            v = parse_value(defn, value)
        except ValueError as e:
            bad.append(str(e))
            continue
        if v is not None:
            out[key] = v
    return out, ("; ".join(bad) if bad else None)


def load_targets(path=TARGETS_FILE):
    """Valid targets from the shared file ({} if none). Problems are logged."""
    targets, problem = read_targets_file(path)
    if problem:
        logging.warning(f"Team targets: {problem}")
    return targets


def save_targets(values, path=TARGETS_FILE, now=None):
    """Validate and write targets. The file is replaced in one step so other
    users never read a half-written file. Returns the saved targets."""
    targets = clean_targets(values)
    if now is None:
        now = datetime.datetime.now()
    data = {
        "version":    FILE_VERSION,
        "updated_at": now.strftime("%Y-%m-%d %H:%M"),
        "targets":    {k: targets[k] for k in BY_KEY if k in targets},
    }
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
    return targets


# ── Comparing actual figures with targets ─────────────────────────────────────

def compare(key, actual, targets, who=None, note=""):
    """One target line: actual vs target, how far off, and whether it's met.

    gap = actual − target (negative means below target).
    who = names that miss the target individually, where that applies.
    """
    defn = BY_KEY[key]
    target = targets.get(key)
    item = {
        "key": key, "label": defn.label, "unit": defn.unit, "better": defn.better,
        "group": defn.group, "target": target, "actual": actual,
        "gap": None, "gap_pct": None, "met": None, "who": who or [], "note": note,
    }
    if target is None or actual is None:
        return item
    item["gap"] = actual - target
    item["gap_pct"] = (item["gap"] / target * 100) if target else None
    item["met"] = actual >= target if defn.better == "higher" else actual <= target
    return item


def performance_progress(result, targets):
    """Cashier Performance figures for a period vs targets.

    result: engine.performance.PerformanceResult
    """
    rows = result.rows
    if not rows:
        return []
    total_txn = sum(r["txn"] for r in rows)
    total_val = sum(r["value"] for r in rows)
    sessions = sum(r["sessions"] for r in rows)
    days = len(result.working_days) or 1
    scores = [r["score"] for r in rows]
    mistakes = sum(r["mistakes"] for r in rows)

    def per_day(r, field):
        return r[field] / r["sessions"] if r["sessions"] else 0.0

    def below(key, value_of):
        t = targets.get(key)
        if t is None:
            return []
        better = BY_KEY[key].better
        return [r["name"] for r in rows
                if (value_of(r) < t if better == "higher" else value_of(r) > t)]

    def err_rate(r):
        return r["mistakes"] / r["txn"] * 100 if r["txn"] else 0.0

    return [
        compare("cashier_daily_slips", total_txn / sessions if sessions else 0.0, targets,
                below("cashier_daily_slips", lambda r: per_day(r, "txn")),
                f"Target used in the score: {result.target_slips:.0f} "
                f"({result.target_sources.get('slips', 'history')})."),
        compare("cashier_daily_value", total_val / sessions if sessions else 0.0, targets,
                below("cashier_daily_value", lambda r: per_day(r, "value")),
                f"Target used in the score: €{result.target_value:,.0f} "
                f"({result.target_sources.get('value', 'history')})."),
        compare("slips_per_hour", sum(r["slips_per_hr"] for r in rows) / len(rows), targets,
                below("slips_per_hour", lambda r: r["slips_per_hr"]),
                f"Target used in the score: {result.target_per_hour:g} per hour "
                f"({result.target_sources.get('per_hour', 'default')})."),
        compare("team_score", int(sum(scores) / len(scores)), targets),
        compare("min_cashier_score", min(scores), targets,
                below("min_cashier_score", lambda r: r["score"])),
        compare("team_daily_slips", total_txn / days, targets, note=f"{days} working day(s)."),
        compare("team_daily_value", total_val / days, targets, note=f"{days} working day(s)."),
        compare("max_error_rate", mistakes / total_txn * 100 if total_txn else 0.0, targets,
                below("max_error_rate", err_rate)),
    ]


def integrity_progress(result, targets):
    """Integrity Check counts for one report vs targets.

    result: engine.detection.IntegrityResult
    """
    return [
        compare("max_high_risk_duplicates", result.high_risk_count, targets),
        compare("max_suspicious_patterns", result.suspicious_count, targets),
        compare("max_shared_wallets", result.shared_wallet_count, targets),
    ]

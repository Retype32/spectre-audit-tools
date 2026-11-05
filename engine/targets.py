"""
engine/targets.py — team targets and rules set by the manager.

Kept in ONE shared file (config.TARGETS_FILE, under BASE_PATH — the network
drive in production) so everyone works to the same numbers. Edited in
Settings → Team Targets.

Every entry is optional. A blank entry uses its default (e.g. 25 slips per
hour, 0 bags carried over, the 360 thresholds) or, for entries without a
default, means "no target".

Pure Python, no Qt.
"""
import datetime
import json
import logging
import os
from dataclasses import dataclass

from config import TARGETS_FILE
from scoring import DEFAULT_360_MAX_SLIPS, DEFAULT_360_MIN_CASH_PER_SLIP, _TARGET_PER_HOUR

FILE_VERSION = 1


@dataclass(frozen=True)
class TargetDef:
    key: str
    label: str          # shown in Settings and to the agent
    unit: str           # "slips/hr", "points", "bags", "€", "slips"
    better: str         # "higher" or "lower" is better (for rules: the direction of the limit)
    group: str          # where it belongs
    description: str
    default: float = None    # used when blank (None = no target)
    in_score: bool = False   # changes how scores are calculated
    positive: bool = False   # must be > 0 (not just >= 0)
    kind: str = "target"     # "target" (compared with results) or "rule" (a setting)


TARGETS = [
    # ── Cashier Performance ───────────────────────────────────────────────
    TargetDef("slips_per_hour", "Slips per hour (VMS)", "slips/hr", "higher",
              "Cashier Performance",
              "Every regular VMS cashier's target. Daily volume follows from shift length "
              "(e.g. 200 for 8 hours, 250 for 10 hours). Used in the score.",
              default=_TARGET_PER_HOUR, in_score=True, positive=True),
    TargetDef("team_score", "Team score", "points", "higher", "Cashier Performance",
              "Average cashier score for the period (0–100)."),
    TargetDef("min_cashier_score", "Lowest acceptable cashier score", "points", "higher",
              "Cashier Performance", "Every cashier should score at least this (0–100)."),
    # ── Daily bags ────────────────────────────────────────────────────────
    TargetDef("max_carry_over_bags", "Bags carried over per day", "bags", "lower",
              "Daily Bags",
              "A day is cleared when no more than this many bags are carried over. On a "
              "cleared day the slips-per-hour target drops to the pace the team managed, "
              "because there was no more work. Used in the score.",
              default=0, in_score=True),
    # ── 360 processing ────────────────────────────────────────────────────
    TargetDef("proc360_min_cash_per_slip", "360: average cash per slip of at least", "€",
              "higher", "360 Processing",
              "With the next rule, marks a cashier's day as 360 processing. 360 days are "
              "not scored and don't affect the team's averages.",
              default=DEFAULT_360_MIN_CASH_PER_SLIP, in_score=True, positive=True, kind="rule"),
    TargetDef("proc360_max_slips", "360: no more than this many slips", "slips", "lower",
              "360 Processing",
              "A day with more slips than this is never treated as 360, however high the cash.",
              default=DEFAULT_360_MAX_SLIPS, in_score=True, positive=True, kind="rule"),
]
BY_KEY = {t.key: t for t in TARGETS}
GROUPS = list(dict.fromkeys(t.group for t in TARGETS))


class TargetError(ValueError):
    """One or more target values are invalid. `errors` lists the messages."""

    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def effective(targets, key):
    """The value in force: the manager's value, else the default (may be None)."""
    value = targets.get(key)
    return BY_KEY[key].default if value is None else value


# ── Reading and writing the shared file ───────────────────────────────────────

def parse_value(defn, raw):
    """Turn user input into a value. Blank → None. Raises ValueError."""
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
    if defn.unit == "points" and value > 100:
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
    A missing file is not a problem: it just means nothing is set."""
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

def compare(key, actual, target, who=None, note=""):
    """One target line: actual vs target, how far off, and whether it's met.

    gap = actual − target (negative means below target).
    who = names (or dates) that miss the target individually.
    """
    defn = BY_KEY[key]
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
    """Cashier Performance and daily-bag figures for a period vs targets.

    result: engine.performance.PerformanceResult
    """
    items = []
    rows = result.rows
    if rows:
        scores = [r["score"] for r in rows]
        rate_target = effective(targets, "slips_per_hour")
        cleared = sum(1 for d in result.days if d.get("cleared"))
        items.append(compare(
            "slips_per_hour", sum(r["slips_per_hr"] for r in rows) / len(rows), rate_target,
            who=[r["name"] for r in rows if r["throughput"] < 1.0],
            note=(f"'who' = below their own target for the days worked; "
                  f"{cleared} cleared day(s) used a lower target.")))
        team_t = targets.get("team_score")
        items.append(compare("team_score", int(sum(scores) / len(scores)), team_t))
        min_t = targets.get("min_cashier_score")
        items.append(compare("min_cashier_score", min(scores), min_t,
                             who=[r["name"] for r in rows if min_t is not None and r["score"] < min_t]))

    logged = [d for d in result.days if d.get("bags") is not None]
    if logged:
        max_carry = effective(targets, "max_carry_over_bags")
        avg_carry = sum(d["carried_over"] for d in logged) / len(logged)
        items.append(compare(
            "max_carry_over_bags", avg_carry, max_carry,
            who=[d["date"] for d in logged if d["carried_over"] > max_carry],
            note=(f"Average over {len(logged)} logged day(s); "
                  f"{sum(d['bags'] for d in logged)} bags in, "
                  f"{sum(d['carried_over'] for d in logged)} carried over. "
                  f"'who' = days over the limit.")))
    return items

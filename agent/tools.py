"""
agent/tools.py — read-only tools behind the manager's questions.

Each tool answers one kind of question from the saved history
(Performance_History.csv, the bag log, mistakes and duplicate verdicts).
No loaded report is needed and nothing is ever written. Every number comes
from the engine — nothing here is estimated — and results are plain,
JSON-friendly dicts, so the same tools serve the End of Day summary today
and an AI model later.

    team_overview         How is the team doing over a period?
    targets_vs_actual     What are the targets and how far off are we?
    cashier_ranking       Who is furthest behind (or ahead), and why?
    cashier_profile       How is one person doing?
    day_summary           What happened on one day?
    monthly_cash_leaders  Who handles the most cash per hour, and why?
"""
import datetime
import os

import pandas as pd

from config import (BAG_LOG_DB, DUPLICATE_VERDICTS_DB, MISTAKE_TYPES, PERFORMANCE_HISTORY_DB,
                    TARGETS_FILE)
from engine.bags import load_bag_log
from engine.performance import compute_performance, scope_cutoff, sort_rows, team_summary
from engine.targets import load_targets, performance_progress
from engine.volume import current_month, monthly_volume
from scoring import (
    SCOPES, _W_ACCURACY, _W_CASH, _W_CLEAN_RATIO, _W_CONSISTENCY, _W_SLIP_RATE, grade,
    load_manual_mistakes, penalty_summary,
)

DATE_FMT = "%d.%m.%Y"
PERIODS = [s for s in SCOPES if s != "This Report"]   # Today, This Week, ... 12 Months

# Where the tools read from. Module attributes, looked up on every call, so
# tests can point them at temporary files.
HISTORY_FILE = PERFORMANCE_HISTORY_DB
BAG_LOG_FILE = BAG_LOG_DB
TARGETS_PATH = TARGETS_FILE
VERDICTS_FILE = DUPLICATE_VERDICTS_DB


def current_targets():
    return load_targets(TARGETS_PATH)


class ToolError(ValueError):
    """Bad input to a tool (unknown period, bad date, ...)."""


# ── helpers ───────────────────────────────────────────────────────────────────

def _today(today):
    return today or datetime.date.today()


def _parse_day(text):
    if isinstance(text, datetime.date):
        return text
    try:
        return datetime.datetime.strptime(str(text).strip(), DATE_FMT).date()
    except ValueError:
        raise ToolError(f"date must be DD.MM.YYYY, got '{text}'")


def _performance(period, today):
    if period not in PERIODS:
        raise ToolError(f"period must be one of: {', '.join(PERIODS)}")
    empty = pd.DataFrame(columns=["Cashier Name"])
    return compute_performance(empty, period, active_date=None, today=today,
                               history_path=HISTORY_FILE, targets=current_targets(),
                               bag_log=load_bag_log(BAG_LOG_FILE))


def _r(x, n=1):
    return None if x is None else round(float(x), n)


def explain(row):
    """What cost this cashier points, biggest first.

    [{"factor", "points_lost", "detail"}] — points_lost is out of the 100
    available; penalties over several days are averaged like the score is.
    """
    b = row["breakdown"]
    out = []

    lost = _W_SLIP_RATE - b["rate_score"]
    if lost >= 0.5:
        detail = (f"{row['slips_per_hr']:.1f} slips/hr — {row['throughput'] * 100:.0f}% "
                  f"of the target ({b['rate_target']:.1f}/hr)")
        daily = row.get("daily") or []
        short = sum(1 for d in daily if d["slips_per_hr"] < d["rate_target"])
        if len(daily) > 1 and short:
            detail += f"; below target on {short} of {len(daily)} days"
        out.append({"factor": "slips per hour", "points_lost": _r(lost), "detail": detail})
    lost = _W_CASH - b["cash_score"]
    if lost >= 0.5:
        out.append({"factor": "cash volume", "points_lost": _r(lost),
                    "detail": f"cash per hour at {b['cash_score'] / _W_CASH * 100:.0f}% of the "
                              f"team average"})
    lost = (_W_ACCURACY - b["acc_score"]) + (_W_CLEAN_RATIO - b["clean_score"])
    if lost >= 0.5:
        out.append({"factor": "accuracy", "points_lost": _r(lost),
                    "detail": f"{row['mistakes']} mistake(s) against {row['txn']} slips"})
    cons = row.get("consistency")
    if cons is not None and _W_CONSISTENCY - cons >= 0.5:
        out.append({"factor": "consistency", "points_lost": _r(_W_CONSISTENCY - cons),
                    "detail": "daily scores vary a lot"})
    if row["penalty"]:
        daily = row.get("daily") or []
        if row.get("period_base") is not None and daily:
            effect = sum(d["penalty"] for d in daily) / len(daily) + row.get("orphan_penalty", 0)
        else:
            effect = row["penalty"]
        out.append({"factor": "mistake penalties", "points_lost": _r(effect),
                    "detail": penalty_summary(row["mistakes_list"]).replace("\n", "; ")})
    return sorted(out, key=lambda x: -x["points_lost"])


def _cashier_line(row, rank=None, reasons=3):
    item = {
        "name": row["name"], "score": row["score"], "grade": row["grade"],
        "slips": row["txn"], "cash": _r(row["value"], 0), "days": row["sessions"],
        "slips_per_hour": _r(row["slips_per_hr"]),
        "pct_of_slip_target": _r(row["throughput"] * 100, 0),
        "mistakes": row["mistakes"], "penalty": row["penalty"],
        "why": explain(row)[:reasons],
    }
    if rank is not None:
        item["rank"] = rank
    return item


def _progress_items(result, targets):
    items = []
    for i in performance_progress(result, targets):
        items.append({
            "target": i["label"], "unit": i["unit"], "better": i["better"],
            "target_value": i["target"], "actual": _r(i["actual"], 2),
            "gap": _r(i["gap"], 2), "gap_pct": _r(i["gap_pct"]), "met": i["met"],
            "who_misses_it": i["who"], "note": i["note"],
        })
    return items


# ── tools ─────────────────────────────────────────────────────────────────────

def team_overview(period="This Week", today=None):
    """Team score, volume, bags and 360/ISA days for a period."""
    t = _today(today)
    res = _performance(period, t)
    start = scope_cutoff(period, t)
    out = {"period": period, "from": start.strftime(DATE_FMT) if start else None,
           "to": t.strftime(DATE_FMT), "working_days": len(res.working_days)}
    if res.rows:
        s = team_summary(res.rows)
        out.update({
            "team_score": s["team_score"], "team_grade": s["team_grade"],
            "cashiers": s["cashiers"], "slips": s["total_txn"], "cash": _r(s["total_value"], 0),
            "avg_slips_per_hour": _r(s["avg_rate"]), "grade_counts": s["grade_counts"],
            "mistakes": s["total_mistakes"], "penalty_points": s["total_penalty"],
        })
    else:
        out["note"] = "No scored work in this period."
    logged = [d for d in res.days if d["bags"] is not None]
    out["bags"] = {
        "logged_days": len(logged), "cleared_days": sum(1 for d in logged if d["cleared"]),
        "bags_in": sum(d["bags"] for d in logged),
        "carried_over": sum(d["carried_over"] for d in logged),
    }
    out["not_scored"] = {
        "days_360": sum(1 for u in res.unscored if u["kind"] == "360"),
        "cashiers_360": sorted({u["name"] for u in res.unscored if u["kind"] == "360"}),
        "other_format_days": sum(1 for u in res.unscored if u["kind"] != "360"),
    }
    out["slip_target_per_hour"] = res.target_per_hour
    return out


def targets_vs_actual(period="This Week", today=None):
    """Each target, the actual figure, the gap, and who misses it."""
    res = _performance(period, _today(today))
    return {"period": period, "items": _progress_items(res, current_targets())}


def cashier_ranking(period="This Week", lowest_first=True, limit=5, today=None):
    """Cashiers ordered by score, with what cost each of them points."""
    res = _performance(period, _today(today))
    ordered = sort_rows(res.rows, "score", ascending=bool(lowest_first))
    team = len(ordered)
    by_score = sort_rows(res.rows, "score", ascending=False)
    rank = {r["name"]: i + 1 for i, r in enumerate(by_score)}
    return {
        "period": period, "order": "lowest score first" if lowest_first else "highest score first",
        "team_size": team,
        "cashiers": [_cashier_line(r, rank=rank[r["name"]]) for r in ordered[:max(1, int(limit))]],
    }


def cashier_profile(name, period="This Month", today=None):
    """One cashier in detail: score breakdown, reasons, each day, mistakes, cash."""
    t = _today(today)
    res = _performance(period, t)
    wanted = str(name).strip().lower()
    rows = [r for r in res.rows if r["name"].lower() == wanted] or \
           [r for r in res.rows if wanted in r["name"].lower()]
    if len(rows) != 1:
        return {"found": False, "period": period,
                "matches" if rows else "cashiers_in_period": sorted(r["name"] for r in (rows or res.rows))}
    row = rows[0]
    by_score = sort_rows(res.rows, "score", ascending=False)
    out = _cashier_line(row, reasons=10)
    out.update({
        "found": True, "period": period, "rank": by_score.index(row) + 1,
        "team_size": len(res.rows), "team_score": team_summary(res.rows)["team_score"],
        "breakdown": {k: row["breakdown"][k] for k in
                      ("rate_score", "cash_score", "acc_score", "clean_score", "consistency")},
        "days_360": row["days_360"], "other_format_days": row["days_other"],
        "daily": [{**d, "value": _r(d["value"], 0), "rate_target": _r(d["rate_target"], 2)}
                  for d in row.get("daily", [])],
        "mistake_list": [{"date": m["date"], "type": MISTAKE_TYPES.get(m["type"], {}).get("label", m["type"]),
                          "points": m["points"]} for m in row["mistakes_list"]],
    })
    month = monthly_volume(current_month(t), history_path=HISTORY_FILE, targets=current_targets())
    mrow = next((m for m in month["rows"] if m["name"] == row["name"]), None)
    if mrow and mrow["days"]:
        out["this_month_cash"] = {
            "month": month["month"], "cash_per_hour": _r(mrow["cash_per_hour"], 0),
            "speed_vs_team_pct": _r(mrow["slips_per_hour_vs_team_pct"], 0),
            "lodgement_size_vs_team_pct": _r(mrow["cash_per_slip_vs_team_pct"], 0),
        }
    return out


def _confirmed_duplicates(day_str):
    if not os.path.exists(VERDICTS_FILE):
        return []
    v = pd.read_csv(VERDICTS_FILE, dtype=str)
    if "key" not in v.columns or "verdict" not in v.columns:
        return []
    v = v[(v["verdict"] == "confirmed") & v["key"].fillna("").str.startswith(day_str + "|")]
    return v["cashier"].fillna("").tolist() if "cashier" in v.columns else [""] * len(v)


def _as_single_day(row):
    """A one-day row scored like the "This Report" view: the day's own score
    (out of 90), with no consistency bonus."""
    day = row["daily"][0]
    row = dict(row, score=int(round(day["score"])), grade=grade(day["score"]), consistency=None)
    row["breakdown"] = dict(row["breakdown"], consistency=None, total=day["score"])
    return row


def day_summary(date=None, today=None):
    """One day: bags, team score, best and lowest cashiers, 360 and ISA work."""
    d = _parse_day(date) if date else _today(today)
    ds = d.strftime(DATE_FMT)
    res = _performance("Today", d)
    res.rows = [_as_single_day(r) for r in res.rows]
    info = res.days[0] if res.days else None
    out = {"date": ds, "weekday": d.strftime("%A"), "cashiers_scored": len(res.rows)}
    if info:
        out["bags"] = None if info["bags"] is None else {
            "bags_in": info["bags"], "carried_over": info["carried_over"],
            "completion_pct": _r(info["completion_pct"], 0), "cleared": info["cleared"]}
        out["slip_target_per_hour"] = _r(info["rate_target"], 2)
        out["team_pace_per_hour"] = _r(info["achieved_rate"], 2)
    if res.rows:
        s = team_summary(res.rows)
        ordered = sort_rows(res.rows, "score", ascending=False)
        out.update({
            "team_score": s["team_score"], "team_grade": s["team_grade"],
            "slips": s["total_txn"], "cash": _r(s["total_value"], 0),
            "best": _cashier_line(ordered[0], reasons=1),
            "lowest": _cashier_line(ordered[-1]) if len(ordered) > 1 else None,
            "cashiers": [_cashier_line(r, rank=i + 1, reasons=2) for i, r in enumerate(ordered)],
        })
    out["processing_360"] = [{"name": u["name"], "slips": u["slips"], "cash": _r(u["value"], 0)}
                             for u in res.unscored if u["kind"] == "360"]
    out["other_format"] = [{"name": u["name"], "format": u["format"], "slips": u["slips"]}
                           for u in res.unscored if u["kind"] != "360"]
    out["mistakes_logged"] = [
        {"cashier": m["cashier"], "type": MISTAKE_TYPES.get(m["type"], {}).get("label", m["type"]),
         "points": m["points"]}
        for m in load_manual_mistakes() if m["date"] == ds]
    out["confirmed_duplicates"] = _confirmed_duplicates(ds)
    return out


def monthly_cash_leaders(month=None, limit=5, today=None):
    """Highest cash per hour this month, and whether it comes from speed or bigger lodgements."""
    data = monthly_volume(month or current_month(_today(today)), history_path=HISTORY_FILE,
                          targets=current_targets())
    rows = [r for r in data["rows"] if r["days"]][:max(1, int(limit))]

    def why(r):
        sp, sz = r["slips_per_hour_vs_team_pct"] or 0, r["cash_per_slip_vs_team_pct"] or 0
        main = "speed" if abs(sp) >= abs(sz) else "lodgement size"
        return (f"{sp:+.0f}% slips per hour and {sz:+.0f}% cash per slip vs the team — "
                f"mainly {main}")

    t = data["team"]
    return {
        "month": data["month"],
        "team": {"cash": _r(t["cash"], 0), "cash_per_hour": _r(t["cash_per_hour"], 0),
                 "slips_per_hour": _r(t["slips_per_hour"]), "cash_per_slip": _r(t["cash_per_slip"], 0),
                 "working_days": t["working_days"], "days_360": t["days_360"],
                 "cash_360": _r(t["cash_360"], 0)},
        "leaders": [{"name": r["name"], "cash_per_hour": _r(r["cash_per_hour"], 0),
                     "days": r["days"], "cash": _r(r["cash"], 0), "why": why(r)} for r in rows],
    }

"""
agent/summary.py — the End of Day summary, in plain English, with no AI.

Built only from the read-only tools, so every figure in it is Spectre's own.
When an online model is connected later, it gets the same tool results and
can answer follow-up questions; this summary stays as the fixed daily view.
"""
import datetime

from agent.tools import DATE_FMT, current_targets, day_summary, team_overview
from engine.targets import effective


def _money(x):
    return f"€{x:,.0f}"


def _why(item):
    reasons = item.get("why") or []
    return "; ".join(r["detail"] for r in reasons) if reasons else "on target"


def end_of_day_summary(date=None, today=None):
    """Plain-text summary of one day (today if no date), for the manager."""
    day = day_summary(date=date, today=today)
    d = datetime.datetime.strptime(day["date"], DATE_FMT).date()
    targets = current_targets()
    lines = [f"End of Day — {day['weekday']} {day['date']}", ""]

    bags = day.get("bags")
    if bags:
        state = "cleared" if bags["cleared"] else "NOT cleared"
        lines.append(f"Bags: {bags['bags_in']} in, {bags['carried_over']} carried over — "
                     f"{state} ({bags['completion_pct']:.0f}% processed).")
        standard = effective(targets, "slips_per_hour")
        if bags["cleared"] and day.get("slip_target_per_hour") \
                and day["slip_target_per_hour"] < standard:
            lines.append(f"Every bag was processed, so today's slip target was the team's own "
                         f"pace: {day['slip_target_per_hour']:.1f} slips per hour.")
    else:
        lines.append("Bags: not logged for this day (Bag Counter → Daily Bag Log).")

    if day["cashiers_scored"]:
        team_t = targets.get("team_score")
        verdict = ""
        if team_t is not None:
            verdict = (f" — target {team_t:g}: met." if day["team_score"] >= team_t
                       else f" — target {team_t:g}: {team_t - day['team_score']:g} points short.")
        lines += [
            f"Team score: {day['team_score']} ({day['team_grade']}){verdict}",
            f"Slips: {day['slips']:,}  ·  Cash: {_money(day['cash'])}  ·  "
            f"{day['cashiers_scored']} cashier(s) scored.",
            "",
            f"Best: {day['best']['name']} — {day['best']['score']} ({day['best']['grade']}), "
            f"{day['best']['slips_per_hour']:.1f} slips/hr.",
        ]
        low = day.get("lowest")
        if low:
            lines.append(f"Needs most attention: {low['name']} — {low['score']} ({low['grade']}): "
                         f"{_why(low)}.")
        min_t = targets.get("min_cashier_score")
        if min_t is not None:
            below = [c["name"] for c in day["cashiers"] if c["score"] < min_t]
            lines.append(f"Below the lowest acceptable score ({min_t:g}): "
                         f"{', '.join(below) if below else 'none'}.")
    else:
        lines.append("No VMS cashier work recorded for this day yet "
                     "(import the day's report in Integrity Check).")

    if day["processing_360"]:
        lines.append("")
        lines.append("360 processing (not scored): " + "; ".join(
            f"{p['name']} — {p['slips']} slips, {_money(p['cash'])}" for p in day["processing_360"]))
    if day["other_format"]:
        lines.append("Not VMS (not scored): " + "; ".join(
            f"{p['name']} — {p['format']}, {p['slips']} slips" for p in day["other_format"]))

    lines.append("")
    mistakes = day["mistakes_logged"]
    lines.append("Mistakes logged: " + ("none." if not mistakes else "; ".join(
        f"{m['cashier']} — {m['type']} (−{m['points']})" for m in mistakes) + "."))
    dups = day["confirmed_duplicates"]
    lines.append("Confirmed duplicates: " + ("none." if not dups else
                                              f"{len(dups)} — {', '.join(n for n in dups if n)}."))

    week = team_overview("This Week", today=d)
    if week.get("team_score") is not None:
        b = week["bags"]
        lines += ["", f"Last 7 days: team score {week['team_score']} ({week['team_grade']}), "
                      f"{week['slips']:,} slips, {b['cleared_days']} of {b['logged_days']} "
                      f"logged day(s) cleared."]
    return "\n".join(lines)

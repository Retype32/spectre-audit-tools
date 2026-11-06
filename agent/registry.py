"""
agent/registry.py — the tool list an AI model will see, and one way to call it.

TOOLS describes each tool (name, plain-English description, JSON schema of
its arguments) in the shape the Claude API expects. run_tool() is the only
way the agent calls a tool: it checks the name and arguments, runs it, and
logs the call to BASE_PATH/logs/agent_YYYYMM.jsonl (tool, arguments,
success, time taken — not the results, which contain staff figures).
"""
import datetime
import json
import logging
import os
import time

from config import BASE_PATH
from agent import tools as T

_PERIOD = {"type": "string", "enum": T.PERIODS,
           "description": "Time period, counted back from today."}

TOOLS = {
    "team_overview": {
        "function": T.team_overview,
        "description": "How the team is doing over a period: team score and grade, slips, "
                       "cash, average slips per hour, bags cleared, 360 and non-VMS days.",
        "parameters": {"period": _PERIOD},
    },
    "targets_vs_actual": {
        "function": T.targets_vs_actual,
        "description": "Each team target, the actual figure, how far off it is (gap and %), "
                       "whether it is met, and who misses it.",
        "parameters": {"period": _PERIOD},
    },
    "cashier_ranking": {
        "function": T.cashier_ranking,
        "description": "Cashiers ordered by score with what cost each of them points "
                       "(slips per hour, cash, accuracy, consistency, penalties). Use "
                       "lowest_first=true for 'who is the weak link'.",
        "parameters": {"period": _PERIOD,
                       "lowest_first": {"type": "boolean"},
                       "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
    },
    "cashier_profile": {
        "function": T.cashier_profile,
        "description": "One cashier in detail: score breakdown, reasons, every day worked, "
                       "mistakes, rank in the team and this month's cash rate.",
        "parameters": {"name": {"type": "string", "description": "Full or partial name."},
                       "period": _PERIOD},
        "required": ["name"],
    },
    "day_summary": {
        "function": T.day_summary,
        "description": "One day: bags in and carried over, team score, best and lowest "
                       "cashiers and why, 360 and non-VMS work, mistakes and confirmed "
                       "duplicates.",
        "parameters": {"date": {"type": "string", "description": "DD.MM.YYYY; today if omitted."}},
    },
    "monthly_cash_leaders": {
        "function": T.monthly_cash_leaders,
        "description": "Highest cash per hour for a month and whether it comes from speed "
                       "(slips per hour) or bigger lodgements (cash per slip).",
        "parameters": {"month": {"type": "string", "description": "YYYY-MM; this month if omitted."},
                       "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
    },
}


def tool_definitions():
    """The tools in Claude API format: [{"name", "description", "input_schema"}]."""
    return [{"name": name, "description": t["description"],
             "input_schema": {"type": "object", "properties": t["parameters"],
                              "required": t.get("required", []),
                              "additionalProperties": False}}
            for name, t in TOOLS.items()]


def _check_args(name, args):
    spec = TOOLS[name]
    unknown = set(args) - set(spec["parameters"])
    if unknown:
        raise T.ToolError(f"{name}: unknown argument(s) {sorted(unknown)}")
    missing = [k for k in spec.get("required", []) if k not in args]
    if missing:
        raise T.ToolError(f"{name}: missing argument(s) {missing}")
    for key, value in args.items():
        schema = spec["parameters"][key]
        if "enum" in schema and value not in schema["enum"]:
            raise T.ToolError(f"{name}: {key} must be one of {schema['enum']}")


def _log(entry, log_dir):
    try:
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, f"agent_{datetime.date.today():%Y%m}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        logging.exception("agent tool log")


def run_tool(name, arguments=None, log_dir=None):
    """Run one tool by name. Returns its result, or {"error": "..."}; never raises."""
    arguments = dict(arguments or {})
    started = time.time()
    entry = {"time": datetime.datetime.now().isoformat(timespec="seconds"),
             "tool": name, "arguments": arguments}
    try:
        if name not in TOOLS:
            raise T.ToolError(f"unknown tool '{name}'. Tools: {', '.join(TOOLS)}")
        _check_args(name, arguments)
        result = TOOLS[name]["function"](**arguments)
        entry["ok"] = True
    except T.ToolError as e:
        result, entry["ok"], entry["error"] = {"error": str(e)}, False, str(e)
    except Exception as e:
        logging.exception(f"agent tool {name}")
        result, entry["ok"], entry["error"] = {"error": f"{type(e).__name__}: {e}"}, False, str(e)
    entry["seconds"] = round(time.time() - started, 3)
    _log(entry, log_dir or os.path.join(BASE_PATH, "logs"))
    return result

"""Command line for the agent toolkit — see agent/__init__.py."""
import json
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__import__("agent").__doc__)
        return 0
    cmd = argv[0]
    if cmd == "summary":
        from agent.summary import end_of_day_summary
        print(end_of_day_summary(date=argv[1] if len(argv) > 1 else None))
        return 0
    if cmd == "tools":
        from agent.registry import tool_definitions
        for t in tool_definitions():
            args = ", ".join(t["input_schema"]["properties"]) or "-"
            print(f"{t['name']:<22} ({args})\n    {t['description']}")
        return 0
    if cmd == "run" and len(argv) >= 2:
        from agent.registry import run_tool
        try:
            args = json.loads(argv[2]) if len(argv) > 2 else {}
        except json.JSONDecodeError as e:
            print(f"Arguments must be JSON, e.g. '{{\"period\": \"This Week\"}}': {e}")
            return 2
        result = run_tool(argv[1], args)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 1 if isinstance(result, dict) and "error" in result else 0
    print(f"Unknown command: {' '.join(argv)}\n")
    print(__import__("agent").__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())

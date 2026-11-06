"""
agent — what the Spectre agent needs, except the AI model itself.

    tools      read-only answers to the manager's questions (from saved history)
    registry   the tool list in Claude API format, and a logged run_tool()
    privacy    swap cashier names for IDs before anything goes online
    summary    the End of Day summary in plain English (no AI needed)

Run from a terminal in the Spectre folder:

    python -m agent summary [DD.MM.YYYY]       End of Day summary
    python -m agent tools                      list the tools
    python -m agent run <tool> ['{"arg": 1}']  run one tool, print JSON
"""

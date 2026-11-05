"""
engine — Spectre's audit logic with no Qt dependency.

The UI pages call into this package, and so can tests, scripts or a local
agent, so everything uses exactly the same rules.

    report     load + normalise a VMS / ISA report
    detection  High Risk Duplicates, Suspicious Patterns, Shared Assets
    archive    history files written after each Integrity Check
"""
from engine.report import Report, ReportError, load_report, summarise
from engine.detection import IntegrityResult, run_integrity_checks
from engine.archive import archive_report

__all__ = [
    "Report", "ReportError", "load_report", "summarise",
    "IntegrityResult", "run_integrity_checks",
    "archive_report",
]

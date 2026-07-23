"""
verdicts.py — Duplicate verdict persistence helpers.

Pure-Python, no Qt dependency.  Shared by integrity.py (which writes
verdicts) and any analytics module that needs to read them.
"""
import datetime
import logging
import os

import pandas as pd

from config import DUPLICATE_VERDICTS_DB


def verdict_key(report_date, op_id, slip, amount) -> str:
    """Return a stable string key for one duplicate group."""
    return f"{report_date}|{op_id}|{slip}|{round(float(amount), 2)}"


def load_verdicts() -> dict:
    """Return {key: 'confirmed' | 'cleared'} from the verdicts CSV."""
    try:
        if os.path.exists(DUPLICATE_VERDICTS_DB):
            vdf = pd.read_csv(DUPLICATE_VERDICTS_DB, dtype=str)
            return dict(zip(vdf["key"].fillna(""), vdf["verdict"].fillna("")))
    except Exception:
        pass
    return {}


def save_verdict(key: str, cashier: str, verdict: str) -> None:
    """Upsert one verdict row into the verdicts CSV."""
    try:
        entry = {
            "key":         key,
            "cashier":     cashier,
            "verdict":     verdict,
            "reviewed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        if os.path.exists(DUPLICATE_VERDICTS_DB):
            vdf = pd.read_csv(DUPLICATE_VERDICTS_DB, dtype=str)
            vdf = vdf[vdf["key"] != key]
            vdf = pd.concat([vdf, pd.DataFrame([entry])], ignore_index=True)
        else:
            vdf = pd.DataFrame([entry])
        vdf.to_csv(DUPLICATE_VERDICTS_DB, index=False)
    except Exception:
        logging.exception("save_verdict")

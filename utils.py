"""
utils.py — small helpers used across pages.

Pure-logic functions (load_db_map, extract_report_date) live in utils_core.py
so they can be tested without a Qt installation.  This module re-exports them
and adds the Qt-dependent helpers (msg_*, open_file_in_default_app).
"""
import logging
import os
import subprocess
import sys

from PySide6.QtWidgets import QMessageBox

from config import DATABASE_FILE, DATE_COL
from utils_core import load_db_map as _load_db_map, extract_report_date as _extract_report_date


def open_file_in_default_app(fp: str):
    """Open a file using the OS's default application."""
    try:
        if sys.platform == 'win32':
            os.startfile(fp)
        elif sys.platform == 'darwin':
            subprocess.run(['open', fp])
        else:
            subprocess.run(['xdg-open', fp])
    except Exception as e:
        logging.error(f"open_file_in_default_app: failed to open '{fp}': {e}")


def load_db_map() -> dict:
    """Load Cashier ID -> Name map from the configured Database.csv."""
    return _load_db_map(DATABASE_FILE)


def extract_report_date(df) -> str:
    """Extract a representative date (DD.MM.YYYY) from a report dataframe."""
    return _extract_report_date(df, date_col_primary=DATE_COL)


# Quick helpers to reduce QMessageBox boilerplate
def msg_info(parent, title, text):
    QMessageBox.information(parent, title, text)


def msg_warn(parent, title, text):
    QMessageBox.warning(parent, title, text)


def msg_err(parent, title, text):
    QMessageBox.critical(parent, title, text)


def msg_yes(parent, title, text):
    return QMessageBox.question(
        parent, title, text,
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No
    ) == QMessageBox.Yes

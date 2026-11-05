"""
config.py — application-wide constants, paths, and version info.

Edit this file to change folder paths, switch between TEST and production
mode, or update SL79 No.3 paths. No business logic lives here.
"""
import os
import sys
import json
import datetime
import logging
from pathlib import Path

# =============================================================================
# LOCAL SETTINGS — site-specific values that must never be committed
# =============================================================================
# Real paths, staff names/IDs and the admin password live in
# local_settings.json (git-ignored), next to config.py — or next to
# Spectre.exe when running a PyInstaller build.
# See local_settings.example.json for the available keys.

def _local_settings_path():
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "local_settings.json")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_settings.json")


LOCAL_SETTINGS_FILE = _local_settings_path()
_LOCAL_SETTINGS_ERROR = None  # logged by setup_logging(); logging isn't ready at import


def _load_local_settings():
    global _LOCAL_SETTINGS_ERROR
    try:
        with open(LOCAL_SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("top level must be a JSON object")
        return data
    except FileNotFoundError:
        return {}
    except Exception as e:
        _LOCAL_SETTINGS_ERROR = f"Could not read {LOCAL_SETTINGS_FILE}: {e}"
        return {}


_LOCAL = _load_local_settings()


def _setting(key, default):
    """Return a value from local_settings.json, or `default` if missing/empty."""
    value = _LOCAL.get(key)
    return default if value in (None, "") else value


# =============================================================================
# APP CONFIG (ported verbatim from v1.6)
# =============================================================================

APP_VERSION = "Spectre v2.0"
VERSION_MODE = "TEST"  # "TEST" → uses Desktop/Audit_System_Files ; else use production path

if VERSION_MODE == "TEST":
    DESKTOP = os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')), 'Desktop')
    BASE_PATH = os.path.join(DESKTOP, "Audit_System_Files")
else:
    BASE_PATH = os.path.normpath(_setting("prod_base_path", r"W:\Work\Path\To\Files\Python"))

REQUIRED_FOLDERS = ["Cashiers Database", "Discrepancies Database",
                    "Slip Audits", "Integrity Reports", "logs"]
for folder in REQUIRED_FOLDERS:
    try:
        os.makedirs(os.path.join(BASE_PATH, folder), exist_ok=True)
    except Exception:
        pass

# Core DB / column names (Integrity module)
DATABASE_FILE = os.path.join(BASE_PATH, "Cashiers Database", "Database.csv")
DISCREPANCY_DB_PATH = os.path.join(BASE_PATH, "Discrepancies Database")
SLIP_AUDIT_PATH = os.path.join(BASE_PATH, "Slip Audits")
SLIP_HISTORY_DB         = os.path.join(SLIP_AUDIT_PATH, "Audit_Database.csv")
PERFORMANCE_HISTORY_DB  = os.path.join(SLIP_AUDIT_PATH, "Performance_History.csv")
# Daily bag numbers entered in the Bag Counter tab (bags in, carried over)
BAG_LOG_DB              = os.path.join(SLIP_AUDIT_PATH, "Bag_Log.csv")
CUSTOMER_DISC_DB      = os.path.join(DISCREPANCY_DB_PATH, "Customer_Discrepancy_DB.csv")
DUPLICATE_VERDICTS_DB = os.path.join(DISCREPANCY_DB_PATH, "duplicate_verdicts.csv")
ALL_DISC_DB           = os.path.join(DISCREPANCY_DB_PATH, "All_Discrepancies_DB.csv")
MISTAKES_DB           = os.path.join(DISCREPANCY_DB_PATH, "mistakes.csv")

# Team targets set by the manager (Settings → Team Targets). Kept under
# BASE_PATH so everyone using the shared folder works to the same targets.
TARGETS_FILE          = os.path.join(BASE_PATH, "targets.json")

# Mistake types and their penalty severity (points deducted from final score)
MISTAKE_TYPES = {
    # A confirmed duplicate is the most serious mistake, so it costs the most
    "duplicate_slip":     {"label": "Duplicate Slip",      "points": 20},
    "miscredit":          {"label": "Miscredit",           "points": 12},
    "money_lost":         {"label": "Money Lost",          "points": 15},
    "slip_not_processed": {"label": "Slip Not Processed",  "points":  8},
    "small_mistake":      {"label": "Small Mistake",       "points":  3},
}

EXPECTED_TOTAL = "Expected Total"
OPERATOR = "Operator Id"
WALLET = "Wallet Number"
LODGEMENT = "Lodgement Slip Number"
AMOUNT = "Total Processed"
COL_DISC = "Discrepancy"
DATE_COL = "Processed Date"
CUSTOMER_ID  = "Customer ID"
CUSTOMER_LOC = "Customer Location"

# NON-VMS config
NON_VMS_CONFIG = {
    "Cork":     {"tickets": ("C", 7, 34),  "amounts": {"500": 0, "200": 0, "100": "I13", "50": "I14", "20": "I15", "10": "I16", "5": "I17", "Coins": "I19"}},
    "Dublin":   {"tickets": ("C", 7, 214), "amounts": {"500": 0, "200": 0, "100": "I9",  "50": "I10", "20": "I11", "10": "I12", "5": "I13"}},
    "Galway":   {"tickets": ("C", 7, 45),  "amounts": {"500": 0, "200": 0, "100": 0,     "50": "I9",  "20": "I10", "10": "I11", "5": "I12", "Coins": "I14"}},
    "Limerick": {"tickets": ("C", 7, 34),  "amounts": {"500": 0, "200": 0, "100": "I9",  "50": "I10", "20": "I11", "10": "I12", "5": "I13", "Coins": "I15"}},
    "Sligo":    {"tickets": ("C", 7, 30),  "amounts": {"500": 0, "200": 0, "100": "I9",  "50": "I10", "20": "I11", "10": "I12", "5": "I13", "Coins": "I15"}},
}
DUBLIN_DSC_AMOUNTS = {"500": 0, "200": 0, "100": 0, "50": "I9", "20": "I10", "10": "I11", "5": "I12"}
NON_VMS_BASE_FOLDER = _setting("non_vms_base_folder", os.path.join(BASE_PATH, "NON VMS", "Irish Rail TVM's"))
JOLLYES_BASE        = _setting("jollyes_base_folder", os.path.join(BASE_PATH, "NON VMS", "Jollyes"))
DBC_FOLDER          = _setting("dbc_folder", os.path.join(BASE_PATH, "DBC's"))
# Text placed before each NON-VMS summary line copied to the clipboard
# (e.g. the name/ID of the person the summary is sent to). Empty by default.
NON_VMS_TEXT_PREFIX = str(_setting("non_vms_text_prefix", ""))

# SL79 No.3 paths
_NO3_DIR          = os.path.join(BASE_PATH, "No. 3 Database")
NO3_DATABASE_PATH = Path(_setting("no3_database_path", os.path.join(_NO3_DIR, "No. 3 Database.xlsx")))
NO3_TEMPLATE_PATH = Path(_setting("no3_template_path", os.path.join(_NO3_DIR, "SL Template.xlsx")))
NO3_TRACKER_DIR   = Path(_setting("no3_tracker_dir", _NO3_DIR))
NO3_OUTPUT_BASE   = Path(_setting("no3_output_base", os.path.join(BASE_PATH, "SL79 forms")))
NO3_ALLOWED_YEARS = [str(y) for y in range(2026, 2031)]

# Operators who work 10-hour shifts (everyone else is scored on 8 hours)
TEN_HOUR_OP_IDS = frozenset(str(x).strip() for x in _setting("ten_hour_operator_ids", []))

# Password for the Cashier Database "danger zone" delete buttons.
# If not set, those buttons stay locked.
ADMIN_PASSWORD = str(_setting("admin_password", ""))


# =============================================================================
# LOGGING
# =============================================================================
def setup_logging():
    """Initialise the rotating log file in BASE_PATH/logs/.
    Called once from main.py at startup."""
    log_dir = os.path.join(BASE_PATH, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"spectre_{datetime.date.today().strftime('%Y%m')}.log")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-7s | %(message)s',
        handlers=[logging.FileHandler(log_file, encoding='utf-8'), logging.StreamHandler()]
    )
    logging.info("=" * 60)
    logging.info(f"{APP_VERSION} starting (mode={VERSION_MODE})")
    if _LOCAL_SETTINGS_ERROR:
        logging.warning(_LOCAL_SETTINGS_ERROR)
    elif not _LOCAL:
        logging.info(f"No local settings found at {LOCAL_SETTINGS_FILE} — using defaults")


# =============================================================================
# OPTIONAL .xls SUPPORT
# =============================================================================
try:
    import xlrd  # noqa: F401
    XLRD_AVAILABLE = True
except ImportError:
    XLRD_AVAILABLE = False

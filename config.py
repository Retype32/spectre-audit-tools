"""
config.py — application-wide constants, paths, and version info.

Edit this file to change folder paths, switch between TEST and production
mode, or update SL79 No.3 paths. No business logic lives here.
"""
import os
import datetime
import logging
from pathlib import Path

# =============================================================================
# APP CONFIG (ported verbatim from v1.6)
# =============================================================================

APP_VERSION = "Spectre v2.0"
VERSION_MODE = "TEST"  # "TEST" → uses Desktop/Audit_System_Files ; else use production path

if VERSION_MODE == "TEST":
    DESKTOP = os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')), 'Desktop')
    BASE_PATH = os.path.join(DESKTOP, "Audit_System_Files")
else:
    BASE_PATH = os.path.normpath(r"W:\Work\Path\To\Files\Python")

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
CUSTOMER_DISC_DB      = os.path.join(DISCREPANCY_DB_PATH, "Customer_Discrepancy_DB.csv")
DUPLICATE_VERDICTS_DB = os.path.join(DISCREPANCY_DB_PATH, "duplicate_verdicts.csv")
ALL_DISC_DB           = os.path.join(DISCREPANCY_DB_PATH, "All_Discrepancies_DB.csv")
MISTAKES_DB           = os.path.join(DISCREPANCY_DB_PATH, "mistakes.csv")

# Mistake types and their penalty severity (points deducted from final score)
MISTAKE_TYPES = {
    "duplicate_slip":     {"label": "Duplicate Slip",      "points": 12},
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
NON_VMS_BASE_FOLDER = r"I:\Brinks\NON VMS\Irish Rail TVM's"
JOLLYES_BASE = r"I:\Brinks\NON VMS\Jollyes"

# SL79 No.3 paths
NO3_DATABASE_PATH = Path(r"C:\Users\OTsiampas\Desktop\Files\Python\No. 3 Database\No. 3 Database.xlsx")
NO3_TEMPLATE_PATH = Path(r"C:\Users\OTsiampas\Desktop\Files\Python\No. 3 Database\SL Template.xlsx")
NO3_TRACKER_DIR   = Path(r"C:\Users\OTsiampas\Desktop\Files\Python\No. 3 Database")
NO3_OUTPUT_BASE   = Path(r"P:\DMS\11. SL79 no 3 account\SL79 forms")
NO3_ALLOWED_YEARS = [str(y) for y in range(2026, 2031)]


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


# =============================================================================
# OPTIONAL .xls SUPPORT
# =============================================================================
try:
    import xlrd  # noqa: F401
    XLRD_AVAILABLE = True
except ImportError:
    XLRD_AVAILABLE = False

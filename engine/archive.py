"""
engine/archive.py — history files written every time a report is checked.

Pure pandas, no Qt. Moved unchanged from the Integrity Check page; each
function takes its destination as a parameter (defaulting to the configured
location) so it can be tested against a temporary folder.

Every writer is idempotent per report date: re-running the same report
replaces that date's rows instead of adding them twice. Errors are logged,
never raised, so a failed archive can't block the Integrity Check.
"""
import datetime
import logging
import os

import pandas as pd

from config import (ALL_DISC_DB, AMOUNT, COL_DISC, CUSTOMER_DISC_DB, CUSTOMER_ID,
                    CUSTOMER_LOC, DISCREPANCY_DB_PATH, EXPECTED_TOTAL, OPERATOR,
                    PERFORMANCE_HISTORY_DB)

SMALL_DISC_LIMIT = 10      # € — discrepancies up to this are "small"


def archive_small_discrepancies(df, report_date, base_dir=DISCREPANCY_DB_PATH):
    """Per-cashier count of small (€0.01–€10) discrepancies →
    base_dir/YYYY/MM/DD.MM.YYYY.xlsx (feeds the History tab)."""
    if COL_DISC not in df.columns: return
    try:
        df = df.copy()
        df[COL_DISC] = pd.to_numeric(df[COL_DISC], errors='coerce').fillna(0)
        disc = df[(df[COL_DISC].abs() > 0) & (df[COL_DISC].abs() <= SMALL_DISC_LIMIT)].copy()
        if disc.empty: return
        try: pd_date = datetime.datetime.strptime(report_date, "%d.%m.%Y")
        except Exception: pd_date = datetime.datetime.now()
        folder = os.path.join(base_dir, pd_date.strftime("%Y"), pd_date.strftime("%m"))
        os.makedirs(folder, exist_ok=True)
        fp = os.path.join(folder, f"{report_date.replace('/', '.')}.xlsx")
        sm = disc.groupby(['Cashier Name', OPERATOR]).size().reset_index(name='Small_Discrepancies')
        sm['Report_Date'] = report_date
        sm.to_excel(fp, index=False)
    except Exception as e:
        logging.error(f"Archive error: {e}")


def archive_customer_discrepancies(df, report_date, db_path=CUSTOMER_DISC_DB):
    """Per-customer discrepancy counts for this report → db_path (CSV)."""
    if COL_DISC not in df.columns or CUSTOMER_ID not in df.columns:
        return
    try:
        df2 = df.copy()
        df2[COL_DISC] = pd.to_numeric(df2[COL_DISC], errors='coerce').fillna(0)
        df2[AMOUNT]   = pd.to_numeric(df2[AMOUNT],   errors='coerce').fillna(0)
        rows = []
        for cid, grp in df2.groupby(CUSTOMER_ID):
            loc = ''
            if CUSTOMER_LOC in grp.columns:
                loc_series = grp[CUSTOMER_LOC].dropna().astype(str)
                loc = loc_series.mode().iloc[0] if not loc_series.empty else ''
            small    = grp[(grp[COL_DISC].abs() > 0) & (grp[COL_DISC].abs() <= SMALL_DISC_LIMIT)]
            all_disc = grp[grp[COL_DISC].abs() > 0]
            not_decl = grp[(grp[AMOUNT] > 0) &
                           ((grp[COL_DISC].abs() - grp[AMOUNT].abs()).abs() < 0.01)]
            rows.append({
                'Customer_Id':         str(cid),
                'Customer_Location':   loc,
                'Report_Date':         str(report_date),
                'Total_Transactions':  len(grp),
                'All_Discrepancies':   len(all_disc),
                'Small_Disc_Count':    len(small),
                'Small_Disc_Amount':   round(float(small[COL_DISC].abs().sum()), 2),
                'Not_Declaring_Count': len(not_decl),
            })
        if not rows:
            return
        new_df = pd.DataFrame(rows).astype(str)
        if os.path.exists(db_path):
            try:
                existing = pd.read_csv(db_path, dtype=str)
                existing = existing[existing['Report_Date'] != str(report_date)]
                combined = pd.concat([existing, new_df], ignore_index=True)
            except Exception:
                combined = new_df
        else:
            combined = new_df
        combined.to_csv(db_path, index=False)
    except Exception as e:
        logging.error(f"Customer disc archive error: {e}")


def _clean_id(v):
    """Convert float IDs like 12345678.0 → '12345678'."""
    try:
        f = float(v)
        return str(int(f)) if not pd.isna(f) else str(v)
    except (ValueError, TypeError):
        return str(v)


def archive_all_discrepancies(df, report_date, db_path=ALL_DISC_DB):
    """Every non-zero Discrepancy row from this report → db_path (CSV).
    Rows with no Expected Total are typed "Blind Count"."""
    if COL_DISC not in df.columns:
        return
    try:
        disc_df = df.copy()
        disc_df[COL_DISC] = pd.to_numeric(disc_df[COL_DISC], errors='coerce').fillna(0)
        disc_df = disc_df[disc_df[COL_DISC] != 0].copy()
        if disc_df.empty:
            return

        exp_col = EXPECTED_TOTAL if EXPECTED_TOTAL in disc_df.columns else None

        rows = []
        for _, row in disc_df.iterrows():
            exp_val = pd.to_numeric(row.get(exp_col, 0), errors='coerce') if exp_col else 0
            exp_val = 0.0 if pd.isna(exp_val) else round(float(exp_val), 2)
            disc_type = "Blind Count" if exp_val == 0 else "Discrepancy"
            rows.append({
                "Report Date":      str(report_date),
                "Customer ID":      _clean_id(row.get(CUSTOMER_ID, "")),
                "Customer Location":str(row.get(CUSTOMER_LOC, "")),
                "Expected Total":   exp_val,
                "Total Processed":  round(float(pd.to_numeric(row.get(AMOUNT, 0), errors='coerce') or 0), 2),
                "Discrepancy":      round(float(row[COL_DISC]), 2),
                "Operator ID":      _clean_id(row.get(OPERATOR, "")),
                "Cashier Name":     str(row.get("Cashier Name", "")),
                "Type":             disc_type,
            })

        new_df = pd.DataFrame(rows)
        if os.path.exists(db_path):
            try:
                existing = pd.read_csv(db_path, dtype=str)
                existing = existing[existing["Report Date"] != str(report_date)]
                combined = pd.concat([existing, new_df], ignore_index=True)
            except Exception:
                combined = new_df
        else:
            combined = new_df
        combined.to_csv(db_path, index=False)
        logging.info(f"All-discrepancies archive: {len(rows)} rows for {report_date}")
    except Exception as e:
        logging.error(f"All-disc archive error: {e}")


def save_performance_history(df, report_date, db_path=PERFORMANCE_HISTORY_DB, fmt="VMS"):
    """Per-cashier slip count and total value for this report → db_path (CSV).

    `fmt` ("VMS" or "ISA") is stored too, so a VMS and an ISA report for the
    same date don't overwrite each other. Older rows without a Format count
    as VMS."""
    try:
        if "Cashier Name" not in df.columns:
            return

        row_date = report_date  # already extracted at load time

        rows = []
        for name, grp in df.groupby("Cashier Name"):
            txn_count = len(grp)
            total_val = float(grp[AMOUNT].sum()) if AMOUNT in df.columns else 0.0
            op_id = ""
            if OPERATOR in grp.columns:
                op = grp[OPERATOR].mode()
                op_id = str(op.iloc[0]).strip() if not op.empty else ""
            rows.append({
                "Date":         row_date,
                "Name":         str(name),
                "Operator_Id":  op_id,
                "System Count": txn_count,
                "Total Value":  round(total_val, 2),
                "Format":       fmt,
            })

        if not rows:
            return

        new_df = pd.DataFrame(rows)

        if os.path.exists(db_path):
            try:
                existing = pd.read_csv(db_path, dtype=str)
                if "Format" not in existing.columns:
                    existing["Format"] = "VMS"
                existing["Format"] = existing["Format"].fillna("VMS")
                same = (existing["Date"] == str(row_date)) & (existing["Format"] == fmt)
                existing = existing[~same]
                combined = pd.concat([existing, new_df.astype(str)], ignore_index=True)
            except Exception:
                combined = new_df.astype(str)
        else:
            combined = new_df.astype(str)

        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        combined.to_csv(db_path, index=False)
        logging.info(f"Performance history saved: {len(rows)} cashiers for {row_date}")

    except Exception:
        logging.exception("Unhandled exception")


def archive_report(df, report_date, fmt="VMS"):
    """Write all history files for a checked report (configured locations)."""
    archive_small_discrepancies(df, report_date)
    archive_customer_discrepancies(df, report_date)
    archive_all_discrepancies(df, report_date)
    save_performance_history(df, report_date, fmt=fmt)

# Spectre v2.0 — Audit Intelligence Platform

**Spectre** is a desktop audit tool for cash-handling operations. It processes VMS and ISA transaction reports, detects integrity violations, tracks discrepancies over time, audits physical slip counts against system records, and auto-generates SL79 statutory forms. All data stays local — no network connection required.

---

## Table of Contents

1. [First-Time Setup](#1-first-time-setup)
2. [Folder Structure](#2-folder-structure)
3. [Tab Reference](#3-tab-reference)
   - [Integrity Check](#31-integrity-check)
   - [Targeted Search](#32-targeted-search)
   - [Universal Search](#33-universal-search)
   - [Slip Audit](#34-slip-audit)
   - [Bag Counter](#35-bag-counter)
   - [History](#36-history)
   - [Cashier Database](#37-cashier-database)
   - [NON-VMS Reports](#38-non-vms-reports)
   - [Amount Discovery](#39-amount-discovery)
   - [No.3 Account](#310-no3-account)
4. [Settings](#4-settings)
5. [File Format Reference](#5-file-format-reference)
6. [Workflow Guide](#6-workflow-guide)
7. [Troubleshooting](#7-troubleshooting)
8. [For Developers](#8-for-developers)

---

## 1. First-Time Setup

### Requirements

```
Python 3.10+
PySide6
pandas
openpyxl
xlrd        (optional — only needed for legacy .xls files)
```

Install dependencies:

```bash
pip install PySide6 pandas openpyxl xlrd
```

### Running the App

```bash
cd Spectre_v2
python main.py
```

### Building Spectre.exe (no Python needed on the PC that runs it)

On a Windows PC with Python 3.10 or newer, double-click **`build_exe.bat`** in the Spectre folder. It installs what the build needs, runs the tests and creates **`dist\Spectre.exe`** — one file with everything inside.

Copy `Spectre.exe` to the shared Spectre folder and put `local_settings.json` next to it; anyone can then start Spectre by double-clicking it. Rebuild after each update to the code. The first start of the `.exe` takes a few seconds while it unpacks.

### TEST vs Production Mode

Open `config.py` and find the `VERSION_MODE` constant near the top:

```python
VERSION_MODE = "TEST"   # uses Desktop\Audit_System_Files
# VERSION_MODE = "PROD" # uses W:\Work\Path\To\Files\Python
```

In **TEST** mode, Spectre creates all its working folders on your Desktop inside a folder called `Audit_System_Files`. This is safe for evaluation and does not touch any network drives.

In production mode, set `prod_base_path` in `local_settings.json` (see below) to point to your shared network location.

### Local settings (paths, IDs, password)

Anything specific to your site — real folder paths, staff names/IDs and the admin password — lives in `local_settings.json`, **not** in the code. This file is git-ignored so it never ends up in the repository.

1. Copy `local_settings.example.json` to `local_settings.json` in the same folder as `config.py` (or next to `Spectre.exe` for a packaged build).
2. Fill in the values you need. Any key you leave out falls back to a folder under `BASE_PATH`.

| Key | Used by |
|-----|---------|
| `prod_base_path` | `BASE_PATH` when `VERSION_MODE` is not `"TEST"` |
| `non_vms_base_folder`, `jollyes_base_folder`, `dbc_folder` | NON-VMS Reports default paths |
| `non_vms_text_prefix` | Text placed before each NON-VMS summary line copied to the clipboard |
| `no3_database_path`, `no3_template_path`, `no3_tracker_dir`, `no3_output_base` | No.3 Account tab |
| `ten_hour_operator_ids` | Operator IDs scored on a 10-hour shift (everyone else is 8 hours) |
| `admin_password` | Cashier Database danger-zone buttons (locked if not set) |

> **Never commit real data.** Reports, slip audits, cashier databases and any file with staff names or figures must stay out of the repository. `.gitignore` already excludes `local_settings.json`, `.xlsx`, `.xls`, `.csv` and `.pdf` files.

---

## 2. Folder Structure

Spectre creates and manages the following folder structure automatically under `BASE_PATH`:

```
Audit_System_Files\
├── Cashiers Database\
│   └── Database.csv              ← cashier ID → name mapping
├── Discrepancies Database\
│   └── YYYY\
│       └── MM\
│           └── DD.MM.YYYY.xlsx   ← auto-archived small discrepancies per report
├── Slip Audits\
│   └── Audit_Database.csv        ← cumulative slip audit history
├── Integrity Reports\            ← reserved for future exports
└── logs\
    └── spectre_YYYYMM.log        ← rotating monthly log file
```

You do not need to create any of these folders — Spectre creates them on first run.

---

## 3. Tab Reference

---

### 3.1 Integrity Check

**Purpose:** The core audit tab. Loads a transaction report (VMS or ISA format), runs three automated detection algorithms, and surfaces anomalies as clickable stat cards and sortable tables.

#### How to use

1. Click **Import Report** and select an `.xlsx`, `.xls`, or `.csv` transaction file.
2. Spectre auto-detects whether the file is VMS or ISA format by scanning the first 15 rows for known header signatures (`Container Seal`, `Lodgement Number`).
3. The top bar updates with: filename, report date, row count, number of unique cashiers, and total processed value.
4. Three stat cards update with detection counts. Click any card to open a full filtered view of all matching rows.
5. Double-click any row in either table to open a **Detail Dialog** with the full transaction record.

#### Detection algorithms

| Card | What it detects |
|------|----------------|
| **High Risk Duplicates** | Rows that are fully identical across Operator ID, Wallet Number, Lodgement Slip, Amount, and all denomination columns. These represent probable duplicate lodgements — the same bag processed twice. |
| **Suspicious Patterns** | Rows sharing the same Operator + Wallet + Amount but differing on other fields. Less certain than High Risk, but flags repeated amounts that may indicate patterns of manipulation. |
| **Shared Assets** | Wallet numbers used by more than one Operator ID within the same report. A wallet should belong to a single cashier — shared wallets may indicate credential sharing or data entry errors. |

#### Small discrepancy archiving

When a report is loaded, Spectre silently scans for a `Discrepancy` column. Any rows with a discrepancy value between €0.01 and €10.00 are automatically archived to `Discrepancies Database\YYYY\MM\` as an Excel file. This data feeds the **History** tab.

> **Note:** After importing here, the cashier list in **Targeted Search** is automatically populated from the loaded report.

---

### 3.2 Targeted Search

**Purpose:** Forensic amount-based search against the currently-loaded report. Given a target amount, it simultaneously searches for exact matches, near-matches within a tolerance, half the amount, and double the amount — the four most common patterns in split-lodgement fraud.

#### How to use

1. A report must already be loaded in **Integrity Check** first.
2. Select a cashier from the dropdown (or leave as **ALL** to search the whole report).
3. Enter a target amount (e.g. `500.00`).
4. Optionally set a **± Tolerance** (e.g. `5` to catch amounts between €495 and €505).
5. Click **Search**.

#### Result panels

| Panel | What it shows |
|-------|--------------|
| **Exact Matches** | All rows where Amount = target exactly. |
| **Tolerance Range** | Rows within ± tolerance of the target, excluding exact matches. The `Diff` column shows how far each row is from the target. |
| **Halved Amount** | Rows where Amount = target ÷ 2. Catches split-lodgement patterns where a large bag was split into two smaller ones. |
| **Doubled Amount** | Rows where Amount = target × 2. Useful for catching consolidation anomalies. |

Double-click any row to open the full transaction detail.

---

### 3.3 Universal Search

**Purpose:** Freeform search across any loaded report, independent of Integrity Check. Lets you load a separate file and search any column by any value — useful for looking up a specific slip number, wallet, operator ID, or any other field without running a full integrity scan.

#### How to use

1. Click **Load Report** to load any VMS or ISA file (independent of Integrity Check's loaded file).
2. Set the **Mode**:
   - **All Columns** — searches every column simultaneously for the query value.
   - **Specific Column** — restricts the search to a single column you pick from the dropdown.
3. Type a query in the **Query** field. Matching is:
   - **Exact** for numeric values (e.g. `100.00` matches 100.00, not 1000.00).
   - **Case-insensitive** for text (e.g. `abc-9876` matches `ABC-9876`).
4. Click **Search** or press Enter.
5. Click **Clear** to reset results without reloading the file.

---

### 3.4 Slip Audit

**Purpose:** Reconciles the system's slip counts against physical counts performed during a cash audit. For each cashier in a report, you enter how many physical slips were counted; Spectre computes the difference and saves a permanent audit record.

#### How to use

1. Click **Load Report** and select a transaction file.
2. Spectre reads the report and creates one row per cashier, showing:
   - **Cashier name** (resolved from the Cashier Database if available)
   - **System count** — number of transactions in the report for that cashier
   - **Physical count** input field — editable, enter the count from the physical audit
3. Fill in physical counts for each cashier.
4. Click **Save Audit** when done.

Spectre computes `Difference = Physical − System` for each cashier and saves the full audit record to `Slip Audits\Audit_Database.csv`. This record is browsable in the **History** tab.

> **Tip:** Cashiers with no discrepancy will show `0`. Negative values mean fewer physical slips than system records — a significant red flag.

---

### 3.5 Bag Counter

**Purpose:** Counts unique bags, total slips, coin totals, and overall transaction value from a report. Works in two modes to accommodate different report formats.

#### How to use

1. Select a **Mode** from the dropdown:
   - **VMS (Full Audit + Bags)** — for standard VMS reports with full denomination breakdown.
   - **Other (Bags + Coins + Slips)** — for ISA or non-standard reports with a simpler structure.
2. Click **Load Report** and select your file.
3. The four stat tiles update automatically:

| Tile | What it shows |
|------|--------------|
| **Unique Bags** | Number of distinct wallet/bag numbers in the report. |
| **Total Slips** | Total number of lodgement slips processed. |
| **Total Coins** | Sum of coin-denomination values across all transactions. |
| **Total Amount** | Grand total of all processed amounts in the report. |

The detail table below the tiles breaks down results per cashier or location.

#### Daily Bag Log

At the bottom of the tab, record each day's **Bags in** and **Carried over** (bags not processed that day) and click **Save Day**. Loading a report moves the date to that report's date. The log is one shared file (`Slip Audits\Bag_Log.csv`), so the whole team sees the same numbers; the table shows the last 14 logged days with the completion % and whether the day was **cleared**.

A day is cleared when no more bags were carried over than the allowed number (Settings → Team Targets, 0 by default). On a cleared day the team ran out of work, so the slips-per-hour target for that day drops to the pace the team actually managed — a quiet day where every bag was processed scores well.

---

### 3.6 History

**Purpose:** Two-panel historical view. Left panel queries accumulated small discrepancy records across any date range. Right panel browses saved slip audit records.

#### Discrepancy History (left panel)

1. Enter a **From** and **To** date in `DD.MM.YYYY` format.
2. Click **Search**.
3. Results show each cashier name alongside a count of small discrepancy events recorded during that period.
4. Double-click a cashier row to see the individual discrepancy records.

This data comes from the automatic archiving that happens every time a report is imported in Integrity Check. No manual action is required to build up this history — it accumulates passively.

#### Slip Audit History (right panel)

Displays all previously saved slip audits from `Audit_Database.csv`, with the most recent at the top. Each row shows the report date, cashier, system count, physical count, and difference. Rows with non-zero differences are highlighted.

Use the **Delete** button to permanently remove a specific audit record after confirmation.

---

### 3.7 Cashier Database

**Purpose:** Manages the ID → Name mapping used across the app to resolve operator IDs to human-readable cashier names. Without entries here, the app displays raw operator IDs instead of names.

#### Adding cashiers

- Enter the **Cashier ID** (numeric, as it appears in reports) and **Name**, then click **Add**.
- The ID is normalised automatically (e.g. `1234.0` becomes `1234`).
- Duplicate IDs are rejected with a warning.

#### Bulk import

Click **Import CSV** and select a CSV file. The file must have columns identifiable as ID and Name — the importer recognises common column names including `Number`, `ID`, `Cashier ID`, `Operator ID`, `Name`, `Cashier Name`, `Operator`. Only new IDs are imported; existing ones are kept.

#### Export

Click **Export CSV** to save the current database to a CSV file of your choice.

#### Filtering

Type in the **Filter** box to instantly filter the list by name or ID.

#### Deleting entries

Double-click any row to open a confirmation prompt to delete that cashier.

#### Danger zone

Three delete buttons at the top require the **admin password** (set as `admin_password` in `local_settings.json`) followed by a confirmation prompt. If no password is configured, the buttons stay locked.

| Button | What it deletes |
|--------|----------------|
| **Delete Discrepancies** | All files in the Discrepancies Database folder (History left panel). |
| **Delete Slip History** | The `Audit_Database.csv` file (History right panel). |
| **Delete All Cashiers** | The entire `Database.csv` cashier mapping. |

> These actions are irreversible. The password is a safeguard against accidental deletion.

---

### 3.8 NON-VMS Reports

**Purpose:** Processes non-VMS location reports (Irish Rail TVM and Jollyes) for a given date. Scans source folders, extracts denomination breakdowns from Excel workbooks, fills them into standardised templates, and copies the completed files to an output folder.

#### How to use

1. Enter a **Scan Date** in `DD/MM/YYYY` format — the date of the reports to process.
2. Select the **Year** from the dropdown.
3. Optionally enter a **DBC Date** if a DBC (Daily Banking Count) file is also being processed.
4. Verify the three paths are correct:
   - **IR Path** — root folder containing Irish Rail TVM report files.
   - **Jollyes** — root folder for Jollyes reports.
   - **Copy To** — destination folder where completed reports will be saved (defaults to `Desktop\NON VMS Reports`).
5. Click **Scan Files**.

Spectre scans the source folders for files matching the scan date, reads denomination data from each workbook using the cell mappings defined in `config.py` per location (Cork, Dublin, Galway, Limerick, Sligo), and writes the processed output to the Copy To path.

Results appear in the table below, showing each file processed, its location, status, and any errors encountered. Double-click a result row to open the output file directly.

#### Location configuration

Denomination cell mappings per location are defined in `config.py` under `NON_VMS_CONFIG`. If a location's report layout changes (i.e. amounts move to different cells), update the cell references there — no code changes needed.

---

### 3.9 Amount Discovery

**Purpose:** Searches across all IR (Irish Rail) reports in a date range for specific amounts, location IDs, or location names. Useful for tracing a specific transaction or verifying whether an amount appears across multiple reports.

#### How to use

1. Enter a **Start** and **End** date in `DD/MM/YYYY` format.
2. Select the **Year**.
3. Optionally fill in one or more filters:
   - **Location ID** — exact numeric match.
   - **Loc Name** — partial, case-insensitive text match against location name.
   - **Amount** — exact numeric match.
4. Click **Search**.

> The search uses the **IR Path** set on the NON-VMS Reports tab. Set that path first.

Results show every matching row across all scanned files, with the source file name, date, location, and amount. Double-click a row to see the full record. Click **Clear** to reset without clearing the filter fields.

---

### 3.10 No.3 Account

**Purpose:** Automates the creation of SL79 No.3 Account statutory forms. Reads entries from a master database Excel file, fills them into an SL79 template, and saves completed forms to the designated DMS output folder.

#### How to use

1. Select the **Year** (2026–2030).
2. Verify or update the three paths:
   - **Database** — the master `No. 3 Database.xlsx` file containing the entries to process.
   - **Template** — the `SL Template.xlsx` file used as the base for each generated form.
   - Output destination is set via `no3_output_base` in `local_settings.json`.
3. Review the entries shown in the preview table.
4. Click **Generate Forms** to produce the SL79 documents.

Generated forms are saved to the `no3_output_base` folder (default: `SL79 forms` under `BASE_PATH`). A tracker file is also updated in `no3_tracker_dir` to record which entries have been processed.

> **Important:** Set `no3_database_path`, `no3_template_path`, `no3_tracker_dir` and `no3_output_base` in `local_settings.json` before using this tab in a new environment.

---

## 4. Settings

Click **⚙ Settings** at the very bottom of the sidebar to open the Settings page.

### Typography

Choose the interface font from five presets. The change applies immediately — no restart required.

| Preset | UI Font | Mono Font | Character |
|--------|---------|-----------|-----------|
| DM Sans | DM Sans | DM Mono | Geometric, modern |
| Jakarta | Plus Jakarta Sans | JetBrains Mono | Confident, slightly quirky |
| IBM Plex | IBM Plex Sans | IBM Plex Mono | Engineering, terminal feel |
| Roboto | Roboto | Roboto Mono | Neutral, clean |
| Segoe UI | Segoe UI | Consolas | Windows native, always available |

Fonts marked with a non-system name (DM Sans, Jakarta, IBM Plex, Roboto) must be installed to take full effect. Download them free from [fonts.google.com](https://fonts.google.com), unzip, select all `.ttf` files, right-click → **Install for all users**, then restart Spectre.

### Color Theme

Full color themes are scaffolded for a future release. The current active theme is **Deep Obsidian** — a black-to-navy palette with blue accent tones throughout.

### Team Targets

The targets and rules the team works to, set by the manager. Type a number in each box you want to change, leave the rest empty to use the default shown in the box, and click **Save Targets**.

- Everything is saved in **one shared file**, `targets.json` in the Spectre folder (`BASE_PATH`), so everyone who runs Spectre from the same shared folder works to the same numbers. Opening Settings again shows changes someone else saved.

| Setting | Default | What it does |
|---------|---------|--------------|
| **Slips per hour (VMS)** | 25 | Every regular VMS cashier's target. Daily volume follows from shift length (200 for 8 hours, 250 for 10 hours). Used in the score. |
| **Team score** | none | Compared with the team's average score. |
| **Lowest acceptable cashier score** | none | Cashiers below it are listed when comparing against targets. |
| **Bags carried over per day** | 0 | A day with no more carry-over than this is *cleared*, which lowers that day's slips-per-hour target to the pace the team managed. |
| **360: average cash per slip of at least** | €10,000 | With the next rule, marks a cashier's day as 360 processing. |
| **360: no more than this many slips** | 100 | A day with more slips is never treated as 360. |

### Data Maintenance

**Fix History IDs** repairs history saved by older versions, where a report with one blank Operator Id stored IDs like `1001.0` and those cashiers showed up as numbers. It turns the IDs back into plain numbers and puts names back from the Cashier Database. Every file it changes is backed up first (`<file>.bak-<date>`), and running it again changes nothing.

### How cashier scores work

Each cashier's working day is scored out of 90, and multi-day periods add up to 10 for consistency:

| Part | Points | Measured against |
|------|--------|------------------|
| Slips per hour | 50 | The slips-per-hour target (25), or the team's pace on a cleared day. Capped at 100%. |
| Cash volume | 10 | The team's average cash per hour that day, capped at 100%. Keeping up with the team's cash counts a little; slips always count more. |
| Accuracy | 20 | Logged mistakes per slip. |
| Clean ratio | 10 | Share of slips with no mistake. |
| Consistency | 10 | How steady the daily scores are (multi-day periods only). |

Mistake penalties are then taken off. A **confirmed duplicate** is the most serious (−20), then money lost (−15), miscredit (−12), slip not processed (−8) and small mistake (−3). Mistakes on days that weren't scored still count against the period.

**Not scored:** 360 processing days (few slips with very high cash per slip — see the 360 rules above) and non-VMS days such as ISA. They are listed under the team score and don't affect the team's averages.

**Monthly Cash Volume** (button on the Cashier Performance tab) shows each cashier's cash per hour for a month, and why: *Speed ±%* compares their slips per hour with the team, *Size ±%* compares their cash per slip. 360 and non-VMS days are shown separately.

---

## 5. File Format Reference

### VMS Reports

Standard transaction export from the VMS cash management system. Expected columns include:

| Column | Description |
|--------|-------------|
| `Operator Id` | Numeric cashier identifier |
| `Wallet Number` | Bag/wallet identifier |
| `Lodgement Slip Number` | Slip reference |
| `Total Processed` | Transaction amount (€) |
| `Discrepancy` | Variance between expected and counted (€) |
| `Processed Date` | Transaction date |
| Denomination columns | `100`, `50`, `20`, `10`, `5`, `2`, `1`, `0.5`, `0.2` |

### ISA Reports

Irish Rail ISA format. Spectre detects this format by finding `Container Seal` or `Lodgement Number` header text in the first 15 rows. Columns are remapped internally:

| ISA column | Maps to |
|------------|---------|
| `User` | `Operator Id` |
| `Seal` | `Wallet Number` |
| `Lodgement Number` | `Lodgement Slip Number` |
| `Counted` | `Total Processed` |

### Cashier Database CSV

Two required columns: `Number` (cashier ID) and `Name`. Additional columns are ignored on import.

---

## 6. Workflow Guide

### Daily audit workflow

```
1. Open Spectre
2. Integrity Check → Import Report
   ↳ Reviews High Risk Duplicates, Suspicious Patterns, Shared Assets
   ↳ Small discrepancies auto-archived to History
3. Targeted Search → enter any suspicious amounts for deeper analysis
4. Slip Audit → Load same report → enter physical counts → Save Audit
5. Bag Counter → Load report → verify bag/slip/coin totals
```

### Weekly NON-VMS workflow

```
1. NON-VMS Reports → set Scan Date to the target date → Scan Files
2. Amount Discovery → enter date range → search for specific amounts if needed
3. History → Discrepancy History → check the week's range for patterns
```

### SL79 forms (monthly/as required)

```
1. No.3 Account → verify Database and Template paths
2. Select year → review entries → Generate Forms
3. Forms saved automatically to DMS output folder
```

### Building up cashier history

```
1. Cashier Database → Import CSV (one-time bulk import)
2. Add individual cashiers manually as needed
3. History → Discrepancy History accumulates automatically as reports are imported
```

---

## 7. Troubleshooting

### "Missing Column" error on import

The report doesn't have the expected `Operator Id` or `Total Processed` columns. Check that:
- You're importing the correct file type (VMS or ISA).
- The file hasn't been manually edited in a way that renamed columns.
- For ISA files, the header row containing `Container Seal` or `Lodgement Number` is still intact in the first 15 rows.

### Cashier names showing as numbers

The Cashier Database doesn't have an entry for that operator ID. Go to **Cashier Database** and add the entry, or use **Import CSV** to bulk-load a mapping file.

If names show as numbers ending in `.0` (e.g. `1001.0`) in history saved by an older version, run **Settings → Data Maintenance → Fix History IDs**. New imports are no longer affected: a blank `Operator Id` cell used to make the whole column load as decimals.

### NON-VMS scan finds no files

- Verify the **IR Path** and **Jollyes** paths point to the correct folders.
- Check that files for the scan date exist in those folders and follow the expected naming convention.
- Ensure the **Scan Date** format is exactly `DD/MM/YYYY`.

### History shows no discrepancy data

Discrepancy data is only archived when a report with a `Discrepancy` column is imported in **Integrity Check**. If your reports don't include that column, or if all discrepancies are outside the €0.01–€10.00 range, nothing will be archived.

### No.3 Account paths not found

Without a `local_settings.json`, the No.3 paths default to folders under `BASE_PATH`. Set `no3_database_path`, `no3_template_path`, `no3_tracker_dir` and `no3_output_base` in `local_settings.json` to the correct locations for your environment.

### `.xls` files not loading

Install `xlrd`: `pip install xlrd`. This library is required for legacy Excel 97–2003 `.xls` format. Modern `.xlsx` files work without it.

### App won't start — font or display errors

Run from the command line to see the full error output:
```bash
python main.py
```
Common causes: missing PySide6 (`pip install PySide6`), Python version below 3.10, or a corrupted `config.py`.

---

## 8. For Developers

### Code layout

| Folder / file | What's in it |
|---------------|--------------|
| `engine/` | Audit logic with **no Qt dependency**: `report.py` (load + clean VMS/ISA reports), `detection.py` (High Risk Duplicates, Suspicious Patterns, Shared Assets), `archive.py` (history files written after each check), `performance.py` (cashier scores for a period: which days count, each day's targets, team summary, ranking, logging mistakes), `targets.py` (team targets and rules: shared file, validation, actual-vs-target comparison), `bags.py` (daily bag log), `volume.py` (monthly cash volume per cashier), `maintenance.py` (Fix History IDs). |
| `agent/` | The agent toolkit: read-only tools, tool registry, name privacy and the End of Day summary (see below). |
| `scoring.py`, `verdicts.py`, `utils_core.py` | Other Qt-free logic: the per-day score and 360 rule, duplicate verdicts, shared helpers. |
| `pages/`, `widgets/`, `main_window.py` | The PySide6 user interface. Pages call into `engine/` rather than doing the calculations themselves. |

Keep new calculations in `engine/` (or another Qt-free module) so they can be tested and reused by scripts.

### Agent toolkit (`agent/`)

Everything the future AI assistant needs except the model itself. All of it reads the saved history and never writes:

| File | What it does |
|------|--------------|
| `agent/tools.py` | One function per manager question: `team_overview`, `targets_vs_actual`, `cashier_ranking` (with what cost each cashier points), `cashier_profile`, `day_summary`, `monthly_cash_leaders`. |
| `agent/registry.py` | The same tools described in Claude API format, and `run_tool()`, which checks the arguments and logs every call to `logs\agent_YYYYMM.jsonl` (tool, arguments, success — not the figures). |
| `agent/privacy.py` | Swaps cashier names for "Cashier <ID>" before anything would go online, and back again for display. |
| `agent/summary.py` | The plain-English **End of Day** summary (button on the Cashier Performance tab). |

From a terminal in the Spectre folder:

```bash
python -m agent summary 05.11.2026
```

```bash
python -m agent tools
```

```bash
python -m agent run cashier_ranking "{\"period\": \"This Week\"}"
```

### Running the tests

```bash
python -m unittest discover -s tests -t .
```

The tests don't need PySide6. All test data is fictional — never put real reports, names or figures in `tests/`.

### Building the .exe

`Spectre.spec` is the PyInstaller recipe used by `build_exe.bat` (see section 1). It bundles `main.py`, every page and the sidebar icons into one windowed `Spectre.exe`. PyInstaller can only build for the system it runs on, so the Windows `.exe` must be built on Windows.

---

*Spectre v2.0 — Audit Intelligence Platform*

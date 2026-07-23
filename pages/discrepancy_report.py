"""
pages/discrepancy_report.py — Discrepancy report generation dialog.

Produces Excel (.xlsx) and PDF reports for:
  - Discrepancy Volume Chart data
  - Cashier Discrepancy Summary
  - Full Discrepancy Log
"""
import datetime
import logging
import os

import pandas as pd

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QPushButton, QVBoxLayout, QWidget, QButtonGroup,
    QComboBox, QDateEdit,
)

from config import ALL_DISC_DB, COL_DISC, EXPECTED_TOTAL, AMOUNT, OPERATOR
from theme import Theme

# reuse bucket definitions from the tab
from pages.discrepancies_tab import (
    BUCKETS, _apply_toggle_style, _toggle_btn,
    DiscrepanciesPage,
)


def _card(title=""):
    f = QFrame()
    f.setStyleSheet(
        f"QFrame{{background:{Theme.SURFACE};border:1px solid {Theme.BORDER_S};border-radius:8px;}}"
    )
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 14, 18, 16); lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setStyleSheet(f"color:{Theme.TXT};font-size:12px;font-weight:600;")
        lay.addWidget(t)
        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div)
    return f, lay


# ── openpyxl style helpers — matching analytics_export.py aesthetics ──────────
def _xl_styles():
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    hdr_font  = lambda: Font(bold=True, color="FFFFFF",  size=10, name="Calibri")
    hdr_fill  = lambda: PatternFill("solid", fgColor="2B4A8A")
    title_font= lambda: Font(bold=True, color="1E3A70",  size=13, name="Calibri")
    sub_font  = lambda: Font(color="5A6E8A", size=10, name="Calibri")
    val_font  = lambda: Font(color="1A2A45", size=10, name="Calibri")
    hi_fill   = lambda: PatternFill("solid", fgColor="EEF3FB")
    med_fill  = lambda: PatternFill("solid", fgColor="FFFFFF")
    neg_font  = lambda: Font(color="C0392B", bold=True, size=10, name="Calibri")
    pos_font  = lambda: Font(color="1E7A3A", bold=True, size=10, name="Calibri")
    thin = Side(style="thin", color="C0CDE0")
    border = lambda: Border(bottom=thin, top=thin, left=thin, right=thin)
    return (hdr_font, hdr_fill, title_font, sub_font, val_font,
            hi_fill, med_fill, neg_font, pos_font, border)


def _auto_width(ws):
    from openpyxl.utils import get_column_letter
    for col in ws.columns:
        max_len = 0
        col_ltr = get_column_letter(col[0].column)
        for cell in col:
            try:
                max_len = max(max_len, len(str(cell.value or "")))
            except Exception:
                pass
        ws.column_dimensions[col_ltr].width = max(8, min(max_len + 3, 42))


# ── Core data helpers ─────────────────────────────────────────────────────────
def _load_db():
    if not os.path.exists(ALL_DISC_DB):
        return pd.DataFrame()
    try:
        df = pd.read_csv(ALL_DISC_DB, dtype=str)
        df["Discrepancy"]    = pd.to_numeric(df.get("Discrepancy",    pd.Series(dtype=float)), errors='coerce').fillna(0)
        df["Expected Total"] = pd.to_numeric(df.get("Expected Total", pd.Series(dtype=float)), errors='coerce').fillna(0)
        df["Total Processed"]= pd.to_numeric(df.get("Total Processed",pd.Series(dtype=float)), errors='coerce').fillna(0)
        return df
    except Exception as e:
        logging.error(f"Report load db: {e}")
        return pd.DataFrame()


def _filter_by_date(df, date_range, report_date_str=None, custom_start=None, custom_end=None):
    if date_range == "This Report":
        if report_date_str and "Report Date" in df.columns:
            return df[df["Report Date"] == report_date_str]
        return df

    today = datetime.date.today()

    def _parse(s):
        for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try: return datetime.datetime.strptime(str(s).strip(), fmt).date()
            except: pass
        return None

    if "Report Date" not in df.columns:
        return df
    df = df.copy()
    df["_d"] = df["Report Date"].apply(_parse)
    df = df[df["_d"].notna()]

    if date_range == "Today":
        df = df[df["_d"] == today]
    elif date_range == "This Week":
        ws = today - datetime.timedelta(days=today.weekday())
        df = df[df["_d"] >= ws]
    elif date_range == "This Month":
        df = df[(df["_d"].apply(lambda d: d.month) == today.month) &
                (df["_d"].apply(lambda d: d.year) == today.year)]
    elif date_range == "This Year":
        df = df[df["_d"].apply(lambda d: d.year) == today.year]
    elif date_range == "Custom Range":
        if custom_start and custom_end:
            df = df[(df["_d"] >= custom_start) & (df["_d"] <= custom_end)]
    return df


def _apply_type(df, type_filter):
    if "Type" not in df.columns or type_filter == "All":
        return df
    if type_filter == "Discrepancies Only":
        return df[df["Type"] == "Discrepancy"]
    if type_filter == "Blind Counts Only":
        return df[df["Type"] == "Blind Count"]
    return df


def _build_bucket_data(df):
    disc = pd.to_numeric(df["Discrepancy"], errors='coerce').fillna(0)
    type_col = df.get("Type", pd.Series(["Discrepancy"] * len(df), index=df.index))
    rows = []
    for lo, hi, label in BUCKETS:
        mask = disc.abs() >= lo
        if hi is not None:
            mask = mask & (disc.abs() < hi)
        sub_disc = disc[mask]
        sub_type = type_col[mask]
        pos_c   = int((sub_disc > 0).sum())
        neg_c   = int((sub_disc < 0).sum())
        blind_c = int((sub_type == "Blind Count").sum())
        pos_c  -= int(((sub_disc > 0) & (sub_type == "Blind Count")).sum())
        neg_c  -= int(((sub_disc < 0) & (sub_type == "Blind Count")).sum())
        total = pos_c + neg_c + blind_c
        rows.append({
            "Bucket":         label,
            "Overages":       max(0, pos_c),
            "Shortages":      max(0, neg_c),
            "Blind Counts":   max(0, blind_c),
            "Total":          total,
        })
    return rows


def _build_cashier_data(df):
    if df.empty:
        return []
    name_col = "Cashier Name" if "Cashier Name" in df.columns else None
    if not name_col:
        return []
    type_col = df.get("Type", pd.Series(["Discrepancy"] * len(df), index=df.index))
    rows = []
    for name, grp in df.groupby(name_col):
        grp_disc = pd.to_numeric(grp["Discrepancy"], errors='coerce').fillna(0)
        grp_type = type_col.loc[grp.index] if hasattr(type_col, 'loc') else grp.get("Type", pd.Series())
        disc_net  = float(grp_disc[grp_type != "Blind Count"].sum())
        blind_net = float(grp_disc[grp_type == "Blind Count"].sum())
        total_net = float(grp_disc.sum())
        rows.append({
            "Cashier Name":        str(name),
            "Discrepancies (net)": disc_net,
            "Blind Count (net)":   blind_net,
            "Total Net":           total_net,
            "# Records":           len(grp),
        })
    rows.sort(key=lambda r: abs(r["Total Net"]), reverse=True)
    return rows


# ── Excel generation ──────────────────────────────────────────────────────────
def generate_excel(path, df, include_chart, include_cashier, include_log, report_label):
    import openpyxl
    from openpyxl.styles import Font, Alignment
    (hdr_font, hdr_fill, title_font, sub_font, val_font,
     hi_fill, med_fill, neg_font, pos_font, border) = _xl_styles()

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    if include_chart:
        ws = wb.create_sheet("Discrepancy Volume")
        ws.sheet_view.showGridLines = False
        ws["A1"] = f"Discrepancy Volume Distribution — {report_label}"
        ws["A1"].font = title_font()
        ws["A2"] = f"Generated: {datetime.datetime.now():%d/%m/%Y %H:%M}"
        ws["A2"].font = sub_font()

        headers = ["Bucket", "Overages", "Shortages", "Blind Counts", "Total"]
        for ci, h in enumerate(headers, 1):
            c = ws.cell(4, ci, h)
            c.font = hdr_font(); c.fill = hdr_fill()
            c.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[4].height = 20
        ws.freeze_panes = "A5"

        rows = _build_bucket_data(df)
        for ri, row in enumerate(rows, 5):
            fill = hi_fill() if ri % 2 else med_fill()
            for ci, key in enumerate(headers, 1):
                c = ws.cell(ri, ci, row[key])
                c.font = val_font(); c.fill = fill; c.border = border()
                c.alignment = Alignment(horizontal="center", vertical="center")
        _auto_width(ws)

    if include_cashier:
        ws = wb.create_sheet("Cashier Summary")
        ws.sheet_view.showGridLines = False
        ws["A1"] = f"Cashier Discrepancy Summary — {report_label}"
        ws["A1"].font = title_font()
        ws["A2"] = f"Generated: {datetime.datetime.now():%d/%m/%Y %H:%M}"
        ws["A2"].font = sub_font()

        headers = ["Cashier Name", "Discrepancies (net)", "Blind Count (net)", "Total Net", "# Records"]
        for ci, h in enumerate(headers, 1):
            c = ws.cell(4, ci, h)
            c.font = hdr_font(); c.fill = hdr_fill()
            c.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[4].height = 20
        ws.freeze_panes = "A5"

        rows = _build_cashier_data(df)
        for ri, row in enumerate(rows, 5):
            fill = hi_fill() if ri % 2 else med_fill()
            for ci, key in enumerate(headers, 1):
                val = row[key]
                c = ws.cell(ri, ci, val)
                c.fill = fill; c.border = border()
                c.alignment = Alignment(horizontal="center", vertical="center")
                if key in ("Discrepancies (net)", "Blind Count (net)", "Total Net"):
                    if isinstance(val, (int, float)):
                        c.number_format = '€#,##0.00;[Red]-€#,##0.00'
                    c.font = (neg_font() if isinstance(val, (int,float)) and val < 0
                              else pos_font() if isinstance(val, (int,float)) and val > 0
                              else val_font())
                else:
                    c.font = val_font()
        _auto_width(ws)

    if include_log:
        ws = wb.create_sheet("Full Discrepancy Log")
        ws.sheet_view.showGridLines = False
        ws["A1"] = f"Full Discrepancy Log — {report_label}"
        ws["A1"].font = title_font()
        ws["A2"] = f"Generated: {datetime.datetime.now():%d/%m/%Y %H:%M}"
        ws["A2"].font = sub_font()

        if not df.empty:
            display_cols = [c for c in ["Report Date", "Customer ID", "Customer Location",
                                        "Expected Total", "Total Processed", "Discrepancy",
                                        "Operator ID", "Cashier Name", "Type"]
                            if c in df.columns]
            for ci, h in enumerate(display_cols, 1):
                c = ws.cell(4, ci, h)
                c.font = hdr_font(); c.fill = hdr_fill()
                c.alignment = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[4].height = 20
            ws.freeze_panes = "A5"

            for ri, (_, row) in enumerate(df[display_cols].iterrows(), 5):
                fill = hi_fill() if ri % 2 else med_fill()
                for ci, key in enumerate(display_cols, 1):
                    val = row[key]
                    try:
                        cell_val = "" if pd.isna(val) else val
                    except (TypeError, ValueError):
                        cell_val = str(val)
                    c = ws.cell(ri, ci, cell_val)
                    c.font = val_font(); c.fill = fill; c.border = border()
                    c.alignment = Alignment(vertical="center")
            _auto_width(ws)
        else:
            ws["A4"] = "No discrepancy data for the selected range."
            ws["A4"].font = sub_font()

    wb.save(path)


# ── PDF generation ────────────────────────────────────────────────────────────
def generate_pdf(path, df, include_chart, include_cashier, include_log, report_label):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, HRFlowable)

    styles = getSampleStyleSheet()
    navy   = colors.HexColor("#2B4A8A")
    dark   = colors.HexColor("#1A2A45")
    muted  = colors.HexColor("#5A6E8A")
    light  = colors.HexColor("#EEF3FB")
    red_c  = colors.HexColor("#C0392B")
    grn_c  = colors.HexColor("#1E7A3A")

    title_style = ParagraphStyle("title", fontSize=14, fontName="Helvetica-Bold",
                                 textColor=navy, spaceAfter=4)
    sub_style   = ParagraphStyle("sub",   fontSize=9,  fontName="Helvetica",
                                 textColor=muted, spaceAfter=12)
    sec_style   = ParagraphStyle("sec",   fontSize=11, fontName="Helvetica-Bold",
                                 textColor=navy, spaceBefore=16, spaceAfter=6)

    def _tbl_style(n_rows):
        return TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), navy),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,-1), 8),
            ("FONTNAME",    (0,1), (-1,-1), "Helvetica"),
            ("TEXTCOLOR",   (0,1), (-1,-1), dark),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [light, colors.white]),
            ("GRID",        (0,0), (-1,-1), 0.4, colors.HexColor("#C0CDE0")),
            ("ALIGN",       (0,0), (-1,-1), "CENTER"),
            ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING",  (0,0), (-1,-1), 4),
            ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ])

    story = []
    story.append(Paragraph(f"Spectre v2.0 — Discrepancy Report", title_style))
    story.append(Paragraph(f"{report_label}  ·  Generated {datetime.datetime.now():%d/%m/%Y %H:%M}", sub_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=navy))
    story.append(Spacer(1, 8))

    if include_chart:
        story.append(Paragraph("Discrepancy Volume Distribution", sec_style))
        rows = _build_bucket_data(df)
        headers = ["Bucket", "Overages", "Shortages", "Blind Counts", "Total"]
        data = [headers] + [[r[h] for h in headers] for r in rows]
        t = Table(data, colWidths=[35*mm, 28*mm, 28*mm, 33*mm, 22*mm])
        t.setStyle(_tbl_style(len(data)))
        story.append(t)
        story.append(Spacer(1, 12))

    if include_cashier:
        story.append(Paragraph("Cashier Discrepancy Summary", sec_style))
        rows = _build_cashier_data(df)
        if rows:
            headers = ["Cashier Name", "Discrepancies (net)", "Blind Count (net)", "Total Net", "# Records"]
            data = [headers]
            for r in rows:
                data.append([
                    r["Cashier Name"],
                    f"€{r['Discrepancies (net)']:+,.2f}",
                    f"€{r['Blind Count (net)']:+,.2f}",
                    f"€{r['Total Net']:+,.2f}",
                    r["# Records"],
                ])
            t = Table(data, colWidths=[45*mm, 35*mm, 35*mm, 28*mm, 22*mm])
            ts = _tbl_style(len(data))
            for ri, row in enumerate(rows, 1):
                net = row["Total Net"]
                if net < 0:
                    ts.add("TEXTCOLOR", (3, ri), (3, ri), red_c)
                elif net > 0:
                    ts.add("TEXTCOLOR", (3, ri), (3, ri), grn_c)
            t.setStyle(ts)
            story.append(t)
        else:
            story.append(Paragraph("No cashier data for the selected range.", sub_style))
        story.append(Spacer(1, 12))

    if include_log:
        story.append(Paragraph("Full Discrepancy Log", sec_style))
        if not df.empty:
            all_log_cols = ["Report Date", "Customer ID", "Customer Location",
                            "Expected Total", "Total Processed", "Discrepancy",
                            "Cashier Name", "Type"]
            display_cols = [c for c in all_log_cols if c in df.columns]

            # Per-column widths (mm) — total = 180 mm (A4 minus margins).
            # Customer Location gets the most space so long names wrap cleanly.
            col_w_map = {
                "Report Date":      20,
                "Customer ID":      18,
                "Customer Location":34,
                "Expected Total":   20,
                "Total Processed":  20,
                "Discrepancy":      18,
                "Cashier Name":     28,
                "Type":             22,
            }
            col_widths = [col_w_map.get(c, 20) * mm for c in display_cols]

            # ParagraphStyle for wrapped location cells — slightly smaller font
            loc_style = ParagraphStyle(
                "loc_cell",
                fontSize=7,
                fontName="Helvetica",
                textColor=dark,
                leading=9,
                wordWrap="LTR",
            )
            loc_hdr_style = ParagraphStyle(
                "loc_hdr",
                fontSize=8,
                fontName="Helvetica-Bold",
                textColor=colors.white,
                leading=10,
                wordWrap="LTR",
            )

            loc_idx = display_cols.index("Customer Location") if "Customer Location" in display_cols else None

            _MONEY_COLS = {"Expected Total", "Total Processed", "Discrepancy"}
            _ID_COLS    = {"Customer ID", "Operator ID"}

            def _fmt_cell(col_name, raw):
                """Format a cell value for clean PDF display."""
                try:
                    if isinstance(raw, float) and pd.isna(raw):
                        return ""
                except (TypeError, ValueError):
                    pass
                if col_name in _MONEY_COLS:
                    try:
                        return f"{round(float(raw), 2):,.2f}"
                    except (ValueError, TypeError):
                        return str(raw)
                if col_name in _ID_COLS:
                    try:
                        f = float(raw)
                        return str(int(f)) if not pd.isna(f) else str(raw)
                    except (ValueError, TypeError):
                        return str(raw)
                return str(raw)

            # Header row — wrap the location header too so it stays tidy
            hdr_row = []
            for ci, c in enumerate(display_cols):
                if ci == loc_idx:
                    hdr_row.append(Paragraph(c, loc_hdr_style))
                else:
                    hdr_row.append(c)
            data = [hdr_row]

            for _, row in df[display_cols].head(500).iterrows():
                data_row = []
                for ci, c in enumerate(display_cols):
                    cell_str = _fmt_cell(c, row[c])
                    if ci == loc_idx:
                        data_row.append(Paragraph(cell_str, loc_style))
                    else:
                        data_row.append(cell_str)
                data.append(data_row)

            ts = _tbl_style(len(data))
            # Location column: left-align and top-anchor so wrapped lines read naturally
            if loc_idx is not None:
                ts.add("ALIGN",  (loc_idx, 0), (loc_idx, -1), "LEFT")
                ts.add("VALIGN", (loc_idx, 0), (loc_idx, -1), "TOP")

            t = Table(data, colWidths=col_widths, repeatRows=1)
            t.setStyle(ts)
            story.append(t)
            if len(df) > 500:
                story.append(Paragraph(f"(Showing first 500 of {len(df)} records)", sub_style))
        else:
            story.append(Paragraph("No discrepancy data for the selected range.", sub_style))

    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=18*mm, bottomMargin=15*mm)
    doc.build(story)


# ── Dialog ────────────────────────────────────────────────────────────────────
class DiscrepancyReportDialog(QDialog):
    def __init__(self, app, hist_date="This Report", hist_type="All",
                 cash_date="This Report", cash_type="All",
                 custom_start=None, custom_end=None, parent=None):
        super().__init__(parent)
        self.app = app
        self._hist_date = hist_date
        self._hist_type = hist_type
        self._cash_date = cash_date
        self._cash_type = cash_type
        self._init_custom_start = custom_start
        self._init_custom_end   = custom_end
        self.setWindowTitle("Generate Discrepancy Report")
        self.setMinimumWidth(520)
        self.setStyleSheet(
            f"QDialog{{background:{Theme.BG};border:1px solid {Theme.BORDER};}}"
        )
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(16)

        title = QLabel("Generate Discrepancy Report")
        title.setStyleSheet(f"color:{Theme.TXT};font-size:16px;font-weight:700;")
        lay.addWidget(title)

        sub = QLabel("Select report sections, date range, type filter, and output format.")
        sub.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
        lay.addWidget(sub)

        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background:{Theme.BORDER_S};")
        lay.addWidget(div)

        # Sections
        sec_card, sec_lay = _card("Sections to Include")
        self._cb_chart   = QCheckBox("Discrepancy Volume Chart (bucket data)")
        self._cb_cashier = QCheckBox("Cashier Discrepancy Summary")
        self._cb_log     = QCheckBox("Full Discrepancy Log")
        for cb in (self._cb_chart, self._cb_cashier, self._cb_log):
            cb.setChecked(True)
            cb.setStyleSheet(f"QCheckBox{{color:{Theme.TXT};font-size:12px;}}")
        sec_lay.addWidget(self._cb_chart)
        sec_lay.addWidget(self._cb_cashier)
        sec_lay.addWidget(self._cb_log)
        lay.addWidget(sec_card)

        # Date range
        dr_card, dr_lay = _card("Date Range")
        dr_row = QHBoxLayout(); dr_row.setSpacing(6)
        self._date_combo = QComboBox()
        for r in ["This Report", "Today", "This Week", "This Month", "This Year", "All Time", "Custom Range"]:
            self._date_combo.addItem(r)
        self._date_combo.setCurrentText(self._hist_date)
        dr_row.addWidget(QLabel("Range:")); dr_row.addWidget(self._date_combo)

        self._type_combo = QComboBox()
        for t in ["All", "Discrepancies Only", "Blind Counts Only"]:
            self._type_combo.addItem(t)
        self._type_combo.setCurrentText(self._hist_type)
        dr_row.addSpacing(16)
        dr_row.addWidget(QLabel("Type:")); dr_row.addWidget(self._type_combo)
        dr_row.addStretch()
        dr_lay.addLayout(dr_row)

        # Custom date pickers — shown only when "Custom Range" is selected
        self._custom_row = QWidget()
        cr_lay = QHBoxLayout(self._custom_row)
        cr_lay.setContentsMargins(0, 4, 0, 0); cr_lay.setSpacing(8)
        today_q = QDate.currentDate()

        def _qdate(py_date):
            if py_date:
                return QDate(py_date.year, py_date.month, py_date.day)
            return None

        _de_style = (
            f"QDateEdit{{background:{Theme.ELEVATED};color:{Theme.TXT};"
            f"border:1px solid {Theme.BORDER};border-radius:4px;padding:3px 7px;font-size:11px;}}"
        )
        lbl_from = QLabel("From:")
        lbl_from.setStyleSheet(f"color:{Theme.TXT_2};font-size:11px;")
        self._from_date = QDateEdit()
        self._from_date.setCalendarPopup(True)
        self._from_date.setDisplayFormat("dd/MM/yyyy")
        self._from_date.setDate(_qdate(self._init_custom_start) or today_q.addMonths(-1))
        self._from_date.setStyleSheet(_de_style)

        lbl_to = QLabel("To:")
        lbl_to.setStyleSheet(f"color:{Theme.TXT_2};font-size:11px;")
        self._to_date = QDateEdit()
        self._to_date.setCalendarPopup(True)
        self._to_date.setDisplayFormat("dd/MM/yyyy")
        self._to_date.setDate(_qdate(self._init_custom_end) or today_q)
        self._to_date.setStyleSheet(_de_style)

        cr_lay.addWidget(lbl_from); cr_lay.addWidget(self._from_date)
        cr_lay.addSpacing(12)
        cr_lay.addWidget(lbl_to);   cr_lay.addWidget(self._to_date)
        cr_lay.addStretch()
        self._custom_row.setVisible(self._hist_date == "Custom Range")
        dr_lay.addWidget(self._custom_row)

        self._date_combo.currentTextChanged.connect(
            lambda t: self._custom_row.setVisible(t == "Custom Range")
        )
        lay.addWidget(dr_card)

        # Format
        fmt_card, fmt_lay = _card("Output Format")
        fmt_row = QHBoxLayout(); fmt_row.setSpacing(6)
        self._cb_excel = QCheckBox("Excel (.xlsx)")
        self._cb_pdf   = QCheckBox("PDF (.pdf)")
        self._cb_excel.setChecked(True)
        for cb in (self._cb_excel, self._cb_pdf):
            cb.setStyleSheet(f"QCheckBox{{color:{Theme.TXT};font-size:12px;}}")
        fmt_row.addWidget(self._cb_excel); fmt_row.addWidget(self._cb_pdf)
        fmt_row.addStretch()
        fmt_lay.addLayout(fmt_row)
        lay.addWidget(fmt_card)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{Theme.OK};font-size:11px;font-weight:600;")
        self._status.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._status)

        btn_row = QHBoxLayout(); btn_row.setSpacing(10)
        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(36)
        cancel.clicked.connect(self.reject)
        self._gen = QPushButton("Generate")
        self._gen.setObjectName("primary")
        self._gen.setFixedHeight(36)
        self._gen.setMinimumWidth(120)
        self._gen.clicked.connect(self._generate)
        btn_row.addStretch(); btn_row.addWidget(cancel); btn_row.addWidget(self._gen)
        lay.addLayout(btn_row)

    def _get_data(self):
        date_range = self._date_combo.currentText()
        type_filter = self._type_combo.currentText()
        report_date = getattr(self.app, "_active_report_date", None)

        custom_start = None
        custom_end   = None
        if date_range == "Custom Range":
            custom_start = self._from_date.date().toPython()
            custom_end   = self._to_date.date().toPython()

        if date_range == "This Report":
            df = getattr(self.app, "active_df", None)
            if df is None or df.empty:
                return pd.DataFrame(), date_range, type_filter, custom_start, custom_end
            sub = df.copy()
            from config import COL_DISC, EXPECTED_TOTAL, OPERATOR
            sub["Discrepancy"] = pd.to_numeric(sub.get(COL_DISC, pd.Series(dtype=float)), errors='coerce').fillna(0)
            sub = sub[sub["Discrepancy"] != 0].copy()
            exp_col = EXPECTED_TOTAL if EXPECTED_TOTAL in sub.columns else None
            def _get_type(row):
                ev = pd.to_numeric(row.get(exp_col, 0), errors='coerce') if exp_col else 0
                return "Blind Count" if (pd.isna(ev) or ev == 0) else "Discrepancy"
            sub["Type"] = sub.apply(_get_type, axis=1)
            if "Cashier Name" not in sub.columns and OPERATOR in sub.columns:
                sub["Cashier Name"] = sub[OPERATOR]
        else:
            db = _load_db()
            sub = _filter_by_date(db, date_range, report_date, custom_start, custom_end)

        sub = _apply_type(sub, type_filter)
        return sub, date_range, type_filter, custom_start, custom_end

    def _generate(self):
        if not self._cb_excel.isChecked() and not self._cb_pdf.isChecked():
            self._status.setText("Select at least one output format.")
            self._status.setStyleSheet(f"color:{Theme.DANGER};font-size:11px;font-weight:600;")
            return
        if not any([self._cb_chart.isChecked(), self._cb_cashier.isChecked(), self._cb_log.isChecked()]):
            self._status.setText("Select at least one section.")
            self._status.setStyleSheet(f"color:{Theme.DANGER};font-size:11px;font-weight:600;")
            return

        df, date_range, type_filter, custom_start, custom_end = self._get_data()
        if date_range == "Custom Range" and custom_start and custom_end:
            range_label = f"{custom_start:%d/%m/%Y} – {custom_end:%d/%m/%Y}"
        else:
            range_label = date_range
        label = f"{range_label}  ·  {type_filter}"

        saved = []
        try:
            self._gen.setEnabled(False)
            self._status.setText("Generating…")

            base_name = f"Discrepancy_Report_{datetime.date.today():%Y%m%d}"

            if self._cb_excel.isChecked():
                path, _ = QFileDialog.getSaveFileName(
                    self, "Save Excel Report", f"{base_name}.xlsx", "Excel (*.xlsx)"
                )
                if path:
                    generate_excel(
                        path, df,
                        self._cb_chart.isChecked(),
                        self._cb_cashier.isChecked(),
                        self._cb_log.isChecked(),
                        label,
                    )
                    saved.append(os.path.basename(path))

            if self._cb_pdf.isChecked():
                path, _ = QFileDialog.getSaveFileName(
                    self, "Save PDF Report", f"{base_name}.pdf", "PDF (*.pdf)"
                )
                if path:
                    generate_pdf(
                        path, df,
                        self._cb_chart.isChecked(),
                        self._cb_cashier.isChecked(),
                        self._cb_log.isChecked(),
                        label,
                    )
                    saved.append(os.path.basename(path))

            if saved:
                self._status.setText("✓  Saved: " + ", ".join(saved))
                self._status.setStyleSheet(f"color:{Theme.OK};font-size:11px;font-weight:600;")
            else:
                self._status.setText("No files saved.")
                self._status.setStyleSheet(f"color:{Theme.TXT_3};font-size:11px;")
        except Exception as e:
            logging.exception("Report generation error")
            self._status.setText(f"Error: {e}")
            self._status.setStyleSheet(f"color:{Theme.DANGER};font-size:11px;font-weight:600;")
        finally:
            self._gen.setEnabled(True)

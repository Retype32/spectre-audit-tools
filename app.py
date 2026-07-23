import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import os
import sys
from datetime import datetime

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# ── Config ────────────────────────────────────────────────────────────────────

if getattr(sys, "frozen", False):
    _DIR = os.path.dirname(sys.executable)
else:
    try:
        _DIR = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        _DIR = os.getcwd()

CSV_FILE    = os.path.join(_DIR, "issues.csv")
HEADERS     = ["ID", "Timestamp", "Customer", "Location",
               "Issue Type", "Solution", "Explanation", "Comment"]

ISSUE_TYPES = [
    "No Slip",
    "Location Not Specified",
    "Illegible Slip",
    "Wrong Account on Slip",
    "Wrong Location on Slip",
    "Wrong Department",
    "Other",
]

ISSUE_EXPLANATIONS = {
    "No Slip":                "Slip not included in the bag.",
    "Location Not Specified": "Location not specified from the customer.",
    "Illegible Slip":         "Slip not readable due to misprint.",
    "Wrong Account on Slip":  "Account provided is not on Compass.",
    "Wrong Location on Slip": "Location number does not exist on Compass.",
    "Wrong Department":       "Account is valid on a different Financial Institution.",
}

SOLUTION_TYPES = [
    "14 Days Cage",
    "Location Provided by Supervisor",
    "Sent to appropriate department",
    "Slip Printed",
    "Other",
]

SOLUTION_EXPLANATIONS = {
    "14 Days Cage":                    "Bag was placed in 14 Days Cage.",
    "Location Provided by Supervisor": "Location was provided manually by the supervisor.",
    "Sent to appropriate department":  "Bag sent to be processed on a different Financial Institution.",
    "Slip Printed":                    "Slip printed and provided manually by the supervisor.",
}

# ── Palette ───────────────────────────────────────────────────────────────────

BG, SURFACE, CARD = "#16213E", "#0F3460", "#1A1A2E"
ACCENT, PURPLE    = "#E94560", "#533483"
TEXT, MUTED       = "#EAEAEA", "#8892A4"
SUCCESS, INPUT_BG = "#06D6A0", "#1E2D40"
BORDER            = "#2C3E5A"

FT_H1  = ("Segoe UI", 22, "bold")
FT_LBL = ("Segoe UI", 11)
FT_ENT = ("Segoe UI", 11)
FT_BTN = ("Segoe UI", 11, "bold")
FT_SM  = ("Segoe UI", 9)
FT_TBL = ("Segoe UI", 10)


# ── App ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Issue Tracker")
        self.geometry("1200x710")
        self.minsize(1050, 640)
        self.configure(bg=BG)

        self._init_csv()
        self._setup_styles()
        self._build_header()
        self._build_tabs()

    # ── Data ──────────────────────────────────────────────────────────────────

    def _init_csv(self):
        if not os.path.exists(CSV_FILE):
            with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=HEADERS).writeheader()
            return
        with open(CSV_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing = reader.fieldnames or []
            if set(HEADERS).issubset(set(existing)):
                return
            records = list(reader)
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=HEADERS)
            w.writeheader()
            for r in records:
                w.writerow({h: r.get(h, "") for h in HEADERS})

    def _load_records(self):
        if not os.path.exists(CSV_FILE):
            return []
        with open(CSV_FILE, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _append_record(self, customer, location, issue_type, solution, explanation, comment):
        records = self._load_records()
        ids = []
        for r in records:
            try:
                ids.append(int(r["ID"]))
            except (ValueError, KeyError):
                pass
        new_id = max(ids, default=0) + 1
        row = {
            "ID": new_id,
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Customer": customer,
            "Location": location,
            "Issue Type": issue_type,
            "Solution": solution,
            "Explanation": explanation,
            "Comment": comment,
        }
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=HEADERS).writerow(row)

    # ── Styles ────────────────────────────────────────────────────────────────

    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure("TNotebook",      background=BG, borderwidth=0)
        s.configure("TNotebook.Tab",  background=SURFACE, foreground=MUTED,
                    padding=[22, 10], font=("Segoe UI", 11), borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", PURPLE)],
              foreground=[("selected", TEXT)])

        s.configure("Treeview",         background=CARD, foreground=TEXT,
                    rowheight=28, fieldbackground=CARD, font=FT_TBL, borderwidth=0)
        s.configure("Treeview.Heading", background=SURFACE, foreground=TEXT,
                    font=("Segoe UI", 10, "bold"), relief="flat")
        s.map("Treeview",
              background=[("selected", PURPLE)],
              foreground=[("selected", TEXT)])

        s.configure("Vertical.TScrollbar",   background=SURFACE, troughcolor=BG,
                    arrowcolor=MUTED, borderwidth=0)
        s.configure("Horizontal.TScrollbar", background=SURFACE, troughcolor=BG,
                    arrowcolor=MUTED, borderwidth=0)

        s.configure("TCombobox", fieldbackground=INPUT_BG, background=SURFACE,
                    foreground=TEXT, arrowcolor=MUTED, font=FT_LBL)
        s.map("TCombobox",
              fieldbackground=[("readonly", INPUT_BG)],
              foreground=[("readonly", TEXT)],
              selectbackground=[("readonly", PURPLE)])

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        bar = tk.Frame(self, bg=SURFACE, height=68)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text="ISSUE TRACKER", font=FT_H1,
                 bg=SURFACE, fg=TEXT).pack(side="left", padx=30, pady=14)
        self._date_label = tk.Label(bar, text=datetime.now().strftime("%A, %d %B %Y"),
                                    font=FT_SM, bg=SURFACE, fg=MUTED)
        self._date_label.pack(side="right", padx=30)
        self._schedule_date_update()

    def _schedule_date_update(self):
        self._date_label.config(text=datetime.now().strftime("%A, %d %B %Y"))
        self.after(3_600_000, self._schedule_date_update)

    # ── Tabs ──────────────────────────────────────────────────────────────────

    def _build_tabs(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self.tab_log     = tk.Frame(nb, bg=BG)
        self.tab_records = tk.Frame(nb, bg=BG)
        self.tab_export  = tk.Frame(nb, bg=BG)

        nb.add(self.tab_log,     text="  Log Issue  ")
        nb.add(self.tab_records, text="  Records  ")
        nb.add(self.tab_export,  text="  Export  ")

        self._build_log_tab()
        self._build_records_tab()
        self._build_export_tab()

        nb.bind("<<NotebookTabChanged>>", lambda e: (
            self._refresh_records() if nb.index("current") == 1 else None
        ))

    # ── Log Tab ───────────────────────────────────────────────────────────────

    def _build_log_tab(self):
        wrap = tk.Frame(self.tab_log, bg=BG)
        wrap.pack(expand=True, fill="both")

        card = tk.Frame(wrap, bg=CARD, padx=32, pady=20,
                        highlightthickness=1, highlightbackground=BORDER)
        card.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(card, text="Log a New Issue", font=("Segoe UI", 13, "bold"),
                 bg=CARD, fg=TEXT).grid(row=0, column=0, columnspan=2,
                                        sticky="w", pady=(0, 12))

        def lbl(row, text):
            tk.Label(card, text=text, font=("Segoe UI", 10), bg=CARD, fg=MUTED).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(0, 2))

        def entry_field(row):
            e = tk.Entry(card, font=("Segoe UI", 10), bg=INPUT_BG, fg=TEXT,
                         insertbackground=TEXT, relief="flat", width=40,
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
            e.grid(row=row + 1, column=0, columnspan=2, sticky="ew",
                   pady=(0, 10), ipady=5)
            return e

        lbl(1, "Customer");  self.ent_customer = entry_field(1)
        lbl(3, "Location");  self.ent_location = entry_field(3)

        lbl(5, "Issue Type")
        self.issue_var = tk.StringVar(value=ISSUE_TYPES[0])
        rb_wrap = tk.Frame(card, bg=CARD)
        rb_wrap.grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 8))
        for idx, issue in enumerate(ISSUE_TYPES):
            r, c = divmod(idx, 3)
            tk.Radiobutton(
                rb_wrap, text=issue, variable=self.issue_var, value=issue,
                bg=CARD, fg=TEXT, selectcolor=PURPLE,
                activebackground=CARD, activeforeground=ACCENT,
                font=("Segoe UI", 10), cursor="hand2",
            ).grid(row=r, column=c, sticky="w", padx=(0, 16), pady=2)

        lbl(7, "Solution")
        self.solution_var = tk.StringVar(value=SOLUTION_TYPES[0])
        sol_wrap = tk.Frame(card, bg=CARD)
        sol_wrap.grid(row=8, column=0, columnspan=2, sticky="w", pady=(0, 8))
        for idx, sol in enumerate(SOLUTION_TYPES):
            r, c = divmod(idx, 3)
            tk.Radiobutton(
                sol_wrap, text=sol, variable=self.solution_var, value=sol,
                bg=CARD, fg=TEXT, selectcolor=PURPLE,
                activebackground=CARD, activeforeground=ACCENT,
                font=("Segoe UI", 10), cursor="hand2",
            ).grid(row=r, column=c, sticky="w", padx=(0, 16), pady=2)

        lbl(9, "Comment  (optional)")
        self.txt_comment = tk.Text(
            card, font=("Segoe UI", 10), bg=INPUT_BG, fg=TEXT,
            insertbackground=TEXT, relief="flat", width=40, height=3,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
        )
        self.txt_comment.grid(row=10, column=0, columnspan=2,
                               sticky="ew", pady=(0, 14))

        btn_row = tk.Frame(card, bg=CARD)
        btn_row.grid(row=11, column=0, columnspan=2, sticky="w")

        tk.Button(
            btn_row, text="  Submit  ", font=FT_BTN, bg=ACCENT, fg="white",
            relief="flat", cursor="hand2", pady=6,
            activebackground="#C73652", activeforeground="white",
            command=self._submit,
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            btn_row, text="  Clear  ", font=FT_BTN, bg=BORDER, fg=TEXT,
            relief="flat", cursor="hand2", pady=6,
            activebackground=SURFACE, activeforeground=TEXT,
            command=self._clear_log,
        ).pack(side="left")

        self._log_status = tk.StringVar()
        tk.Label(card, textvariable=self._log_status, font=("Segoe UI", 10, "bold"),
                 bg=CARD, fg=SUCCESS).grid(row=12, column=0, columnspan=2,
                                           sticky="w", pady=(8, 0))

    def _submit(self):
        customer = self.ent_customer.get().strip()
        location = self.ent_location.get().strip()
        issue    = self.issue_var.get()
        solution = self.solution_var.get()
        comment  = self.txt_comment.get("1.0", "end-1c").strip()

        if not customer:
            messagebox.showwarning("Missing Field", "Please enter a Customer name.")
            return
        if not location:
            messagebox.showwarning("Missing Field", "Please enter a Location.")
            return

        parts       = [p for p in [ISSUE_EXPLANATIONS.get(issue, ""),
                                   SOLUTION_EXPLANATIONS.get(solution, "")] if p]
        explanation = " ".join(parts)

        self._append_record(customer, location, issue, solution, explanation, comment)
        self._log_status.set("✓  Issue Recorded!")
        self.after(4000, lambda: self._log_status.set(""))
        self._clear_log()

    def _clear_log(self):
        self.ent_customer.delete(0, "end")
        self.ent_location.delete(0, "end")
        self.issue_var.set(ISSUE_TYPES[0])
        self.solution_var.set(SOLUTION_TYPES[0])
        self.txt_comment.delete("1.0", "end")

    # ── Records Tab ───────────────────────────────────────────────────────────

    def _build_records_tab(self):
        toolbar = tk.Frame(self.tab_records, bg=SURFACE, padx=16, pady=10)
        toolbar.pack(fill="x")

        def tlbl(text):
            tk.Label(toolbar, text=text, font=FT_LBL,
                     bg=SURFACE, fg=MUTED).pack(side="left", padx=(0, 6))

        tlbl("Filter:")
        self._filter_var = tk.StringVar(value="All")
        fcb = ttk.Combobox(toolbar, textvariable=self._filter_var,
                           values=["All"] + ISSUE_TYPES, state="readonly",
                           width=22, font=FT_LBL)
        fcb.pack(side="left", padx=(0, 20), ipady=4)
        fcb.bind("<<ComboboxSelected>>", lambda _: self._refresh_records())

        tlbl("Search:")
        self._search_var = tk.StringVar()
        se = tk.Entry(toolbar, textvariable=self._search_var, font=FT_LBL,
                      bg=INPUT_BG, fg=TEXT, insertbackground=TEXT, relief="flat",
                      width=24, highlightthickness=1, highlightbackground=BORDER,
                      highlightcolor=ACCENT)
        se.pack(side="left", ipady=5)
        se.bind("<KeyRelease>", lambda _: self._refresh_records())

        self._count_var = tk.StringVar()
        tk.Label(toolbar, textvariable=self._count_var, font=FT_SM,
                 bg=SURFACE, fg=MUTED).pack(side="right", padx=8)

        frame = tk.Frame(self.tab_records, bg=BG)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        self.tree = ttk.Treeview(frame, columns=HEADERS, show="headings",
                                  selectmode="extended")

        col_w = {"ID": 45, "Timestamp": 135, "Customer": 120,
                  "Location": 120, "Issue Type": 155, "Solution": 200,
                  "Explanation": 220, "Comment": 9999}
        for col in HEADERS:
            self.tree.heading(col, text=col,
                               command=lambda c=col: self._sort(c))
            self.tree.column(col, width=col_w.get(col, 120), minwidth=50,
                              anchor="w", stretch=(col == "Comment"))

        vsb = ttk.Scrollbar(frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        self.tree.tag_configure("even", background="#1C1C2E")
        self.tree.tag_configure("odd",  background="#1A1A2E")

        self._sort_col = "ID"
        self._sort_rev = True
        self._refresh_records()

    def _refresh_records(self):
        records = self._load_records()

        f = self._filter_var.get()
        if f != "All":
            records = [r for r in records if r["Issue Type"] == f]

        q = self._search_var.get().strip().lower()
        if q:
            records = [
                r for r in records
                if q in r["Customer"].lower()
                or q in r["Location"].lower()
                or q in r.get("Solution", "").lower()
                or q in r.get("Explanation", "").lower()
                or q in r.get("Comment", "").lower()
            ]

        if self._sort_col:
            num = self._sort_col == "ID"
            def _sort_key(r):
                if num:
                    try:
                        return int(r[self._sort_col])
                    except (ValueError, KeyError):
                        return 0
                return r.get(self._sort_col, "")
            records.sort(key=_sort_key, reverse=self._sort_rev)

        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(records):
            self.tree.insert("", "end",
                              values=[r["ID"], r["Timestamp"], r["Customer"],
                                      r["Location"], r["Issue Type"],
                                      r.get("Solution", ""), r.get("Explanation", ""),
                                      r.get("Comment", "")],
                              tags=("even" if i % 2 == 0 else "odd",))

        n = len(records)
        self._count_var.set(f"{n} record{'s' if n != 1 else ''}")

    def _sort(self, col):
        self._sort_rev = not self._sort_rev if self._sort_col == col else False
        self._sort_col = col
        self._refresh_records()

    # ── Export Tab ────────────────────────────────────────────────────────────

    def _build_export_tab(self):
        outer = tk.Frame(self.tab_export, bg=BG)
        outer.pack(expand=True, fill="both")

        card = tk.Frame(outer, bg=CARD, padx=50, pady=44,
                        highlightthickness=1, highlightbackground=BORDER)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        tk.Label(card, text="Export Data", font=("Segoe UI", 15, "bold"),
                 bg=CARD, fg=TEXT).grid(row=0, columnspan=2, sticky="w",
                                        pady=(0, 6))
        tk.Label(card, text="Export all logged issues to a formatted file.",
                 font=FT_SM, bg=CARD, fg=MUTED).grid(row=1, columnspan=2,
                                                       sticky="w", pady=(0, 28))

        def export_card(col, title, desc, btn_txt, btn_color, cmd, avail, hint):
            f = tk.Frame(card, bg=SURFACE, padx=26, pady=22,
                         highlightthickness=1, highlightbackground=BORDER)
            f.grid(row=2, column=col, padx=(0, 18) if col == 0 else 0, sticky="nsew")
            tk.Label(f, text=title, font=("Segoe UI", 13, "bold"),
                     bg=SURFACE, fg=TEXT).pack(anchor="w")
            tk.Label(f, text=desc, font=FT_SM, bg=SURFACE, fg=MUTED,
                     justify="left").pack(anchor="w", pady=(6, 14))
            tk.Button(
                f, text=btn_txt, font=FT_BTN, relief="flat", padx=14, pady=8,
                bg=btn_color if avail else BORDER,
                fg="white" if avail else MUTED,
                cursor="hand2" if avail else "arrow",
                state="normal" if avail else "disabled",
                command=cmd,
            ).pack(anchor="w")
            if not avail:
                tk.Label(f, text=hint, font=FT_SM, bg=SURFACE,
                         fg=MUTED).pack(anchor="w", pady=(5, 0))

        export_card(0, "Excel (.xlsx)",
                    "Formatted spreadsheet with colored\nheaders, borders, and a summary sheet.",
                    "Export to Excel", SUCCESS, self._export_excel,
                    EXCEL_AVAILABLE, "pip install openpyxl")

        export_card(1, "PDF (.pdf)",
                    "Printable A4 landscape report with a\nfull records table and issue breakdown.",
                    "Export to PDF", ACCENT, self._export_pdf,
                    PDF_AVAILABLE, "pip install reportlab")

        self._export_status = tk.StringVar()
        tk.Label(card, textvariable=self._export_status, font=FT_SM,
                 bg=CARD, fg=SUCCESS).grid(row=3, columnspan=2,
                                           sticky="w", pady=(22, 0))

    # ── Excel export ──────────────────────────────────────────────────────────

    def _export_excel(self):
        records = self._load_records()
        if not records:
            messagebox.showinfo("Empty", "No records to export.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            initialfile=f"Report {datetime.now().strftime('%Y-%m-%d')}.xlsx",
            filetypes=[("Excel Workbook", "*.xlsx")],
            title="Save as Excel",
        )
        if not path:
            return

        wb = openpyxl.Workbook()

        # ── Records sheet ─────────────────────────────────────────────────────
        ws = wb.active
        ws.title = "Records"

        thin_side   = Side(style="thin", color="2C3E5A")
        border      = Border(left=thin_side, right=thin_side,
                             top=thin_side, bottom=thin_side)
        hdr_fill    = PatternFill("solid", fgColor="0F3460")
        hdr_font    = Font(bold=True, color="EAEAEA", size=11, name="Segoe UI")
        data_font   = Font(color="EAEAEA", size=10, name="Segoe UI")
        even_fill   = PatternFill("solid", fgColor="1A1A2E")
        odd_fill    = PatternFill("solid", fgColor="1E2D40")
        center_al   = Alignment(horizontal="center", vertical="center")
        left_al     = Alignment(horizontal="left",   vertical="center",
                                wrap_text=True)

        for ci, h in enumerate(HEADERS, 1):
            c = ws.cell(1, ci, h)
            c.fill, c.font, c.alignment, c.border = hdr_fill, hdr_font, center_al, border
        ws.row_dimensions[1].height = 26

        for ci, w in enumerate([6, 20, 20, 20, 24, 34, 42, 28], 1):
            ws.column_dimensions[get_column_letter(ci)].width = w

        for ri, rec in enumerate(records, 2):
            fill = even_fill if ri % 2 == 0 else odd_fill
            for ci, key in enumerate(HEADERS, 1):
                c = ws.cell(ri, ci, rec.get(key, ""))
                c.fill, c.font, c.border = fill, data_font, border
                c.alignment = center_al if ci <= 5 else left_al
            ws.row_dimensions[ri].height = 30

        ws.freeze_panes = "A2"

        # ── Summary sheet ─────────────────────────────────────────────────────
        ws2 = wb.create_sheet("Summary")
        ws2.sheet_properties.tabColor = "533483"
        ws2.column_dimensions["A"].width = 26
        ws2.column_dimensions["B"].width = 10
        ws2.column_dimensions["C"].width = 14

        title_c = ws2.cell(1, 1, "Issue Type Breakdown")
        title_c.font = Font(bold=True, size=14, color="E94560", name="Segoe UI")
        title_c.fill = PatternFill("solid", fgColor="1A1A2E")
        ws2.row_dimensions[1].height = 28

        hdr2_fill = PatternFill("solid", fgColor="533483")
        hdr2_font = Font(bold=True, color="EAEAEA", size=11, name="Segoe UI")
        for ci, h in enumerate(["Issue Type", "Count", "% of Total"], 1):
            c = ws2.cell(2, ci, h)
            c.fill, c.font, c.alignment, c.border = hdr2_fill, hdr2_font, center_al, border
        ws2.row_dimensions[2].height = 24

        counts = {}
        for r in records:
            counts[r["Issue Type"]] = counts.get(r["Issue Type"], 0) + 1
        total = len(records)

        for i, issue in enumerate(ISSUE_TYPES):
            cnt  = counts.get(issue, 0)
            pct  = f"{cnt / total * 100:.1f}%" if total else "0.0%"
            fill = PatternFill("solid", fgColor="1A1A2E" if i % 2 == 0 else "1E2D40")
            row  = i + 3
            for ci, val in enumerate([issue, cnt, pct], 1):
                c = ws2.cell(row, ci, val)
                c.fill, c.font, c.border = fill, data_font, border
                c.alignment = left_al if ci == 1 else center_al
            ws2.row_dimensions[row].height = 20

        tr = len(ISSUE_TYPES) + 3
        tot_font = Font(bold=True, color="E94560", size=10, name="Segoe UI")
        tot_fill = PatternFill("solid", fgColor="0F3460")
        for ci, val in enumerate(["Total", total, "100.0%"], 1):
            c = ws2.cell(tr, ci, val)
            c.fill, c.font, c.border = tot_fill, tot_font, border
            c.alignment = left_al if ci == 1 else center_al
        ws2.row_dimensions[tr].height = 22

        try:
            wb.save(path)
        except Exception as e:
            messagebox.showerror("Export Failed", f"Could not save Excel file:\n{e}")
            return
        self._export_status.set(f"✓  Saved  →  {os.path.basename(path)}")
        self.after(5000, lambda: self._export_status.set(""))

    # ── PDF export ────────────────────────────────────────────────────────────

    def _export_pdf(self):
        records = self._load_records()
        if not records:
            messagebox.showinfo("Empty", "No records to export.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=f"Report {datetime.now().strftime('%Y-%m-%d')}.pdf",
            filetypes=[("PDF File", "*.pdf")],
            title="Save as PDF",
        )
        if not path:
            return

        doc = SimpleDocTemplate(
            path, pagesize=landscape(A4),
            leftMargin=1.5*cm, rightMargin=1.5*cm,
            topMargin=2*cm,    bottomMargin=1.5*cm,
        )

        dark   = colors.HexColor("#1A1A2E")
        navy   = colors.HexColor("#0F3460")
        purple = colors.HexColor("#533483")
        slate  = colors.HexColor("#CBD5E1")
        row1   = colors.HexColor("#F0F4FF")
        row2   = colors.white

        title_s  = ParagraphStyle("t",  fontName="Helvetica-Bold", fontSize=20,
                                   textColor=dark, spaceAfter=4)
        sub_s    = ParagraphStyle("s",  fontName="Helvetica", fontSize=10,
                                   textColor=colors.HexColor("#8892A4"), spaceAfter=18)
        h2_s     = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13,
                                   textColor=dark, spaceBefore=14, spaceAfter=8)

        elems = []
        elems.append(Paragraph("Issue Tracker  —  Report", title_s))
        elems.append(Paragraph(
            f"Generated {datetime.now().strftime('%B %d, %Y  •  %H:%M')}  "
            f"•  {len(records)} record{'s' if len(records) != 1 else ''}",
            sub_s,
        ))

        # Summary table
        elems.append(Paragraph("Issue Breakdown", h2_s))
        counts = {}
        for r in records:
            counts[r["Issue Type"]] = counts.get(r["Issue Type"], 0) + 1

        sd = [["Issue Type", "Count", "% of Total"]]
        for issue in ISSUE_TYPES:
            c = counts.get(issue, 0)
            sd.append([issue, str(c), f"{c / len(records) * 100:.1f}%"])

        st = Table(sd, colWidths=[5.5*cm, 2.5*cm, 3*cm])
        st.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0), navy),
            ("TEXTCOLOR",      (0, 0), (-1, 0), colors.white),
            ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",       (0, 0), (-1, -1), 9),
            ("ALIGN",          (1, 0), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [row1, row2]),
            ("GRID",           (0, 0), (-1, -1), 0.4, slate),
            ("TOPPADDING",     (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 6),
        ]))
        elems.append(st)
        elems.append(Spacer(1, 0.5*cm))

        # Full records table
        elems.append(Paragraph("All Records", h2_s))
        cell_s = ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10)
        td = [HEADERS]
        for r in records:
            td.append([r["ID"], r["Timestamp"], r["Customer"],
                        r["Location"],
                        Paragraph(r["Issue Type"], cell_s),
                        Paragraph(r.get("Solution", ""), cell_s),
                        Paragraph(r.get("Explanation", ""), cell_s),
                        Paragraph(r.get("Comment", ""), cell_s)])

        mt = Table(td, colWidths=[0.9*cm, 3.3*cm, 3*cm, 3*cm, 4*cm, 5*cm, 5*cm, 2.5*cm],
                   repeatRows=1)
        mt.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0), purple),
            ("TEXTCOLOR",      (0, 0), (-1, 0), colors.white),
            ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",       (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [row1, row2]),
            ("GRID",           (0, 0), (-1, -1), 0.3, slate),
            ("TOPPADDING",     (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
            ("VALIGN",         (0, 0), (-1, -1), "TOP"),
        ]))
        elems.append(mt)

        try:
            doc.build(elems)
        except Exception as e:
            messagebox.showerror("Export Failed", f"Could not save PDF file:\n{e}")
            return
        self._export_status.set(f"✓  Saved  →  {os.path.basename(path)}")
        self.after(5000, lambda: self._export_status.set(""))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    App().mainloop()

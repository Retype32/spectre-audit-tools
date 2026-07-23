"""
theme.py — visual theme constants and Qt stylesheet.

To change the look (colors, accent, fonts), edit only this file.
"""

# =============================================================================
# THEME — Aurora Dark palette
# Aesthetic: modern SaaS intelligence platform. Deep space backgrounds,
# electric indigo-blue accent, real semantic status colours.
# Inspired by: Linear, Vercel, Arc, Raycast, Figma dark mode.
# =============================================================================
class Theme:
    # ── Backgrounds — strong contrast between sidebar and content ───────
    BG          = "#090c12"   # content area — very dark near-black
    SURFACE     = "#111827"   # sidebar & panel surfaces — clearly distinct navy
    ELEVATED    = "#161e32"   # input fields / raised card surfaces
    HOVER       = "#1c2540"   # hover state
    SELECTED    = "#1f2c4e"   # active / selected state

    # ── Borders — visible against dark backgrounds ───────────────────────
    BORDER      = "#243050"   # standard border — clearly visible
    BORDER_S    = "#151c30"   # subtle hairline divider

    # ── Text ────────────────────────────────────────────────────────────
    TXT         = "#e8eef8"   # primary — near white
    TXT_2       = "#8893b0"   # secondary — blue-grey
    TXT_3       = "#4a5878"   # tertiary — muted
    TXT_DIM     = "#202a44"   # dimmed / disabled

    # ── Accent — electric indigo-blue ───────────────────────────────────
    ACCENT      = "#5b8af5"   # primary interactive colour
    ACCENT_H    = "#7aa4ff"   # hover — lighter
    ACCENT_D    = "#3b6ee0"   # pressed — deeper
    # Qt QSS rgba() requires 0-255 integer for alpha, NOT 0.0-1.0 float
    ACCENT_GLOW = "rgba(91,138,245,46)"    # ~18% opacity
    ACCENT_DIM  = "rgba(91,138,245,26)"    # ~10% opacity

    # ── Status — real semantic colours ──────────────────────────────────
    OK          = "#36c98a"   # emerald green — success / positive
    OK_DIM      = "#09241a"   # success background tint
    WARN        = "#f0a030"   # amber — warning
    WARN_DIM    = "#231700"   # amber background tint
    DANGER      = "#ef4f44"   # red — danger / error
    DANGER_DIM  = "#210c0b"   # red background tint
    INFO        = "#5b8af5"   # blue info (= accent)
    GOLD        = "#efc050"   # gold / highlight
    PURPLE      = "#9b72ef"   # violet / accent-2

    # ── Data / money ────────────────────────────────────────────────────
    MONEY       = "#7aa4ff"   # bright blue for monetary values
    NEG         = "#ef4f44"   # red — negative value
    POS         = "#36c98a"   # green — positive value


# =============================================================================
# FONT PRESETS
# =============================================================================
FONT_PRESETS = [
    {
        "name":    "DM Sans",
        "ui":      "DM Sans, Trebuchet MS, Segoe UI, sans-serif",
        "mono":    "DM Mono, Consolas, monospace",
        "display": "DM Sans",
        "fallback":"Trebuchet MS, Segoe UI, sans-serif",
        "mono_fb": "Consolas, monospace",
    },
    {
        "name":    "Jakarta",
        "ui":      "Plus Jakarta Sans, Calibri, Segoe UI, sans-serif",
        "mono":    "JetBrains Mono, Consolas, monospace",
        "display": "Plus Jakarta Sans",
        "fallback":"Calibri, Segoe UI, sans-serif",
        "mono_fb": "Consolas, monospace",
    },
    {
        "name":    "IBM Plex",
        "ui":      "IBM Plex Sans, Century Gothic, Segoe UI, sans-serif",
        "mono":    "IBM Plex Mono, Courier New, monospace",
        "display": "IBM Plex Sans",
        "fallback":"Century Gothic, Segoe UI, sans-serif",
        "mono_fb": "Courier New, monospace",
    },
    {
        "name":    "Roboto",
        "ui":      "Roboto, Arial, sans-serif",
        "mono":    "Roboto Mono, Consolas, monospace",
        "display": "Roboto",
        "fallback":"Arial, sans-serif",
        "mono_fb": "Consolas, monospace",
    },
    {
        "name":    "Segoe UI",
        "ui":      "Segoe UI, sans-serif",
        "mono":    "Consolas, monospace",
        "display": "Segoe UI",
        "fallback":"Segoe UI, sans-serif",
        "mono_fb": "Consolas, monospace",
    },
]

_active_preset_idx = 4

def get_font_preset():
    return FONT_PRESETS[_active_preset_idx]

def set_font_preset(idx: int):
    global _active_preset_idx
    _active_preset_idx = idx % len(FONT_PRESETS)

def FONT_FAMILY():
    return get_font_preset()["ui"]

def FONT_MONO():
    return get_font_preset()["mono"]


# =============================================================================
# QSS STYLESHEET — applied app-wide
# NOTE: All rgba() values use 0-255 integer alpha, as required by Qt QSS.
# =============================================================================
def build_qss() -> str:
    T   = Theme
    fp  = get_font_preset()
    FF  = fp["ui"]
    FM  = fp["mono"]
    return f"""
    /* ================================================================
       BASE
    ================================================================ */
    QWidget {{
        background: {T.BG};
        color: {T.TXT};
        font-family: {FF};
        font-size: 13px;
        letter-spacing: 0.1px;
    }}
    QMainWindow, QDialog {{ background: {T.BG}; }}

    /* ================================================================
       SIDEBAR  — distinctly lighter navy vs content background
    ================================================================ */
    #sidebar {{
        background: {T.SURFACE};
        border-right: 1px solid {T.BORDER_S};
    }}
    #sidebarLogo {{
        color: {T.TXT};
        font-family: {FF};
        font-size: 17px;
        font-weight: 800;
        letter-spacing: -0.2px;
        padding: 20px 20px 2px 20px;
    }}
    #sidebarVersion {{
        color: {T.TXT_3};
        font-size: 10px;
        letter-spacing: 0.8px;
        padding: 0 20px 16px 20px;
        font-family: {FM};
    }}

    /* ── Nav buttons — Linear-style: flat left / rounded right pill ─────
       The active state uses a gradient bg + vivid left border so it's
       immediately obvious which page is active.
    ─────────────────────────────────────────────────────────────────── */
    QPushButton#navBtn {{
        background: transparent;
        color: {T.TXT_3};
        border: none;
        text-align: left;
        padding: 7px 16px 7px 14px;
        margin: 1px 10px 1px 0px;
        border-top-right-radius: 9px;
        border-bottom-right-radius: 9px;
        border-top-left-radius: 0px;
        border-bottom-left-radius: 0px;
        font-size: 13px;
        font-weight: 400;
        letter-spacing: 0.1px;
    }}
    QPushButton#navBtn:hover {{
        background: rgba(255,255,255,12);
        color: {T.TXT_2};
    }}
    QPushButton#navBtn:checked {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(91,138,245,60), stop:0.15 rgba(91,138,245,35),
            stop:1 rgba(91,138,245,10));
        color: {T.ACCENT_H};
        border-left: 3px solid {T.ACCENT};
        font-weight: 600;
    }}
    QPushButton#navBtn:pressed {{
        background: {T.SELECTED};
        border-left: 3px solid {T.ACCENT};
    }}

    /* ================================================================
       CARDS / SURFACES
    ================================================================ */
    QFrame#card {{
        background: {T.SURFACE};
        border: 1px solid {T.BORDER_S};
        border-radius: 12px;
    }}
    QFrame#card:hover {{
        border: 1px solid {T.BORDER};
    }}
    QFrame#cardElevated {{
        background: {T.ELEVATED};
        border: 1px solid {T.BORDER};
        border-radius: 12px;
    }}
    QFrame#cardElevated:hover {{
        border: 1px solid rgba(91,138,245,100);
        background: {T.HOVER};
    }}

    QLabel#cardTitle {{
        color: {T.TXT};
        font-size: 14px;
        font-weight: 700;
        letter-spacing: -0.1px;
    }}
    QLabel#cardSubtitle {{
        color: {T.TXT_3};
        font-size: 11px;
        letter-spacing: 0.2px;
    }}
    QLabel#sectionLabel {{
        color: {T.TXT_3};
        font-size: 9.5px;
        font-weight: 700;
        letter-spacing: 1.5px;
    }}
    QLabel#fieldLabel {{
        color: {T.TXT_2};
        font-size: 12px;
        font-weight: 500;
        letter-spacing: 0.1px;
    }}

    /* ================================================================
       INPUTS
    ================================================================ */
    QLineEdit, QDateEdit, QComboBox, QTextEdit {{
        background: {T.ELEVATED};
        color: {T.TXT};
        border: 1px solid {T.BORDER};
        border-radius: 8px;
        padding: 8px 12px;
        selection-background-color: {T.ACCENT_D};
        selection-color: white;
        font-family: {FF};
        font-size: 13px;
    }}
    QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QTextEdit:focus {{
        border: 2px solid {T.ACCENT};
        background: {T.ELEVATED};
    }}
    QLineEdit:disabled, QDateEdit:disabled, QComboBox:disabled {{
        color: {T.TXT_3};
        background: {T.SURFACE};
        border-color: {T.BORDER_S};
    }}
    QComboBox::drop-down {{ border: none; padding-right: 6px; }}
    QComboBox::down-arrow {{
        width: 0; height: 0;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {T.TXT_3};
        margin-right: 10px;
    }}
    QComboBox QAbstractItemView {{
        background: {T.ELEVATED};
        border: 1px solid {T.BORDER};
        border-radius: 8px;
        selection-background-color: {T.HOVER};
        selection-color: {T.TXT};
        outline: 0;
        padding: 4px;
    }}
    QDateEdit::up-button, QDateEdit::down-button {{ width: 0; }}

    /* ================================================================
       BUTTONS
    ================================================================ */
    QPushButton {{
        background: {T.ELEVATED};
        color: {T.TXT_2};
        border: 1px solid {T.BORDER};
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 500;
        letter-spacing: 0.2px;
        font-family: {FF};
        font-size: 13px;
    }}
    QPushButton:hover {{
        background: {T.HOVER};
        border-color: rgba(91,138,245,120);
        color: {T.TXT};
    }}
    QPushButton:pressed {{
        background: {T.SELECTED};
        border-color: {T.ACCENT};
        color: {T.TXT_2};
        padding-top: 9px;
        padding-bottom: 7px;
    }}
    QPushButton:disabled {{
        color: {T.TXT_DIM};
        background: {T.SURFACE};
        border-color: {T.BORDER_S};
    }}

    /* Primary — electric gradient */
    QPushButton#primary {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {T.ACCENT_H}, stop:1 {T.ACCENT_D});
        color: #ffffff;
        border: 1px solid {T.ACCENT_D};
        border-radius: 8px;
        font-weight: 700;
        letter-spacing: 0.2px;
        padding: 8px 18px;
    }}
    QPushButton#primary:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #90bcff, stop:1 {T.ACCENT});
        border-color: {T.ACCENT};
    }}
    QPushButton#primary:pressed {{
        background: {T.ACCENT_D};
        border-color: #2a52c0;
        padding-top: 9px;
        padding-bottom: 7px;
    }}
    QPushButton#primary:disabled {{
        background: {T.BORDER};
        border-color: {T.BORDER_S};
        color: {T.TXT_3};
    }}

    /* Success */
    QPushButton#success {{
        background: {T.OK_DIM};
        color: {T.OK};
        border: 1px solid rgba(54,201,138,56);
        border-radius: 8px;
        font-weight: 600;
    }}
    QPushButton#success:hover {{
        background: {T.OK};
        color: #04130e;
        border-color: {T.OK};
    }}
    QPushButton#success:pressed {{
        background: #1a6040;
        border-color: #0a3020;
        color: {T.OK};
        padding-top: 9px;
        padding-bottom: 7px;
    }}

    /* Danger */
    QPushButton#danger {{
        background: transparent;
        color: {T.DANGER};
        border: 1px solid rgba(239,79,68,92);
        border-radius: 8px;
    }}
    QPushButton#danger:hover {{
        background: {T.DANGER};
        color: white;
        border-color: {T.DANGER};
    }}
    QPushButton#danger:pressed {{
        background: #8a2020;
        border-color: #5a1010;
        color: white;
        padding-top: 9px;
        padding-bottom: 7px;
    }}

    /* Ghost */
    QPushButton#ghost {{
        background: transparent;
        border: 1px solid transparent;
        color: {T.TXT_3};
        border-radius: 8px;
    }}
    QPushButton#ghost:hover {{
        color: {T.TXT_2};
        background: rgba(255,255,255,10);
    }}
    QPushButton#ghost:pressed {{
        background: {T.SELECTED};
        color: {T.TXT};
    }}

    /* ================================================================
       TABLES
    ================================================================ */
    QTableView {{
        background: {T.SURFACE};
        alternate-background-color: rgba(0,0,0,30);
        gridline-color: {T.BORDER_S};
        border: 1px solid {T.BORDER_S};
        border-radius: 10px;
        selection-background-color: {T.SELECTED};
        selection-color: {T.TXT};
        font-family: {FM};
        font-size: 12px;
        outline: 0;
    }}
    QTableView::item {{ padding: 8px 12px; border: 0; }}
    QTableView::item:selected {{ background: {T.SELECTED}; color: {T.TXT}; }}
    QTableView::item:hover {{ background: {T.HOVER}; }}

    QHeaderView::section {{
        background: {T.BG};
        color: {T.TXT_3};
        padding: 9px 12px;
        border: none;
        border-right: 1px solid {T.BORDER_S};
        border-bottom: 1px solid {T.BORDER};
        font-family: {FF};
        font-weight: 700;
        font-size: 10px;
        letter-spacing: 1.2px;
    }}
    QHeaderView::section:hover {{
        background: {T.ELEVATED};
        color: {T.TXT_2};
    }}

    /* ================================================================
       SCROLLBARS
    ================================================================ */
    QScrollBar:vertical {{
        background: transparent;
        width: 7px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(100,120,170,71);
        border-radius: 3px;
        min-height: 32px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: rgba(100,120,170,140);
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 7px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: rgba(100,120,170,71);
        border-radius: 3px;
        min-width: 32px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: rgba(100,120,170,140);
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

    /* ================================================================
       STATUS BAR
    ================================================================ */
    QStatusBar {{
        background: {T.SURFACE};
        color: {T.TXT_3};
        border-top: 1px solid {T.BORDER_S};
        font-size: 11px;
        font-family: {FM};
        letter-spacing: 0.3px;
    }}
    QStatusBar::item {{ border: none; }}

    /* ================================================================
       TOOLTIP
    ================================================================ */
    QToolTip {{
        background: {T.ELEVATED};
        color: {T.TXT};
        border: 1px solid {T.BORDER};
        border-radius: 7px;
        padding: 6px 10px;
        font-size: 12px;
    }}

    /* ================================================================
       TABS
    ================================================================ */
    QTabBar::tab {{
        background: transparent;
        color: {T.TXT_3};
        padding: 7px 16px;
        border: none;
        border-bottom: 2px solid transparent;
        font-weight: 500;
        font-size: 12px;
        margin-bottom: 1px;
    }}
    QTabBar::tab:hover {{ color: {T.TXT_2}; }}
    QTabBar::tab:selected {{
        color: {T.ACCENT_H};
        border-bottom: 2px solid {T.ACCENT};
        font-weight: 600;
    }}
    QTabWidget::pane {{
        border: 1px solid {T.BORDER_S};
        border-radius: 10px;
    }}

    /* ================================================================
       SPLITTERS
    ================================================================ */
    QSplitter::handle {{
        background: {T.BORDER_S};
        width: 1px;
        height: 1px;
    }}

    /* ================================================================
       CHECKBOX
    ================================================================ */
    QCheckBox {{
        color: {T.TXT_2};
        spacing: 8px;
        font-size: 13px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 2px solid {T.BORDER};
        border-radius: 5px;
        background: {T.ELEVATED};
    }}
    QCheckBox::indicator:hover {{ border-color: {T.TXT_3}; }}
    QCheckBox::indicator:checked {{
        background: {T.ACCENT};
        border-color: {T.ACCENT};
    }}

    /* ================================================================
       GROUPBOX
    ================================================================ */
    QGroupBox {{
        color: {T.TXT_3};
        border: 1px solid {T.BORDER_S};
        border-radius: 10px;
        margin-top: 14px;
        padding-top: 10px;
        font-size: 9.5px;
        font-weight: 700;
        letter-spacing: 1.5px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
        background: {T.BG};
    }}

    /* ================================================================
       PROGRESS BAR
    ================================================================ */
    QProgressBar {{
        background: {T.ELEVATED};
        border: 1px solid {T.BORDER_S};
        border-radius: 4px;
        height: 6px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {T.ACCENT}, stop:1 {T.ACCENT_H});
        border-radius: 4px;
    }}

    /* ================================================================
       SPIN BOX
    ================================================================ */
    QSpinBox, QDoubleSpinBox {{
        background: {T.ELEVATED};
        color: {T.TXT};
        border: 1px solid {T.BORDER};
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 13px;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 2px solid {T.ACCENT};
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button,
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        width: 0;
    }}
    """

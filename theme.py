"""
theme.py — visual theme constants and Qt stylesheet.

To change the look (colors, accent, fonts), edit only this file.
"""

# =============================================================================
# THEME — Deep obsidian / cold steel palette
# Aesthetic: refined intelligence tool. Like a financial terminal
# crossed with a high-end design tool. Precise, cool, unapologetic.
# =============================================================================
class Theme:
    # Backgrounds — pure black to deep navy
    BG          = "#05070d"   # window — near-pure black
    SURFACE     = "#090e18"   # cards — deep navy-black
    ELEVATED    = "#0e1628"   # input bg — dark navy
    HOVER       = "#121e35"   # hover — navy
    SELECTED    = "#162440"   # selected — mid navy

    # Borders — navy-toned
    BORDER      = "#1a2a45"
    BORDER_S    = "#0f1a2e"   # subtle divider

    # Text — cool blue-whites
    TXT         = "#dde8f5"   # primary — icy white
    TXT_2       = "#7a96b8"   # secondary — steel blue
    TXT_3       = "#3d5470"   # tertiary — muted blue
    TXT_DIM     = "#243348"   # dimmed — deep blue-grey

    # Accent — bright royal blue. The primary interactive color.
    ACCENT      = "#4d9fff"   # bright blue
    ACCENT_H    = "#74b5ff"   # hover — lighter blue
    ACCENT_D    = "#2d7dd6"   # pressed — deeper blue
    ACCENT_GLOW = "rgba(77, 159, 255, 0.12)"

    # Status colors — all blue family, differentiated by brightness/saturation
    OK          = "#60c8ff"   # light sky blue — positive/success
    OK_DIM      = "#0a1f3d"   # dark navy dim for success backgrounds
    WARN        = "#93b8ff"   # soft periwinkle — warning (was yellow)
    DANGER      = "#3d7fff"   # vivid cobalt — alert/danger (was red)
    INFO        = "#4d9fff"   # same as accent
    GOLD        = "#a8c8ff"   # pale blue — was gold/yellow
    PURPLE      = "#7eb8ff"   # cornflower blue — was purple

    # Mono / data colors
    MONEY       = "#74b5ff"   # bright blue for amounts
    NEG         = "#3d7fff"   # cobalt — negative values (was red)
    POS         = "#60c8ff"   # sky blue — positive values (was green)


# =============================================================================
# FONT PRESETS — 5 options switchable at runtime via Settings.
#
# Each preset lists fonts in priority order. Qt picks the first one that is
# actually installed on the system. Fonts marked with (*) can be installed
# freely from fonts.google.com to get the best result; the fallbacks are
# guaranteed Windows/macOS system fonts that look meaningfully different.
#
# To install: download TTF from fonts.google.com, right-click -> Install.
# Then restart Spectre for the new font to activate.
# =============================================================================
FONT_PRESETS = [
    {
        "name":    "DM Sans",
        # (*) DM Sans — geometric, modern SaaS feel
        # Fallback: Trebuchet MS — humanist, similar warmth
        "ui":      "DM Sans, Trebuchet MS, Segoe UI, sans-serif",
        "mono":    "DM Mono, Consolas, monospace",
        "display": "DM Sans",
        "fallback":"Trebuchet MS, Segoe UI, sans-serif",
        "mono_fb": "Consolas, monospace",
    },
    {
        "name":    "Jakarta",
        # (*) Plus Jakarta Sans — confident, slightly quirky
        # Fallback: Calibri — rounded, modern
        "ui":      "Plus Jakarta Sans, Calibri, Segoe UI, sans-serif",
        "mono":    "JetBrains Mono, Consolas, monospace",
        "display": "Plus Jakarta Sans",
        "fallback":"Calibri, Segoe UI, sans-serif",
        "mono_fb": "Consolas, monospace",
    },
    {
        "name":    "IBM Plex",
        # (*) IBM Plex Sans — engineering, terminal personality
        # Fallback: Century Gothic — geometric, distinctive
        "ui":      "IBM Plex Sans, Century Gothic, Segoe UI, sans-serif",
        "mono":    "IBM Plex Mono, Courier New, monospace",
        "display": "IBM Plex Sans",
        "fallback":"Century Gothic, Segoe UI, sans-serif",
        "mono_fb": "Courier New, monospace",
    },
    {
        "name":    "Roboto",
        # (*) Roboto — clean, neutral, Android/Material standard
        # Fallback: Arial — similar neutral grotesque
        "ui":      "Roboto, Arial, sans-serif",
        "mono":    "Roboto Mono, Consolas, monospace",
        "display": "Roboto",
        "fallback":"Arial, sans-serif",
        "mono_fb": "Consolas, monospace",
    },
    {
        "name":    "Segoe UI",
        # Built-in Windows system font — always available, crisp at small sizes
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

# Convenience — returns current UI font name string
def FONT_FAMILY():
    return get_font_preset()["ui"]

def FONT_MONO():
    return get_font_preset()["mono"]


# =============================================================================
# QSS STYLESHEET — applied app-wide
# =============================================================================
def build_qss() -> str:
    T = Theme
    fp  = get_font_preset()
    FF  = fp["ui"]    # full CSS stack e.g. "DM Sans, Trebuchet MS, sans-serif"
    FM  = fp["mono"]  # full CSS stack e.g. "DM Mono, Consolas, monospace"
    return f"""
    /* === Base === */
    QWidget {{
        background: {T.BG};
        color: {T.TXT};
        font-family: {FF};
        font-size: 13px;
        letter-spacing: 0.1px;
    }}
    QMainWindow, QDialog {{ background: {T.BG}; }}

    /* === Sidebar === */
    #sidebar {{
        background: {T.SURFACE};
        border-right: 1px solid {T.BORDER_S};
    }}
    #sidebarLogo {{
        color: {T.TXT};
        font-family: {FF};
        font-size: 17px;
        font-weight: 700;
        letter-spacing: 0.3px;
        padding: 14px 20px 4px 20px;
    }}
    #sidebarVersion {{
        color: {T.TXT_3};
        font-size: 10px;
        letter-spacing: 0.6px;
        padding: 0 20px 12px 20px;
        font-family: {FM};
    }}
    #sidebarSection {{
        color: {T.TXT_DIM};
        font-size: 9.5px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 2px;
        padding: 10px 20px 4px 20px;
    }}
    QPushButton#navBtn {{
        background: transparent;
        color: {T.TXT_3};
        border: none;
        border-left: 2px solid transparent;
        text-align: left;
        padding: 8px 20px;
        font-size: 13px;
        font-weight: 400;
        letter-spacing: 0.1px;
    }}
    QPushButton#navBtn:hover {{
        background: {T.HOVER};
        color: {T.TXT_2};
    }}
    QPushButton#navBtn:checked {{
        background: {T.ELEVATED};
        color: {T.TXT};
        border-left: 2px solid {T.ACCENT};
        font-weight: 600;
    }}

    /* === Cards / surfaces === */
    QFrame#card {{
        background: {T.SURFACE};
        border: 1px solid {T.BORDER_S};
        border-radius: 8px;
    }}
    QFrame#cardElevated {{
        background: {T.ELEVATED};
        border: 1px solid {T.BORDER};
        border-radius: 8px;
    }}
    QLabel#cardTitle {{
        color: {T.TXT};
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 0.2px;
    }}
    QLabel#cardSubtitle {{
        color: {T.TXT_3};
        font-size: 11px;
        letter-spacing: 0.3px;
    }}
    QLabel#sectionLabel {{
        color: {T.TXT_3};
        font-size: 9.5px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.5px;
    }}
    QLabel#fieldLabel {{
        color: {T.TXT_2};
        font-size: 12px;
        font-weight: 500;
        letter-spacing: 0.2px;
    }}

    /* === Inputs === */
    QLineEdit, QDateEdit, QComboBox, QTextEdit {{
        background: {T.ELEVATED};
        color: {T.TXT};
        border: 1px solid {T.BORDER};
        border-radius: 6px;
        padding: 7px 10px;
        selection-background-color: {T.ACCENT_D};
        selection-color: white;
        font-family: {FF};
    }}
    QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QTextEdit:focus {{
        border: 1px solid {T.ACCENT};
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
        margin-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background: {T.ELEVATED};
        border: 1px solid {T.BORDER};
        border-radius: 6px;
        selection-background-color: {T.HOVER};
        selection-color: {T.TXT};
        outline: 0;
        padding: 2px;
    }}
    QDateEdit::up-button, QDateEdit::down-button {{ width: 0; }}

    /* === Buttons === */
    QPushButton {{
        background: {T.ELEVATED};
        color: {T.TXT_2};
        border: 1px solid {T.BORDER};
        border-radius: 6px;
        padding: 7px 16px;
        font-weight: 500;
        letter-spacing: 0.2px;
        font-family: {FF};
    }}
    QPushButton:hover {{
        background: {T.HOVER};
        border-color: {T.TXT_3};
        color: {T.TXT};
    }}
    QPushButton:pressed {{
        background: #050a14;
        border-color: {T.ACCENT};
        border-top: 2px solid {T.BORDER_S};
        color: {T.TXT_2};
        padding-top: 8px;
        padding-bottom: 6px;
    }}
    QPushButton:disabled {{
        color: {T.TXT_DIM};
        background: {T.SURFACE};
        border-color: {T.BORDER_S};
    }}

    QPushButton#primary {{
        background: {T.ACCENT};
        color: #ffffff;
        border: 1px solid {T.ACCENT_D};
        font-weight: 700;
        letter-spacing: 0.3px;
    }}
    QPushButton#primary:hover {{
        background: {T.ACCENT_H};
        border-color: {T.ACCENT};
        color: #ffffff;
    }}
    QPushButton#primary:pressed {{
        background: #1a4d8a;
        border-color: #1a4d8a;
        border-top: 2px solid #0d2e5e;
        color: #ffffff;
        padding-top: 8px;
        padding-bottom: 6px;
    }}

    QPushButton#success {{
        background: {T.OK_DIM};
        color: {T.OK};
        border: 1px solid {T.OK_DIM};
        font-weight: 600;
    }}
    QPushButton#success:hover {{ background: {T.OK}; color: #05070d; }}
    QPushButton#success:pressed {{
        background: #062a40;
        border-top: 2px solid #041e2e;
        color: {T.OK};
        padding-top: 8px; padding-bottom: 6px;
    }}

    QPushButton#danger {{
        background: transparent;
        color: {T.DANGER};
        border: 1px solid rgba(61, 127, 255, 0.4);
    }}
    QPushButton#danger:hover {{ background: {T.DANGER}; color: white; border-color: {T.DANGER}; }}
    QPushButton#danger:pressed {{
        background: #1a3a8a;
        border-top: 2px solid #0d2060;
        color: white;
        padding-top: 8px; padding-bottom: 6px;
    }}

    QPushButton#ghost {{
        background: transparent;
        border: 1px solid transparent;
        color: {T.TXT_3};
    }}
    QPushButton#ghost:hover {{ color: {T.TXT_2}; background: {T.HOVER}; }}
    QPushButton#ghost:pressed {{ background: {T.SELECTED}; color: {T.TXT}; }}

    QPushButton#navBtn:pressed {{
        background: {T.SELECTED};
        border-left: 2px solid {T.ACCENT};
    }}

    /* === Tables === */
    QTableView {{
        background: {T.SURFACE};
        alternate-background-color: {T.BG};
        gridline-color: {T.BORDER_S};
        border: 1px solid {T.BORDER_S};
        border-radius: 6px;
        selection-background-color: {T.SELECTED};
        selection-color: {T.TXT};
        font-family: {FM};
        font-size: 12px;
        outline: 0;
    }}
    QTableView::item {{ padding: 7px 10px; border: 0; }}
    QTableView::item:selected {{ background: {T.SELECTED}; color: {T.TXT}; }}
    QTableView::item:hover {{ background: {T.HOVER}; }}

    QHeaderView::section {{
        background: {T.BG};
        color: {T.TXT_3};
        padding: 8px 10px;
        border: none;
        border-right: 1px solid {T.BORDER_S};
        border-bottom: 1px solid {T.BORDER};
        font-family: {FF};
        font-weight: 700;
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    QHeaderView::section:hover {{ background: {T.ELEVATED}; color: {T.TXT_2}; }}

    /* === Scrollbars === */
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {T.BORDER};
        border-radius: 4px;
        min-height: 32px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {T.TXT_3}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 8px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {T.BORDER};
        border-radius: 4px;
        min-width: 32px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {T.TXT_3}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

    /* === Status bar === */
    QStatusBar {{
        background: {T.SURFACE};
        color: {T.TXT_3};
        border-top: 1px solid {T.BORDER_S};
        font-size: 11px;
        font-family: {FM};
        letter-spacing: 0.3px;
    }}
    QStatusBar::item {{ border: none; }}

    /* === Tooltip === */
    QToolTip {{
        background: {T.ELEVATED};
        color: {T.TXT};
        border: 1px solid {T.BORDER};
        border-radius: 5px;
        padding: 5px 9px;
        font-size: 12px;
    }}

    /* === Tabs === */
    QTabBar::tab {{
        background: transparent;
        color: {T.TXT_3};
        padding: 7px 16px;
        border: none;
        border-bottom: 2px solid transparent;
        font-weight: 500;
        font-size: 12px;
    }}
    QTabBar::tab:hover {{ color: {T.TXT_2}; }}
    QTabBar::tab:selected {{
        color: {T.ACCENT};
        border-bottom: 2px solid {T.ACCENT};
        font-weight: 600;
    }}
    QTabWidget::pane {{
        border: 1px solid {T.BORDER_S};
        border-radius: 6px;
    }}

    /* === Splitters === */
    QSplitter::handle {{
        background: {T.BORDER_S};
        width: 1px;
        height: 1px;
    }}

    /* === CheckBox === */
    QCheckBox {{
        color: {T.TXT_2};
        spacing: 8px;
        font-size: 13px;
    }}
    QCheckBox::indicator {{
        width: 15px;
        height: 15px;
        border: 1px solid {T.BORDER};
        border-radius: 4px;
        background: {T.ELEVATED};
    }}
    QCheckBox::indicator:hover {{ border-color: {T.TXT_3}; }}
    QCheckBox::indicator:checked {{
        background: {T.ACCENT};
        border-color: {T.ACCENT};
    }}

    /* === GroupBox === */
    QGroupBox {{
        color: {T.TXT_3};
        border: 1px solid {T.BORDER_S};
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 8px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        text-transform: uppercase;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 4px;
        background: {T.BG};
    }}
    """

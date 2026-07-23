"""
main.py — entry point for Spectre v2.0.

Run with:
    python main.py

Optional dependencies:
    pip install PySide6 pandas openpyxl xlrd

xlrd is only needed to read legacy .xls files (used by NON-VMS scanner
and SL79 No.3 database when those are saved as .xls). The app runs without
it but skips .xls files where xlsx is not available.
"""
import sys
import logging
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QPalette, QColor

from config import setup_logging, APP_VERSION
from theme import Theme, build_qss
from main_window import MainWindow


def main():
    setup_logging()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss())

    # Tighten default Qt palette to make sure popups (combo lists, tooltips)
    # use our colors even where QSS doesn't reach.
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(Theme.BG))
    pal.setColor(QPalette.Base, QColor(Theme.ELEVATED))
    pal.setColor(QPalette.Text, QColor(Theme.TXT))
    pal.setColor(QPalette.WindowText, QColor(Theme.TXT))
    pal.setColor(QPalette.Button, QColor(Theme.ELEVATED))
    pal.setColor(QPalette.ButtonText, QColor(Theme.TXT))
    pal.setColor(QPalette.Highlight, QColor(Theme.ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    pal.setColor(QPalette.ToolTipBase, QColor(Theme.ELEVATED))
    pal.setColor(QPalette.ToolTipText, QColor(Theme.TXT))
    app.setPalette(pal)

    win = MainWindow()
    win.show()
    logging.info(f"{APP_VERSION} ready")
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        try:
            QMessageBox.critical(None, "Fatal Error",
                                  f"Spectre failed to start:\n\n{e}")
        except Exception:
            pass
        sys.exit(1)

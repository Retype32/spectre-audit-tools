"""
widgets/data_table.py — pandas-backed Qt table model and sortable table view.

DataFrameModel — QAbstractTableModel wrapping a DataFrame, with type-aware
                 sorting, display formatting, and per-row metadata.
DataTable      — QTableView pre-configured with sorting/filtering proxy
                 and rowDoubleClicked / rowClicked signals.
"""
import datetime
import pandas as pd

from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Signal
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QTableView, QHeaderView, QAbstractItemView


class DataFrameModel(QAbstractTableModel):
    """A pandas DataFrame backed Qt table model. Handles type-aware sorting,
    display formatting, and per-row metadata (e.g. discrepancy color)."""

    def __init__(self, df=None, columns=None, parent=None):
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame(columns=columns or [])
        self._columns = list(columns) if columns is not None else list(self._df.columns)
        self._row_meta = {}   # row index -> dict (e.g. {"color": "#f87171"})

    def set_dataframe(self, df, row_meta=None):
        self.beginResetModel()
        self._df = (df.reset_index(drop=True) if df is not None
                    else pd.DataFrame(columns=self._columns))
        self._row_meta = row_meta or {}
        self.endResetModel()

    def add_row(self, values_dict, meta=None):
        new = pd.DataFrame([values_dict])
        # ensure column order
        for c in self._columns:
            if c not in new.columns:
                new[c] = ""
        new = new[self._columns]
        self.beginInsertRows(QModelIndex(), len(self._df), len(self._df))
        self._df = pd.concat([self._df, new], ignore_index=True)
        if meta:
            self._row_meta[len(self._df) - 1] = meta
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self._df = pd.DataFrame(columns=self._columns)
        self._row_meta = {}
        self.endResetModel()

    def row_data(self, row):
        if 0 <= row < len(self._df):
            return self._df.iloc[row].to_dict()
        return None

    def row_meta(self, row):
        return self._row_meta.get(row, {})

    # Qt API ----------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._columns[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if r >= len(self._df) or c >= len(self._columns):
            return None
        col = self._columns[c]
        v = self._df.iloc[r][col]
        if role == Qt.DisplayRole:
            return self._format(v)
        if role == Qt.ForegroundRole:
            meta = self._row_meta.get(r, {})
            if "fg" in meta:
                return QBrush(QColor(meta["fg"]))
            return None
        if role == Qt.BackgroundRole:
            meta = self._row_meta.get(r, {})
            if "bg" in meta:
                return QBrush(QColor(meta["bg"]))
            return None
        if role == Qt.TextAlignmentRole:
            try:
                float(v)
                return int(Qt.AlignRight | Qt.AlignVCenter)
            except (ValueError, TypeError):
                return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.UserRole:
            # raw value — used by sorter
            return v
        return None

    @staticmethod
    def _format(v):
        if v is None:
            return "—"
        if isinstance(v, float):
            if pd.isna(v):
                return "—"
            if v.is_integer():
                return f"{int(v):,}"
            return f"{v:,.2f}"
        if isinstance(v, (int,)):
            return f"{v:,}" if abs(v) >= 1000 else str(v)
        if isinstance(v, (datetime.date, datetime.datetime)):
            return v.strftime("%d/%m/%Y")
        s = str(v)
        return s if s != "" else "—"


class DataTable(QTableView):
    """Sortable, clickable, alternating-rows table.
    Use .set_dataframe(df, meta=...) or .model_obj.add_row(...) to populate."""

    rowDoubleClicked = Signal(dict)
    rowClicked = Signal(dict)

    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self._columns = list(columns)
        self.model_obj = DataFrameModel(columns=self._columns)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model_obj)
        self.proxy.setSortRole(Qt.UserRole)            # sort by raw value
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setModel(self.proxy)

        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(32)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setDefaultSectionSize(120)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)

        self.doubleClicked.connect(self._on_double)
        self.clicked.connect(self._on_clicked)

    def set_dataframe(self, df, row_meta=None):
        self.model_obj.set_dataframe(df, row_meta)

    def clear(self):
        self.model_obj.clear()

    def add_row(self, values_dict, meta=None):
        self.model_obj.add_row(values_dict, meta)

    def set_column_width(self, col_name, width):
        if col_name in self._columns:
            i = self._columns.index(col_name)
            self.setColumnWidth(i, width)

    def set_filter(self, text, column=-1):
        """Filter visible rows by text in given column (-1 = all)."""
        self.proxy.setFilterKeyColumn(column)
        self.proxy.setFilterFixedString(text)

    def _on_double(self, index):
        src = self.proxy.mapToSource(index)
        rd = self.model_obj.row_data(src.row())
        if rd is not None:
            self.rowDoubleClicked.emit(rd)

    def _on_clicked(self, index):
        src = self.proxy.mapToSource(index)
        rd = self.model_obj.row_data(src.row())
        if rd is not None:
            self.rowClicked.emit(rd)

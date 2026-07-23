"""widgets package — reusable Qt components."""
from widgets.cards import Card, StatCard, FieldLabel, StatusPill
from widgets.data_table import DataFrameModel, DataTable
from widgets.dialogs import DetailDialog, FilteredRowsDialog

__all__ = [
    "Card", "StatCard", "FieldLabel", "StatusPill",
    "DataFrameModel", "DataTable",
    "DetailDialog", "FilteredRowsDialog",
]

"""pages package — one file per sidebar tab."""
from pages.integrity import IntegrityPage
from pages.search import SearchPage
from pages.universal import UniversalSearchPage
from pages.slip_audit import SlipAuditPage
from pages.bag_counter import BagCounterPage
from pages.history import HistoryPage
from pages.cashier_db import CashierDbPage
from pages.nonvms import NonVmsPage
from pages.discovery import AmountDiscoveryPage
from pages.no3 import No3Page
from pages.settings import SettingsPage
from pages.analytics_dashboard import DashboardPage
from pages.analytics_risk import RiskScoringPage
from pages.analytics_trend import TrendAnalysisPage
from pages.analytics_export import ExportReportPage
from pages.analytics_quality import DataQualityPage
from pages.analytics_correlation import CorrelationPage
from pages.analytics_visual_report import VisualReportPage
from pages.analytics_cashier_performance import CashierPerformancePage
from pages.discrepancies_tab import DiscrepanciesPage
from pages.debug_log import DebugLogPage, install_memory_handler

__all__ = [
    "IntegrityPage", "SearchPage", "UniversalSearchPage",
    "SlipAuditPage", "BagCounterPage", "HistoryPage",
    "CashierDbPage", "NonVmsPage", "AmountDiscoveryPage", "No3Page",
    "SettingsPage",
    "DashboardPage", "RiskScoringPage", "TrendAnalysisPage",
    "ExportReportPage", "DataQualityPage", "CorrelationPage", "VisualReportPage",
    "CashierPerformancePage",
    "DiscrepanciesPage",
    "DebugLogPage", "install_memory_handler",
]

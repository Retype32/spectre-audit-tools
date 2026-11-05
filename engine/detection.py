"""
engine/detection.py — the three Integrity Check detection algorithms.

Pure pandas, no Qt. Takes a cleaned report DataFrame (see engine.report)
and returns the flagged rows as plain dicts, in the same shape the UI and
analytics pages already use: every column of the row plus '_line', the
row's line number in the source spreadsheet.
"""
from dataclasses import dataclass, field

from config import AMOUNT, LODGEMENT, OPERATOR, WALLET
from engine.report import EMPTY_WALLET

SUSPICIOUS_KEYS = [OPERATOR, WALLET, AMOUNT]


@dataclass
class IntegrityResult:
    exact_rows: list = field(default_factory=list)          # High Risk Duplicates
    suspicious_rows: list = field(default_factory=list)     # Suspicious Patterns
    shared_wallet_rows: list = field(default_factory=list)  # Shared Assets
    high_risk_count: int = 0        # duplicate pairs (rows // 2)
    suspicious_count: int = 0       # suspicious pairs (rows // 2)
    shared_wallet_count: int = 0    # wallets used by >1 operator


def row_dict(idx, row):
    """Row → dict with '_line' = spreadsheet line (header is line 1)."""
    d = {'_line': idx + 2}
    for col in row.index:
        d[col] = row[col]
    return d


def high_risk_keys(df, denoms):
    return [k for k in [OPERATOR, WALLET, LODGEMENT, AMOUNT] + list(denoms) if k in df.columns]


def find_exact_duplicates(df, denoms):
    """Rows identical on operator, wallet, slip, amount and every denomination."""
    return df[df.duplicated(subset=high_risk_keys(df, denoms), keep=False)].copy()


def find_suspicious(df, exact):
    """Rows sharing operator + wallet + amount that aren't exact duplicates."""
    all_pot = df[df.duplicated(subset=SUSPICIOUS_KEYS, keep=False)].copy()
    return all_pot[~all_pot.index.isin(exact.index)].copy()


def find_shared_wallets(df):
    """Series of wallet → number of distinct operators, for wallets with >1."""
    wc = df[df[WALLET] != EMPTY_WALLET].groupby(WALLET)[OPERATOR].nunique()
    return wc[wc > 1]


def _grouped_rows(frame, keys):
    """Row dicts ordered group by group (as shown in the UI tables)."""
    rows = []
    if frame.empty:
        return rows
    for _, grp in frame.groupby(keys, dropna=False):
        if len(grp) < 2:
            continue
        for idx, r in grp.iterrows():
            rows.append(row_dict(idx, r))
    return rows


def run_integrity_checks(df, denoms):
    """Run all three checks on a cleaned report DataFrame."""
    exact = find_exact_duplicates(df, denoms)
    sus = find_suspicious(df, exact)
    result = IntegrityResult(
        exact_rows=_grouped_rows(exact, high_risk_keys(df, denoms)),
        suspicious_rows=_grouped_rows(sus, SUSPICIOUS_KEYS),
        high_risk_count=len(exact) // 2,
        suspicious_count=len(sus) // 2,
    )
    if WALLET in df.columns:
        sw = find_shared_wallets(df)
        result.shared_wallet_count = len(sw)
        if len(sw):
            result.shared_wallet_rows = [row_dict(i, r)
                                         for i, r in df[df[WALLET].isin(sw.index)].iterrows()]
    return result

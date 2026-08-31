"""Shared revenue-model constants.

`revenue_leak.py` and `ad_traffic.py` both derive euro figures from the same
handful of assumptions (default revenue, AOV bucket, benchmark conversion
rate). They used to define these independently and had drifted apart — most
notably two different "benchmark CVR" values (2% vs 3%) feeding the same
report. Centralising them here means the report can no longer disagree with
itself about what "average" means.
"""

from __future__ import annotations

# Used whenever the operator hasn't supplied a real annual revenue figure.
DEFAULT_ANNUAL_REVENUE_EUR = 108_000.0  # = €9k/mnd legacy benchmark

# Single benchmark conversion rate used across the revenue model whenever no
# measured session data is available to back-derive a real CR.
BENCHMARK_CR = 0.03

# Assumed ad spend as a share of monthly revenue, used to size "wasted ad
# spend" euro figures when the operator hasn't supplied real spend.
AD_SPEND_SHARE_OF_REVENUE = 0.15


def aov_for_monthly_revenue(monthly_revenue_eur: float) -> float:
    """Bucketed AOV guess used only when no real AOV is supplied."""
    if monthly_revenue_eur < 50_000:
        return 75.0
    if monthly_revenue_eur < 250_000:
        return 95.0
    return 120.0

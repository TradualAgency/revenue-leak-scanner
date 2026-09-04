from datetime import UTC, datetime

from app.competitor_benchmark.comparison import build_comparisons
from app.competitor_benchmark.gap_pricing import price_gap_to_market
from app.competitor_benchmark.schemas import CompetitorSnapshot
from app.full_audit.schemas import FunnelModel, LighthouseScores, MobileCWV, Performance


def _snapshot(domain, lcp_ms):
    return CompetitorSnapshot(
        domain=domain, measure_status="ok", measured_at=datetime.now(UTC),
        performance=Performance(mobile=MobileCWV(lcp_ms=lcp_ms), lighthouse=LighthouseScores(performance=80)),
    )


def _funnel(monthly_revenue_eur=120_000.0):
    return FunnelModel(
        monthly_sessions=100_000, conversion_rate=0.02, aov_eur=60,
        monthly_revenue_eur=monthly_revenue_eur, monthly_purchases=2000,
        monthly_ad_spend_eur=18_000, mobile_share=0.70, paid_share=0.30,
    )


def test_gap_priced_when_store_slower_than_median():
    store = _snapshot("store.com", 4200)
    competitors = [_snapshot("c1.com", 2000), _snapshot("c2.com", 2100), _snapshot("c3.com", 2200)]
    comparisons = build_comparisons(store, competitors)
    funnel = _funnel()

    gaps, med_lo, med_hi, best_lo, best_hi = price_gap_to_market(comparisons, funnel)

    lcp_gap = next(g for g in gaps if g.finding_id == "gap.lcp_mobile")
    assert lcp_gap.median_value == 2100
    assert lcp_gap.store_value == 4200

    s_over = (4200 - 2100) / 1000  # 2.1
    exposure = (1 - funnel.paid_share) * funnel.mobile_share
    expected_uplift_low = min(0.10, s_over * 0.02)
    expected_uplift_high = min(0.25, s_over * 0.05)
    expected_low = funnel.monthly_revenue_eur * exposure * expected_uplift_low
    expected_high = funnel.monthly_revenue_eur * exposure * expected_uplift_high

    assert lcp_gap.gap_to_median_eur_low == expected_low
    assert lcp_gap.gap_to_median_eur_high == expected_high
    assert med_lo is not None and med_hi is not None


def test_no_gap_when_insufficient_measured_domains():
    store = _snapshot("store.com", 4200)
    competitors = [_snapshot("c1.com", 2000)]  # only 1 — insufficient
    comparisons = build_comparisons(store, competitors)
    gaps, med_lo, med_hi, best_lo, best_hi = price_gap_to_market(comparisons, _funnel())

    assert not any(g.finding_id == "gap.lcp_mobile" for g in gaps)
    assert med_lo is None
    assert med_hi is None


def test_slow_market_does_not_floor_median_at_2500ms():
    """The median must not be floored at the universal 2,500ms benchmark — a slow
    market showing as a small gap (not the full absolute-leak amount) is the honest
    outcome, and `market_is_also_below_benchmark` must say so."""
    store = _snapshot("store.com", 4500)
    competitors = [_snapshot("c1.com", 4100), _snapshot("c2.com", 4200), _snapshot("c3.com", 4300)]
    comparisons = build_comparisons(store, competitors)
    gaps, med_lo, med_hi, _, _ = price_gap_to_market(comparisons, _funnel())

    lcp_gap = next(g for g in gaps if g.finding_id == "gap.lcp_mobile")
    assert lcp_gap.median_value == 4200
    assert lcp_gap.market_is_also_below_benchmark is True

    # s_over should be based on the RAW median (300ms gap), not floored to 2500
    s_over_expected = (4500 - 4200) / 1000
    exposure = (1 - _funnel().paid_share) * _funnel().mobile_share
    expected_high = _funnel().monthly_revenue_eur * exposure * min(0.25, s_over_expected * 0.05)
    assert lcp_gap.gap_to_median_eur_high == expected_high

    # sanity: this must be much smaller than the "gap to the universal 2500ms
    # benchmark" would have been (a 2000ms gap) — proves no silent flooring occurred
    s_over_if_floored = (4500 - 2500) / 1000
    inflated_high = _funnel().monthly_revenue_eur * exposure * min(0.25, s_over_if_floored * 0.05)
    assert lcp_gap.gap_to_median_eur_high < inflated_high


def test_gap_to_best_emitted_alongside_gap_to_median():
    store = _snapshot("store.com", 4200)
    competitors = [_snapshot("c1.com", 1900), _snapshot("c2.com", 2100), _snapshot("c3.com", 2300)]
    comparisons = build_comparisons(store, competitors)
    gaps, _, _, best_lo, best_hi = price_gap_to_market(comparisons, _funnel())

    lcp_gap = next(g for g in gaps if g.finding_id == "gap.lcp_mobile")
    assert lcp_gap.best_value == 1900
    assert lcp_gap.gap_to_best_eur_high is not None
    # best (1900) is further from the store than median (2100) -> bigger gap
    assert lcp_gap.gap_to_best_eur_high > lcp_gap.gap_to_median_eur_high
    assert best_hi is not None and best_hi >= lcp_gap.gap_to_best_eur_high

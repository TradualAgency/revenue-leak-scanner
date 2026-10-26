from datetime import UTC, datetime

import pytest

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


def _shopify_checkout_snapshot(domain, fields):
    from app.full_audit.schemas import CheckoutFlow, PlatformArchitecture
    return CompetitorSnapshot(
        domain=domain, measure_status="ok", measured_at=datetime.now(UTC),
        platform=PlatformArchitecture(detected_platform="Shopify"),
        checkout=CheckoutFlow(probe_status="ok", fields_in_address_form=fields),
    )


def test_address_field_gap_counts_fields_over_the_market_median_not_over_ten():
    """18 fields against a market median of 12 is 6 fields too many. The old code
    counted fields over the absolute Baymard baseline of 10 (8 here) and so priced the
    absolute gap under a "vs. your market" label."""
    store = _shopify_checkout_snapshot("store.com", 18)
    competitors = [_shopify_checkout_snapshot(f"c{i}.com", 12) for i in range(3)]
    funnel = _funnel()

    gaps, *_ = price_gap_to_market(build_comparisons(store, competitors), funnel)

    fields_gap = next(g for g in gaps if g.finding_id == "gap.checkout_address_fields")
    n_over = 18 - 12
    assert fields_gap.gap_to_median_eur_low == funnel.monthly_revenue_eur * n_over * 0.005
    assert fields_gap.gap_to_median_eur_high == funnel.monthly_revenue_eur * n_over * 0.010


def _tbt_snapshot(domain, tbt_ms):
    return CompetitorSnapshot(
        domain=domain, measure_status="ok", measured_at=datetime.now(UTC),
        performance=Performance(mobile=MobileCWV(lcp_ms=2000), tbt_ms=tbt_ms,
                                lighthouse=LighthouseScores(performance=80)),
    )


@pytest.mark.parametrize("store_tbt", [450, 650])
def test_gap_inp_uses_the_same_curve_as_the_absolute_model(store_tbt):
    """Same ms over the reference → same uplift, whether the reference is Google's
    200ms threshold (absolute model) or a market median of 200ms (gap model). The gap
    model used to price per 100ms linearly while the absolute model stepped."""
    from app.full_audit.analyzers.benchmarks import inp_uplift
    from app.full_audit.analyzers.revenue_leak import calculate_revenue_leak

    store = _tbt_snapshot("store.com", store_tbt)
    competitors = [_tbt_snapshot(f"c{i}.com", 200) for i in range(3)]
    funnel = _funnel()
    gaps, *_ = price_gap_to_market(build_comparisons(store, competitors), funnel)
    gap = next(g for g in gaps if g.finding_id == "gap.inp_mobile")

    exposure = (1 - funnel.paid_share) * funnel.mobile_share
    low, high = inp_uplift(store_tbt - 200)
    assert gap.gap_to_median_eur_low == pytest.approx(funnel.monthly_revenue_eur * exposure * low)
    assert gap.gap_to_median_eur_high == pytest.approx(funnel.monthly_revenue_eur * exposure * high)

    absolute = calculate_revenue_leak(
        performance=Performance(tbt_ms=store_tbt), third_party=None, checkout=None,
        cro_observations=[], rich_results=None, product_feeds=None, accessibility=None,
        ad_traffic=None, sessions_override=100_000, cr_override_pct=2.0, aov_override=60.0,
    )
    inp = next(f for f in absolute.findings if f.finding_id == "perf.inp_mobile")
    assert (inp.uplift_low, inp.uplift_high) == (low, high)


def test_gap_speed_findings_cite_the_elasticity_not_only_the_market():
    store = _snapshot("store.com", 4200)
    competitors = [_snapshot(f"c{i}.com", 2100) for i in range(3)]
    gaps, *_ = price_gap_to_market(build_comparisons(store, competitors), _funnel())
    lcp_gap = next(g for g in gaps if g.finding_id == "gap.lcp_mobile")
    assert lcp_gap.citation == "DELOITTE_MS_MILLIONS"
    assert lcp_gap.citations == ["DELOITTE_MS_MILLIONS", "MARKET_MEDIAN_BENCHMARK"]


def test_missing_express_pay_vs_market_is_diagnostic_not_priced():
    from app.full_audit.schemas import CheckoutFlow, PlatformArchitecture

    def snap(domain, methods):
        return CompetitorSnapshot(
            domain=domain, measure_status="ok", measured_at=datetime.now(UTC),
            platform=PlatformArchitecture(detected_platform="Shopify"),
            checkout=CheckoutFlow(probe_status="ok", express_checkout_methods=methods),
        )

    store = snap("store.com", [])
    competitors = [snap(f"c{i}.com", ["Shop Pay"]) for i in range(3)]
    gaps, med_lo, med_hi, *_ = price_gap_to_market(build_comparisons(store, competitors), _funnel())

    express = next(g for g in gaps if g.finding_id == "gap.checkout_express")
    assert express.kind == "diagnostic" and express.confidence == "low"
    assert express.gap_to_median_eur_low is None
    assert med_lo is None and med_hi is None  # nothing else priced in this fixture

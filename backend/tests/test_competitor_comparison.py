from datetime import UTC, datetime

from app.competitor_benchmark.comparison import build_comparisons, score_layers
from app.competitor_benchmark.schemas import CompetitorSnapshot
from app.full_audit.schemas import (
    CheckoutFlow,
    LighthouseScores,
    MobileCWV,
    Performance,
    PlatformArchitecture,
    ThirdPartyScripts,
)


def _snapshot(domain, *, lcp_ms=None, platform="Shopify", checkout_probed=False, address_fields=None, express_methods=None, measure_status="ok"):
    checkout = None
    if checkout_probed:
        checkout = CheckoutFlow(
            probe_status="ok",
            fields_in_address_form=address_fields,
            express_checkout_methods=express_methods or [],
            guest_checkout_available=True,
        )
    return CompetitorSnapshot(
        domain=domain, measure_status=measure_status, measured_at=datetime.now(UTC),
        platform=PlatformArchitecture(detected_platform=platform) if platform else None,
        performance=Performance(mobile=MobileCWV(lcp_ms=lcp_ms), lighthouse=LighthouseScores(performance=80)) if lcp_ms else None,
        third_party=ThirdPartyScripts(total_third_party_domains=10),
        checkout=checkout,
    )


def _lcp(comparisons, key="speed.lcp_mobile_ms"):
    return next(c for c in comparisons if c.key == key)


def test_median_is_none_below_three_measured_domains():
    store = _snapshot("store.com", lcp_ms=4000)
    competitors = [_snapshot("c1.com", lcp_ms=2000), _snapshot("c2.com", lcp_ms=2200)]
    comparisons = build_comparisons(store, competitors)
    lcp = _lcp(comparisons)
    assert lcp.measured_domains == 2
    assert lcp.sufficiency == "insufficient"
    assert lcp.median is None
    assert lcp.store_rank is None


def test_median_present_at_three_measured_domains_with_thin_sufficiency():
    store = _snapshot("store.com", lcp_ms=4000)
    competitors = [_snapshot("c1.com", lcp_ms=2000), _snapshot("c2.com", lcp_ms=2200), _snapshot("c3.com", lcp_ms=2400)]
    comparisons = build_comparisons(store, competitors)
    lcp = _lcp(comparisons)
    assert lcp.measured_domains == 3
    assert lcp.sufficiency == "thin"
    assert lcp.median == 2200


def test_shopify_only_metric_excludes_non_shopify_from_eligible():
    store = _snapshot("store.com", lcp_ms=3000, checkout_probed=True, address_fields=10, express_methods=["applepay"])
    competitors = [
        _snapshot("c1.com", platform="Shopify", checkout_probed=True, address_fields=8, express_methods=["applepay"]),
        _snapshot("c2.com", platform="Shopify", checkout_probed=True, address_fields=9, express_methods=[]),
        _snapshot("c3.com", platform="WooCommerce", checkout_probed=False),
        _snapshot("c4.com", platform="WooCommerce", checkout_probed=False),
    ]
    comparisons = build_comparisons(store, competitors)
    fields = _lcp(comparisons, key="checkout.address_fields")
    assert fields.total_domains == 4
    assert fields.eligible_domains == 2  # only the two Shopify competitors
    assert fields.measured_domains == 2
    assert "Shopify-concurrent" in fields.coverage_label_nl
    assert "2 van 4" in fields.coverage_label_nl or "geen Shopify" in fields.coverage_label_nl


def test_unmeasured_shopify_peer_counted_as_eligible_not_measured():
    store = _snapshot("store.com", checkout_probed=True, address_fields=10, express_methods=[])
    competitors = [
        _snapshot("c1.com", platform="Shopify", checkout_probed=True, address_fields=8, express_methods=[]),
        _snapshot("c2.com", platform="Shopify", checkout_probed=True, address_fields=9, express_methods=[]),
        _snapshot("c3.com", platform="Shopify", checkout_probed=False, measure_status="partial"),  # eligible, not measured
    ]
    comparisons = build_comparisons(store, competitors)
    fields = _lcp(comparisons, key="checkout.address_fields")
    assert fields.eligible_domains == 3
    assert fields.measured_domains == 2
    assert "niet meetbaar" in fields.coverage_label_nl


def test_no_imputation_missing_values_stay_none():
    store = _snapshot("store.com", lcp_ms=None)  # performance not measured for the store
    competitors = [_snapshot("c1.com", lcp_ms=2000), _snapshot("c2.com", lcp_ms=2200), _snapshot("c3.com", lcp_ms=2400)]
    comparisons = build_comparisons(store, competitors)
    lcp = _lcp(comparisons)
    assert lcp.store_measured is False
    assert lcp.store_value is None
    assert lcp.gap_to_median_abs is None  # must not fabricate a gap for an unmeasured store


def test_boolean_metric_uses_adoption_rate_not_median():
    store = _snapshot("store.com", checkout_probed=True, address_fields=10, express_methods=[])
    competitors = [
        _snapshot("c1.com", checkout_probed=True, address_fields=8, express_methods=["applepay"]),
        _snapshot("c2.com", checkout_probed=True, address_fields=8, express_methods=["applepay"]),
        _snapshot("c3.com", checkout_probed=True, address_fields=8, express_methods=[]),
    ]
    comparisons = build_comparisons(store, competitors)
    guest = _lcp(comparisons, key="checkout.guest_available")
    assert guest.unit == "pct"
    # all three competitors have guest_checkout_available=True in the helper -> 100%
    assert guest.median == 100.0


def test_score_layers_returns_none_for_insufficient_layers_not_zero():
    store = _snapshot("store.com", lcp_ms=4000)
    competitors = [_snapshot("c1.com", lcp_ms=2000)]  # only 1 — insufficient everywhere
    comparisons = build_comparisons(store, competitors)
    layer_scores, overall = score_layers(comparisons, store)
    for ls in layer_scores:
        assert ls.relative_score is None
    assert overall is None

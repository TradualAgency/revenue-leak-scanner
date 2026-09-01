"""Tests for the revenue-leak model.

Pure/sync — `calculate_revenue_leak` has no I/O, so these run without a database.
"""

import pytest

from app.full_audit.analyzers.findings import FindingsRegistry, PricedFinding, price_findings
from app.full_audit.analyzers.funnel import build_funnel_model
from app.full_audit.analyzers.revenue_leak import calculate_revenue_leak
from app.full_audit.schemas import (
    CheckoutFlow,
    CroObservation,
    LighthouseScores,
    MobileCWV,
    Performance,
    RevenueLeakReport,
    ThirdPartyScripts,
)


def _layer(report, layer_num: int):
    return next(l for l in report.layers if l.layer == layer_num)


def _metric(layer, name_contains: str):
    return next(m for m in layer.metrics if name_contains in m.metric)


# The exact inputs from a real audit (barts.eu) whose report claimed a €77,700/mo
# leak — 2.9x the €26,400/mo the operator's own sessions/CR/AOV inputs imply, and
# whose €58,300 "pages" figure turned out to be exactly the 10% cap regardless of
# finding count. This fixture is the regression anchor for that report.
_BARTS_KWARGS = dict(
    annual_revenue_eur=7_000_000,
    aov_override=66.0,
    sessions_override=20_000,
    cr_override_pct=2.0,
    ad_spend_override=10_000.0,
)


def _barts_checkout() -> CheckoutFlow:
    return CheckoutFlow(
        probe_status="ok",
        tested_as_mobile=True,
        fields_in_address_form=21,
        guest_checkout_available=True,
        payment_methods_order=["Shop Pay"],
        express_checkout_methods=["Shop Pay"],
        redirects_before_payment=1,
        errors_encountered=[],
        total_checkout_time_seconds=3.2,
        observed_friction=[],
    )


def _barts_cro_observations() -> list[CroObservation]:
    return [
        CroObservation(page="Checkout", observation="Address form has 21 input fields.", severity="high"),
        CroObservation(
            page="Homepage",
            observation="Geen reviews, sterren of vertrouwenssignalen gedetecteerd op de homepage.",
            severity="high",
        ),
        CroObservation(
            page="Collection page",
            observation="Geen reviews, sterren of vertrouwenssignalen gedetecteerd op de collection page.",
            severity="high",
        ),
    ]


def _barts_performance(lcp_ms: float = 4200.0) -> Performance:
    return Performance(
        mobile=MobileCWV(lcp_ms=lcp_ms, inp_ms=350, cls=0.15),
        lighthouse=LighthouseScores(performance=45),
        desktop_lighthouse=LighthouseScores(performance=89),
        tbt_ms=350,
    )


def test_mobile_gap_not_measured_when_mobile_score_missing():
    """A missing mobile Lighthouse score must never render as 'mobile and desktop
    are comparable — good'. Before this fix, `gap = (desk - mob) if both else 0`
    silently produced gap=0 whenever mobile was unmeasured, and the `elif
    desk_score is not None` branch then reported that as a clean bill of health —
    a missing measurement presented as reassurance instead of as unmeasured.
    """
    performance = Performance(
        mobile=None,
        lighthouse=None,  # mobile PSI run never came back
        desktop_lcp_ms=1634.0,
        desktop_lighthouse=LighthouseScores(performance=89, accessibility=81, best_practices=96, seo=92),
    )

    report = calculate_revenue_leak(
        performance=performance,
        third_party=None,
        tracking=None,
        checkout=None,
        owned=None,
        cro_observations=[],
        rich_results=None,
        product_feeds=None,
        accessibility=None,
        ad_traffic=None,
        annual_revenue_eur=7_000_000,
        aov_override=66.0,
        sessions_override=20_000,
        cr_override_pct=2.0,
        ad_spend_override=10_000.0,
    )

    layer3 = _layer(report, 3)
    mobile_metric = _metric(layer3, "Verliest mobiel")

    assert mobile_metric.status == "not-measured"
    assert mobile_metric.signal is None
    # This metric is diagnostic (collinear with perf.lcp_mobile, priced in layer 1)
    # rather than independently priced, so "no data" and "no loss" both read as None.
    assert mobile_metric.monthly_loss_eur is None


def test_lcp_desktop_fallback_is_labelled_not_silent():
    """When mobile LCP is unavailable and the metric falls back to desktop LCP, the
    signal text must say so — desktop performance is not mobile UX and must not be
    presented as if it were measured on the channel most visitors use.
    """
    performance = Performance(
        mobile=None,
        lighthouse=None,
        desktop_lcp_ms=1634.0,
        desktop_lighthouse=LighthouseScores(performance=89),
    )

    report = calculate_revenue_leak(
        performance=performance,
        third_party=None,
        tracking=None,
        checkout=None,
        owned=None,
        cro_observations=[],
        rich_results=None,
        product_feeds=None,
        accessibility=None,
        ad_traffic=None,
        annual_revenue_eur=7_000_000,
        aov_override=66.0,
        sessions_override=20_000,
        cr_override_pct=2.0,
        ad_spend_override=10_000.0,
    )

    layer1 = _layer(report, 1)
    lcp_metric = _metric(layer1, "Hoe snel zien bezoekers")

    assert lcp_metric.signal is not None
    assert "desktop" in lcp_metric.signal.lower()


# --- funnel reconciliation -----------------------------------------------------------

def test_golden_barts_total_within_sane_share():
    """The regression test for the €77,700/mo headline: it was 2.9x the funnel's own
    €26,400/mo revenue. The rewritten model must price findings as a bounded share of
    the (reconciled) funnel revenue, never multiples of it."""
    report = calculate_revenue_leak(
        performance=_barts_performance(),
        third_party=ThirdPartyScripts(total_third_party_blocking_ms=1500, total_third_party_domains=22),
        tracking=None,
        checkout=_barts_checkout(),
        owned=None,
        cro_observations=_barts_cro_observations(),
        rich_results=None,
        product_feeds=None,
        accessibility=None,
        ad_traffic=None,
        **_BARTS_KWARGS,
    )

    assert report.funnel.monthly_revenue_eur == 26_400.0
    assert report.total_monthly_loss_eur_low is not None
    assert 0 < report.total_monthly_loss_eur_low <= report.total_monthly_loss_eur_high
    # The old model's headline was 294% of funnel revenue. The rewritten model must
    # stay well under 100% — the whole point of a "leak" is that it's less than the
    # store's total revenue.
    assert report.total_monthly_loss_eur_high < report.funnel.monthly_revenue_eur
    assert report.leak_share_of_revenue_high < 1.0


def test_operator_revenue_conflict_surfaced():
    """barts's operator inputs implied a 22x gap between the revenue field and the
    sessions/CR/AOV fields. That must produce a visible, correctly-sized conflict —
    and the loss math must be based on the funnel number, not the revenue field."""
    report = calculate_revenue_leak(
        performance=None, third_party=None, tracking=None, checkout=None, owned=None,
        cro_observations=[], rich_results=None, product_feeds=None, accessibility=None,
        ad_traffic=None, **_BARTS_KWARGS,
    )

    conflicts = [c for c in report.data_conflicts if c.kind == "revenue_vs_funnel"]
    assert len(conflicts) == 1
    assert conflicts[0].severity == "critical"
    assert conflicts[0].ratio == pytest.approx(22.1, rel=0.02)
    assert report.funnel.monthly_revenue_eur == 26_400.0  # funnel wins, not the revenue field


def test_ad_spend_conflict_surfaced():
    """€10k/mo ad spend on a €26.4k/mo funnel (38%) is a second, independent signal
    that the operator's inputs don't agree with each other."""
    report = calculate_revenue_leak(
        performance=None, third_party=None, tracking=None, checkout=None, owned=None,
        cro_observations=[], rich_results=None, product_feeds=None, accessibility=None,
        ad_traffic=None, **_BARTS_KWARGS,
    )
    assert any(c.kind == "ad_spend_vs_revenue" for c in report.data_conflicts)


def test_no_conflict_when_revenue_is_the_only_input():
    """If the operator supplies ONLY revenue (no sessions/CR/AOV), the funnel backs
    sessions out of that same revenue figure — they trivially agree, so comparing
    them proves nothing and must not raise a conflict."""
    report = calculate_revenue_leak(
        performance=None, third_party=None, tracking=None, checkout=None, owned=None,
        cro_observations=[], rich_results=None, product_feeds=None, accessibility=None,
        ad_traffic=None, annual_revenue_eur=120_000,
    )
    assert report.data_conflicts == []
    assert report.funnel.monthly_revenue_eur == pytest.approx(10_000.0)


# --- deduplication ---------------------------------------------------------------------

def test_address_form_counted_once_across_checkout_and_cro():
    """The address-form finding is raised independently by the checkout analyzer
    (>12 fields observed_friction) and by the generic CRO scan (same threshold on
    the same field). It must be priced once, not twice."""
    with_cro = calculate_revenue_leak(
        performance=None, third_party=None, tracking=None, checkout=_barts_checkout(), owned=None,
        cro_observations=_barts_cro_observations(), rich_results=None, product_feeds=None,
        accessibility=None, ad_traffic=None, **_BARTS_KWARGS,
    )
    without_cro = calculate_revenue_leak(
        performance=None, third_party=None, tracking=None, checkout=_barts_checkout(), owned=None,
        cro_observations=[], rich_results=None, product_feeds=None,
        accessibility=None, ad_traffic=None, **_BARTS_KWARGS,
    )

    layer3_with = _layer(with_cro, 3)
    layer3_without = _layer(without_cro, 3)
    checkout_with = _metric(layer3_with, "Lekt de betaalpagina")
    checkout_without = _metric(layer3_without, "Lekt de betaalpagina")

    # Adding the CRO observation for the SAME field-count issue must not change the
    # priced amount — it should merge into the existing finding, not add a second one.
    assert checkout_with.monthly_loss_eur_low == checkout_without.monthly_loss_eur_low
    assert checkout_with.monthly_loss_eur_high == checkout_without.monthly_loss_eur_high


def test_social_proof_collapses_across_pages_and_is_unpriced():
    """Three CRO observations (homepage/PDP/collection all missing reviews) are one
    root cause, not three — and Spiegel Research Center's 0-vs-5-reviews study does
    not license pricing 'our scraper found no widget in server HTML', so this
    finding must carry no euro figure and contribute nothing to the layer total."""
    report = calculate_revenue_leak(
        performance=None, third_party=None, tracking=None, checkout=None, owned=None,
        cro_observations=_barts_cro_observations()[1:],  # the two social-proof observations
        rich_results=None, product_feeds=None, accessibility=None, ad_traffic=None,
        **_BARTS_KWARGS,
    )
    layer3 = _layer(report, 3)
    social_proof = _metric(layer3, "sociaal bewijs")

    assert social_proof.verify_manually is True
    assert social_proof.confidence == "low"
    assert social_proof.monthly_loss_eur_low is None
    assert set(social_proof.pages_affected) == {"Homepage", "Collection page"}
    # Contributes nothing to the layer total.
    assert layer3.est_monthly_loss_eur_low == 0.0 or layer3.est_monthly_loss_eur_low is None


def test_low_confidence_findings_excluded_from_totals():
    """A finding registered with confidence='low' (or verify_manually=True) must
    never be priced, regardless of what exposure/uplift it's given — low confidence
    is supposed to mean 'we chose not to price this', full stop."""
    funnel, _ = build_funnel_model(annual_revenue_eur=120_000)
    registry = FindingsRegistry()
    registry.register(PricedFinding(
        finding_id="test.low_conf", owning_layer=3, stage="reach_checkout", kind="revenue",
        metric="m", what_we_measure="w", priority="high", status="warning", calculation_note="c",
        exposure_share=1.0, uplift_low=0.10, uplift_high=0.20, confidence="low",
    ), source="test")
    priced = price_findings(registry, funnel)
    assert priced == {}


# --- ceilings ----------------------------------------------------------------------

def test_ceiling_never_silently_binds_on_realistic_bad_store():
    """A realistically bad (but plausible) store should not trip the sanity-guard
    ceiling. If it does, the rule table's uplift ranges are miscalibrated — the
    ceiling is a smoke alarm, not a normal code path."""
    report = calculate_revenue_leak(
        performance=_barts_performance(),
        third_party=ThirdPartyScripts(total_third_party_blocking_ms=1500, total_third_party_domains=22),
        tracking=None,
        checkout=_barts_checkout(),
        owned=None,
        cro_observations=_barts_cro_observations(),
        rich_results=None, product_feeds=None, accessibility=None, ad_traffic=None,
        **_BARTS_KWARGS,
    )
    ceiling_warnings = [w for w in report.model_warnings if "ceiling" in w.kind]
    assert ceiling_warnings == []


def test_ceiling_binds_and_warns_on_absurd_input():
    """Piling up implausibly many findings in one funnel stage must scale down
    proportionally (not silently clamp to a fixed number) AND raise a warning —
    binding must be visible, never a silent substitute value."""
    funnel, _ = build_funnel_model(annual_revenue_eur=120_000)
    registry = FindingsRegistry()
    for i in range(5):
        registry.register(PricedFinding(
            finding_id=f"test.extreme_{i}", owning_layer=3, stage="reach_checkout", kind="revenue",
            metric="m", what_we_measure="w", priority="high", status="critical", calculation_note="c",
            exposure_share=1.0, uplift_low=0.20, uplift_high=0.30, confidence="medium",
        ), source="test")
    priced = price_findings(registry, funnel)

    total_high = sum(hi for _, hi in priced.values())
    assert total_high == pytest.approx(funnel.monthly_revenue_eur * 0.35, rel=0.01)
    assert any(w.kind == "stage_ceiling_bound" for w in registry.warnings)


def test_finding_count_is_monotonic_below_ceiling():
    """3 findings must price higher than 1 finding of the same size (below the
    ceiling) — the old `min(revenue * 10%, count * 350 * scale)` model made 3
    findings and 30 findings produce an identical number once the cap bound."""
    funnel, _ = build_funnel_model(annual_revenue_eur=1_200_000)  # big enough to stay under ceiling

    def _totals(n: int) -> float:
        registry = FindingsRegistry()
        for i in range(n):
            registry.register(PricedFinding(
                finding_id=f"test.finding_{i}", owning_layer=3, stage="add_to_cart", kind="revenue",
                metric="m", what_we_measure="w", priority="high", status="warning", calculation_note="c",
                exposure_share=0.1, uplift_low=0.01, uplift_high=0.02, confidence="medium",
            ), source="test")
        priced = price_findings(registry, funnel)
        assert registry.warnings == []  # must not be hitting the ceiling in this test
        return sum(hi for _, hi in priced.values())

    assert _totals(1) < _totals(3) < _totals(6)


# --- heuristic fallback --------------------------------------------------------------

def test_heuristic_fallback_when_no_inputs_available():
    """With no operator inputs and no SE Ranking data, the model must fall back to
    the default-store heuristic and label itself as such — never claim 'measured'."""
    report = calculate_revenue_leak(
        performance=None, third_party=None, tracking=None, checkout=None, owned=None,
        cro_observations=[], rich_results=None, product_feeds=None, accessibility=None,
        ad_traffic=None,
    )
    assert report.data_source == "heuristic"
    assert report.funnel.data_source == "heuristic"
    assert report.data_conflicts == []
    assert report.total_monthly_loss_eur_low == 0.0  # no detected findings, no invented loss


# --- layer 4: restatement, not new euros ---------------------------------------------

def test_layer4_adds_no_euros():
    """Layer 4 must never contribute additional euros beyond layers 1+3 — it's a
    restatement of the same total in CPA/ROAS/CR language, not new upside."""
    report = calculate_revenue_leak(
        performance=_barts_performance(),
        third_party=ThirdPartyScripts(total_third_party_blocking_ms=1500, total_third_party_domains=22),
        tracking=None, checkout=_barts_checkout(), owned=None,
        cro_observations=_barts_cro_observations(),
        rich_results=None, product_feeds=None, accessibility=None, ad_traffic=None,
        **_BARTS_KWARGS,
    )
    layer4 = _layer(report, 4)
    assert layer4.kind == "restatement"
    assert layer4.est_monthly_loss_eur_low is None
    assert layer4.est_monthly_loss_eur_high is None
    assert all(m.monthly_loss_eur is None for m in layer4.metrics)
    # The report total must equal layers 1+3 only.
    l1, l3 = _layer(report, 1), _layer(report, 3)
    expected_high = (l1.est_monthly_loss_eur_high or 0) + (l3.est_monthly_loss_eur_high or 0)
    assert report.total_monthly_loss_eur_high == pytest.approx(expected_high)


# --- scale invariance & ROI ------------------------------------------------------------

def test_scale_invariance():
    """The old model's `scale = monthly_revenue / 9_000` made every euro figure a
    fixed price scaled linearly by revenue — so a finding 'cost' the same fraction
    of revenue regardless of store size, but the ABSOLUTE euro number was the whole
    story. The rewritten model must be scale-invariant in a stronger sense: the
    same store (same relative session/CR/AOV shape, same findings) reports the same
    LEAK SHARE OF REVENUE whether it's a €9k/mo or €900k/mo store."""
    # `_r()` rounds every euro figure to the nearest €100 (each layer, then the
    # report total) — a deliberate display convention, not a precision guarantee.
    # That rounding is a much larger fraction of a small store's totals than a
    # large one's, so both stores here are kept well clear of that noise floor
    # (a 200-session/mo store's ~€264 revenue would round every loss to exactly
    # zero and trivially "pass"; that isn't the invariant this test is checking).
    small = calculate_revenue_leak(
        performance=_barts_performance(), third_party=None, tracking=None,
        checkout=_barts_checkout(), owned=None, cro_observations=[],
        rich_results=None, product_feeds=None, accessibility=None, ad_traffic=None,
        annual_revenue_eur=None, aov_override=66.0, sessions_override=20_000, cr_override_pct=2.0,
    )
    large = calculate_revenue_leak(
        performance=_barts_performance(), third_party=None, tracking=None,
        checkout=_barts_checkout(), owned=None, cro_observations=[],
        rich_results=None, product_feeds=None, accessibility=None, ad_traffic=None,
        annual_revenue_eur=None, aov_override=66.0, sessions_override=200_000, cr_override_pct=2.0,
    )
    assert small.funnel.monthly_revenue_eur > 0 and large.funnel.monthly_revenue_eur > 0
    assert small.leak_share_of_revenue_high == pytest.approx(large.leak_share_of_revenue_high, rel=0.02)


def test_roi_range_and_negative_year_one_not_clamped():
    """The worst-case payback must be at least as long as the best-case, and a
    negative low-bound year-one return must be reported as-is (not clamped to zero
    the way the old `max(0.0, ...)` did) — that's real information about how
    sensitive the ROI claim is to the low end of the estimate."""
    report = calculate_revenue_leak(
        performance=_barts_performance(),
        third_party=ThirdPartyScripts(total_third_party_blocking_ms=1500, total_third_party_domains=22),
        tracking=None, checkout=_barts_checkout(), owned=None,
        cro_observations=_barts_cro_observations(),
        rich_results=None, product_feeds=None, accessibility=None, ad_traffic=None,
        **_BARTS_KWARGS,
    )
    roi = report.roi
    assert roi is not None
    assert roi.payback_months_worst >= roi.payback_months_best
    assert roi.year_one_net_return_eur_low <= roi.year_one_net_return_eur_high


# --- backward compatibility ------------------------------------------------------------

def test_good_signals_stay_revenue_kind_not_diagnostic():
    """A metric that is currently fine (CLS score 0.00, LCP fast, checkout has no
    friction, reviews are present) must still be `kind='revenue'` and render as a
    priced zero ('✓ geen verlies' in the UI) — not `kind='diagnostic'`. A live run
    against barts.eu surfaced this: a perfect CLS score of 0.00 was rendering as
    'diagnose' instead of a green zero, because the 'nothing registered' fallback
    path was reusing the always-diagnostic helper (meant for layer 2's stack causes
    and the mobile/desktop-gap metric, which never get an independent price under
    any circumstance) for metrics that WOULD be priced the moment something is
    actually wrong.
    """
    performance = Performance(
        mobile=MobileCWV(lcp_ms=1200, inp_ms=50, cls=0.0),
        lighthouse=LighthouseScores(performance=95),
        desktop_lighthouse=LighthouseScores(performance=96),
        tbt_ms=50,
    )
    checkout = CheckoutFlow(
        probe_status="ok", tested_as_mobile=True, fields_in_address_form=8,
        guest_checkout_available=True, payment_methods_order=["iDEAL"],
        express_checkout_methods=["Apple Pay"], redirects_before_payment=1,
        errors_encountered=[], total_checkout_time_seconds=2.0, observed_friction=[],
    )

    report = calculate_revenue_leak(
        performance=performance, third_party=None, tracking=None, checkout=checkout,
        owned=None, cro_observations=[], rich_results=None, product_feeds=None,
        accessibility=None, ad_traffic=None,
        annual_revenue_eur=1_200_000, aov_override=95.0, sessions_override=20_000,
        cr_override_pct=2.0,
    )

    layer1 = _layer(report, 1)
    layer3 = _layer(report, 3)
    for name in ("Hoe snel zien bezoekers", "Reageert de pagina meteen"):
        m = _metric(layer1, name)
        assert m.kind == "revenue", f"{name} should stay kind=revenue when fine, got {m.kind}"
        assert m.status == "good"
        assert m.monthly_loss_eur == 0.0

    checkout_metric = _metric(layer3, "Lekt de betaalpagina")
    assert checkout_metric.kind == "revenue"
    assert checkout_metric.status == "good"
    assert checkout_metric.monthly_loss_eur == 0.0

    cls_metric = _metric(layer3, "Springt de pagina")
    assert cls_metric.kind == "revenue"
    assert cls_metric.status == "good"
    assert cls_metric.monthly_loss_eur == 0.0

    social_proof_metric = _metric(layer3, "sociaal bewijs")
    assert social_proof_metric.kind == "revenue"
    assert social_proof_metric.status == "good"
    assert social_proof_metric.monthly_loss_eur == 0.0

    # The always-diagnostic metrics must still be kind=diagnostic — this test isn't
    # asking for diagnostic metrics to disappear, only for the misclassified ones.
    mobile_gap_metric = _metric(layer3, "Verliest mobiel")
    assert mobile_gap_metric.kind == "diagnostic"


def test_v1_audit_row_still_parses():
    """A pre-rewrite jsonb `revenue_leak` payload (no funnel/data_conflicts/low-high
    fields at all) must still validate — the schema additions are all optional with
    defaults specifically so stored v1 reports don't break on read."""
    v1_payload = {
        "total_monthly_loss_eur": 48900,
        "layers": [{
            "layer": 1, "name": "De Deur", "core_question": "q", "leads_to": "x",
            "metrics": [{"metric": "m", "what_we_measure": "w", "priority": "high", "calculation_note": "c"}],
        }],
    }
    report = RevenueLeakReport.model_validate(v1_payload)
    assert report.model_version is None
    assert report.funnel is None
    assert report.total_monthly_loss_eur == 48900

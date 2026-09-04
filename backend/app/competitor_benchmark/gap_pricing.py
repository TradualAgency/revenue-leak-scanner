"""Prices the gap between the store and its measured market, mirroring the exact
LCP -> euro formula in revenue_leak.py's `_register_performance_findings` but with
the market median substituted for the hardcoded 2,500ms constant — this is the
feature's headline claim, and its strength is that the "benchmark" is a first-party
measurement of the store's own competitors, not an extrapolation from a published
study.

Four rules keep this honest (see module-level checks below): never price below the
sufficiency threshold, never floor the median at 2,500ms (a slow market must show as
a slow market, not get silently rounded up to the universal benchmark), always emit
a gap-to-best alongside gap-to-median, and always reuse the funnel from the source
audit rather than rebuilding it.
"""

from __future__ import annotations

from app.competitor_benchmark.schemas import GapFinding, MetricComparison
from app.full_audit.analyzers.findings import FindingsRegistry, PricedFinding, price_findings
from app.full_audit.schemas import FunnelModel

_MIN_ADDRESS_FIELD_GAP = 4
_EXPRESS_ADOPTION_THRESHOLD = 0.60
_MIN_ELIGIBLE_FOR_ADOPTION_CLAIM = 3


def _priceable(comparison: MetricComparison | None) -> bool:
    return bool(comparison and comparison.store_measured and comparison.sufficiency != "insufficient")


def _register_lcp_gap(registry: FindingsRegistry, comparisons: dict[str, MetricComparison], funnel: FunnelModel, reference: str) -> None:
    lcp = comparisons.get("speed.lcp_mobile_ms")
    if not _priceable(lcp):
        return
    reference_value = getattr(lcp, reference)
    if reference_value is None or lcp.store_value <= reference_value:
        return
    s_over = (lcp.store_value - reference_value) / 1_000
    exposure = (1 - funnel.paid_share) * funnel.mobile_share
    registry.register(PricedFinding(
        finding_id="gap.lcp_mobile", owning_layer=1, stage="session", kind="revenue",
        metric="Hoe snel zien bezoekers je producten t.o.v. je markt?",
        what_we_measure="Het verschil tussen jouw laadtijd en wat je concurrenten al halen",
        priority="high", status="warning",
        calculation_note=(
            f"€{funnel.monthly_revenue_eur:,.0f} omzet x {exposure * 100:.0f}% organisch/mobiel x "
            f"{min(0.10, s_over * 0.02) * 100:.1f}–{min(0.25, s_over * 0.05) * 100:.1f}% conversie-impact"
        ),
        signal=f"Jouw site is {s_over:.1f}s trager dan je markt",
        exposure_share=exposure, uplift_low=min(0.10, s_over * 0.02), uplift_high=min(0.25, s_over * 0.05),
        confidence="medium", citation="MARKET_MEDIAN_BENCHMARK",
    ), source="competitor_benchmark")


def _register_inp_gap(registry: FindingsRegistry, comparisons: dict[str, MetricComparison], funnel: FunnelModel, reference: str) -> None:
    tbt = comparisons.get("speed.tbt_ms")
    if not _priceable(tbt):
        return
    reference_value = getattr(tbt, reference)
    if reference_value is None or tbt.store_value <= reference_value:
        return
    ms_over = (tbt.store_value - reference_value) / 100
    exposure = (1 - funnel.paid_share) * funnel.mobile_share
    registry.register(PricedFinding(
        finding_id="gap.inp_mobile", owning_layer=1, stage="product_view", kind="revenue",
        metric="Reageert je site trager op een klik dan je markt?",
        what_we_measure="Het verschil in reactietijd t.o.v. wat concurrenten halen",
        priority="medium", status="warning",
        calculation_note=(
            f"€{funnel.monthly_revenue_eur:,.0f} omzet x {exposure * 100:.0f}% x "
            f"{min(0.03, ms_over * 0.01) * 100:.1f}–{min(0.06, ms_over * 0.03) * 100:.1f}%"
        ),
        signal="Je site reageert trager op klikken dan je markt",
        exposure_share=exposure, uplift_low=min(0.03, ms_over * 0.01), uplift_high=min(0.06, ms_over * 0.03),
        confidence="medium", citation="MARKET_MEDIAN_BENCHMARK",
    ), source="competitor_benchmark")


def _register_checkout_gaps(registry: FindingsRegistry, comparisons: dict[str, MetricComparison]) -> None:
    express = comparisons.get("checkout.express_methods_count")
    if express and express.store_measured and express.store_value == 0 and express.eligible_domains >= _MIN_ELIGIBLE_FOR_ADOPTION_CLAIM:
        measured_vals = [v.value for v in express.competitor_values if v.available]
        if measured_vals:
            adoption = sum(1 for v in measured_vals if v > 0) / len(measured_vals)
            if adoption >= _EXPRESS_ADOPTION_THRESHOLD:
                registry.register(PricedFinding(
                    finding_id="gap.checkout_express", owning_layer=3, stage="reach_checkout", kind="revenue",
                    metric="Mist je een snelle betaalknop die je markt al wel heeft?",
                    what_we_measure="Express-betaalopties (Apple Pay/Google Pay/Shop Pay) verlagen frictie in checkout",
                    priority="medium", status="warning",
                    calculation_note=f"{adoption * 100:.0f}% van je gemeten Shopify-concurrenten heeft een express-betaalknop, jij niet",
                    signal="Geen Apple Pay/Google Pay/Shop Pay-knop gevonden, terwijl je markt dit wel aanbiedt",
                    exposure_share=1.0, uplift_low=0.02, uplift_high=0.05,
                    confidence="medium", citation="BAYMARD_CHECKOUT_ABANDONMENT",
                ), source="competitor_benchmark")

    # Reuses the exact uplift formula _register_checkout_and_cro_findings applies to
    # "checkout.address_fields" (n_over = fields - 10, slope 0.005/0.010, caps
    # 0.08/0.15) so the gap model can't disagree with the absolute-leak model about
    # how much a given field count costs — only the reference point differs (market
    # median instead of the fixed Baymard baseline of 10).
    fields = comparisons.get("checkout.address_fields")
    if fields and fields.store_measured and fields.median is not None and fields.sufficiency != "insufficient":
        if fields.store_value > fields.median + _MIN_ADDRESS_FIELD_GAP:
            n_over = fields.store_value - 10
            registry.register(PricedFinding(
                finding_id="gap.checkout_address_fields", owning_layer=3, stage="reach_checkout", kind="revenue",
                metric="Heb je meer velden dan je markt?",
                what_we_measure="Extra velden in het adresformulier t.o.v. wat concurrenten vragen",
                priority="medium", status="warning",
                calculation_note=f"{fields.store_value:.0f} velden vs. mediaan {fields.median:.0f} in je markt",
                signal=f"Jouw adresformulier heeft {fields.store_value:.0f} velden, je markt gebruikt gemiddeld {fields.median:.0f}",
                exposure_share=1.0, uplift_low=min(0.08, n_over * 0.005), uplift_high=min(0.15, n_over * 0.010),
                confidence="medium", citation="BAYMARD_CHECKOUT_ABANDONMENT",
            ), source="competitor_benchmark")


def _price_reference(comparisons: dict[str, MetricComparison], funnel: FunnelModel, reference: str) -> dict[str, tuple[float, float]]:
    registry = FindingsRegistry()
    _register_lcp_gap(registry, comparisons, funnel, reference)
    _register_inp_gap(registry, comparisons, funnel, reference)
    if reference == "median":
        _register_checkout_gaps(registry, comparisons)
    return price_findings(registry, funnel)


def _diagnostic_gaps(comparisons: dict[str, MetricComparison]) -> list[GapFinding]:
    gaps: list[GapFinding] = []

    attribution = comparisons.get("tracking.est_attribution_loss_pct")
    if _priceable(attribution) and attribution.median is not None and attribution.store_value > attribution.median:
        gaps.append(GapFinding(
            finding_id="gap.tracking_attribution", layer=4, label_nl="Attributieverlies t.o.v. markt",
            store_value=attribution.store_value, median_value=attribution.median,
            kind="diagnostic", confidence="low",
            note_nl="Diagnostisch — geen apart bedrag, telt niet mee in de omzetberekening.",
        ))

    rating = comparisons.get("future.aggregate_rating")
    if rating and rating.store_measured and rating.store_value == 0 and rating.median is not None and rating.median > 30:
        gaps.append(GapFinding(
            finding_id="gap.schema_aggregate_rating", layer=5, label_nl="Reviewsterren t.o.v. markt",
            store_value=0, median_value=rating.median,
            kind="diagnostic", confidence="low", citation="SPIEGEL_REVIEWS",
            note_nl="Diagnostisch — handmatig verifiëren, geen bedrag (zie Spiegel Research Center methodologie).",
        ))

    return gaps


def price_gap_to_market(
    comparisons: list[MetricComparison], funnel: FunnelModel,
) -> tuple[list[GapFinding], float | None, float | None, float | None, float | None]:
    """Returns (gaps, gap_to_median_eur_low, gap_to_median_eur_high,
    gap_to_best_eur_low, gap_to_best_eur_high). Each reference (median/best) is
    priced through its own fresh FindingsRegistry — stacking both in one registry
    would apply the stage/global ceilings across two overlapping claims about the
    same findings."""
    by_key = {c.key: c for c in comparisons}

    median_priced = _price_reference(by_key, funnel, "median")
    best_priced = _price_reference(by_key, funnel, "best")

    gaps: list[GapFinding] = []
    lcp = by_key.get("speed.lcp_mobile_ms")
    if "gap.lcp_mobile" in median_priced or "gap.lcp_mobile" in best_priced:
        median_lo, median_hi = median_priced.get("gap.lcp_mobile", (None, None))
        best_lo, best_hi = best_priced.get("gap.lcp_mobile", (None, None))
        gaps.append(GapFinding(
            finding_id="gap.lcp_mobile", layer=1, label_nl="Laadtijd mobiel t.o.v. markt",
            store_value=lcp.store_value if lcp else None, median_value=lcp.median if lcp else None, best_value=lcp.best if lcp else None,
            gap_to_median_eur_low=median_lo, gap_to_median_eur_high=median_hi,
            gap_to_best_eur_low=best_lo, gap_to_best_eur_high=best_hi,
            market_is_also_below_benchmark=bool(lcp and lcp.median is not None and lcp.median > 2500),
            kind="revenue", confidence="medium", citation="MARKET_MEDIAN_BENCHMARK",
        ))

    tbt = by_key.get("speed.tbt_ms")
    if "gap.inp_mobile" in median_priced or "gap.inp_mobile" in best_priced:
        median_lo, median_hi = median_priced.get("gap.inp_mobile", (None, None))
        best_lo, best_hi = best_priced.get("gap.inp_mobile", (None, None))
        gaps.append(GapFinding(
            finding_id="gap.inp_mobile", layer=1, label_nl="Reactietijd t.o.v. markt",
            store_value=tbt.store_value if tbt else None, median_value=tbt.median if tbt else None, best_value=tbt.best if tbt else None,
            gap_to_median_eur_low=median_lo, gap_to_median_eur_high=median_hi,
            gap_to_best_eur_low=best_lo, gap_to_best_eur_high=best_hi,
            kind="revenue", confidence="medium", citation="MARKET_MEDIAN_BENCHMARK",
        ))

    express = by_key.get("checkout.express_methods_count")
    if "gap.checkout_express" in median_priced:
        lo, hi = median_priced["gap.checkout_express"]
        gaps.append(GapFinding(
            finding_id="gap.checkout_express", layer=3, label_nl="Express-checkout t.o.v. markt",
            store_value=express.store_value if express else None, median_value=express.median if express else None,
            gap_to_median_eur_low=lo, gap_to_median_eur_high=hi,
            kind="revenue", confidence="medium", citation="BAYMARD_CHECKOUT_ABANDONMENT",
        ))

    fields = by_key.get("checkout.address_fields")
    if "gap.checkout_address_fields" in median_priced:
        lo, hi = median_priced["gap.checkout_address_fields"]
        gaps.append(GapFinding(
            finding_id="gap.checkout_address_fields", layer=3, label_nl="Adresformulier t.o.v. markt",
            store_value=fields.store_value if fields else None, median_value=fields.median if fields else None,
            gap_to_median_eur_low=lo, gap_to_median_eur_high=hi,
            kind="revenue", confidence="medium", citation="BAYMARD_CHECKOUT_ABANDONMENT",
        ))

    gaps.extend(_diagnostic_gaps(by_key))

    revenue_gaps = [g for g in gaps if g.kind == "revenue"]
    total_median_low = sum(g.gap_to_median_eur_low or 0 for g in revenue_gaps) or None
    total_median_high = sum(g.gap_to_median_eur_high or 0 for g in revenue_gaps) or None
    total_best_low = sum(g.gap_to_best_eur_low or 0 for g in revenue_gaps if g.gap_to_best_eur_low is not None) or None
    total_best_high = sum(g.gap_to_best_eur_high or 0 for g in revenue_gaps if g.gap_to_best_eur_high is not None) or None

    return gaps, total_median_low, total_median_high, total_best_low, total_best_high

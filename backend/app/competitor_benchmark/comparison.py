"""Builds per-metric store-vs-competitor comparisons and per-layer scores, enforcing
the honesty rules a market comparison needs to be defensible in a sales conversation:
no median below 3 measurements, no imputed values, and a coverage sentence that says
exactly how many competitors a figure is actually based on.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime

from app.competitor_benchmark.metrics import LAYER_NAMES_NL, LAYER_WEIGHTS, METRICS, ComparableMetric
from app.competitor_benchmark.schemas import (
    CompetitorMetricValue,
    CompetitorSnapshot,
    LayerScore,
    MetricComparison,
)
from app.full_audit.schemas import FullAuditData

# (good, poor, higher_is_better) — used only for the *absolute* 0-100 score; the
# *relative* score (the primary frame for this feature) comes from store_percentile
# instead. Both are shown, deliberately: relative-only would hide a market that's
# uniformly below the norm; absolute-only would hide that the store still leads (or
# trails) its actual peers.
_ABSOLUTE_THRESHOLDS: dict[str, tuple[float, float, bool]] = {
    "speed.lcp_mobile_ms": (2500, 6000, False),
    "speed.lcp_moneypage_ms": (2500, 6000, False),
    "speed.tbt_ms": (200, 1000, False),
    "speed.cls": (0.1, 0.4, False),
    "speed.lighthouse_performance": (90, 30, True),
    "speed.page_weight_kb": (1500, 6000, False),
    "stack.third_party_domains": (8, 30, False),
    "stack.third_party_blocking_ms": (200, 1500, False),
    "checkout.address_fields": (10, 25, False),
    "checkout.express_methods_count": (2, 0, True),
    "tracking.est_attribution_loss_pct": (10, 50, False),
    "future.a11y_score": (90, 40, True),
}


def store_snapshot_from_audit(audit: FullAuditData, store_domain: str) -> CompetitorSnapshot:
    """The store's own full-audit results, wrapped in the same schema competitor
    measurements use — this is what lets `extract` callables in metrics.py run
    identically over the store and every competitor."""
    return CompetitorSnapshot(
        domain=store_domain,
        measure_status="ok",
        measured_at=datetime.now(UTC),
        platform=audit.platform_architecture,
        performance=audit.performance,
        third_party=audit.third_party_scripts,
        checkout=audit.checkout_flow,
        tracking=audit.tracking_data_quality,
        server_side_tracking=audit.server_side_tracking,
        dns_email=audit.dns_email,
        domain_health=audit.domain_health,
        rich_results=audit.rich_results,
        product_feeds=audit.product_feeds,
        seo=audit.seo_health,
        accessibility=audit.accessibility,
        cost=audit.cost_analysis,
    )


def _eligible(metric: ComparableMetric, snapshot: CompetitorSnapshot) -> bool:
    if metric.applicability == "shopify_only":
        from app.competitor_benchmark.metrics import is_shopify
        return is_shopify(snapshot)
    return True


def _unmeasured_reason(snapshot: CompetitorSnapshot) -> str:
    return {
        "unreachable": "domein niet bereikbaar",
        "timeout": "meting duurde te lang",
        "partial": "meting mislukt voor dit onderdeel",
    }.get(snapshot.measure_status, "niet gemeten")


def _coverage_label(metric: ComparableMetric, eligible: int, measured: int, total: int) -> str:
    if metric.applicability == "shopify_only":
        non_eligible = total - eligible
        base = f"mediaan over {eligible} Shopify-concurrent{'en' if eligible != 1 else ''}"
        if non_eligible > 0:
            base += f" ({non_eligible} van {total} draai{'t' if non_eligible == 1 else 'en'} geen Shopify)"
        if measured < eligible:
            base += f" — {eligible - measured} niet meetbaar"
        return base
    if measured < total:
        return f"mediaan over {measured} van de {total} concurrenten — {total - measured} niet meetbaar"
    if total == 0:
        return "geen concurrenten gemeten"
    return f"mediaan over alle {total} concurrenten"


def _sufficiency(measured_domains: int) -> str:
    if measured_domains < 3:
        return "insufficient"
    if measured_domains < 5:
        return "thin"
    return "sufficient"


def _build_one(metric: ComparableMetric, store_snapshot: CompetitorSnapshot, competitor_snapshots: list[CompetitorSnapshot]) -> MetricComparison:
    store_value = metric.extract(store_snapshot)
    total_domains = len(competitor_snapshots)

    values: list[CompetitorMetricValue] = []
    eligible_count = 0
    measured_vals: list[float] = []
    unavailable_reasons: dict[str, str] = {}

    for snap in competitor_snapshots:
        if not _eligible(metric, snap):
            values.append(CompetitorMetricValue(domain=snap.domain, value=None, available=False, unavailable_reason="niet van toepassing (geen Shopify)"))
            continue
        eligible_count += 1
        val = metric.extract(snap)
        source = metric.extract_source(snap) if metric.extract_source else None
        if val is None:
            reason = _unmeasured_reason(snap)
            unavailable_reasons[snap.domain] = reason
            values.append(CompetitorMetricValue(domain=snap.domain, value=None, available=False, unavailable_reason=reason, source=source))
            continue
        measured_vals.append(val)
        values.append(CompetitorMetricValue(domain=snap.domain, value=val, available=True, source=source))

    measured_domains = len(measured_vals)
    sufficiency = _sufficiency(measured_domains)

    median: float | None = None
    best: float | None = None
    best_domain: str | None = None
    p25: float | None = None

    if measured_domains >= 3:
        if metric.aggregation == "adoption_rate":
            median = (sum(measured_vals) / len(measured_vals)) * 100
        else:
            median = statistics.median(measured_vals)
            best = min(measured_vals) if metric.direction == "lower_is_better" else max(measured_vals)
            for v in values:
                if v.available and v.value == best:
                    best_domain = v.domain
                    break
            if len(measured_vals) >= 4:
                try:
                    p25 = statistics.quantiles(measured_vals, n=4)[0]
                except statistics.StatisticsError:
                    p25 = None

    store_measured = store_value is not None
    gap_abs: float | None = None
    gap_pct: float | None = None
    if store_measured and median is not None and metric.aggregation != "adoption_rate":
        gap_abs = (store_value - median) if metric.direction == "lower_is_better" else (median - store_value)
        gap_pct = (gap_abs / median * 100) if median else None

    store_rank: int | None = None
    domains_ranked: int | None = None
    store_percentile: float | None = None
    if store_measured and measured_domains >= 3:
        pool = measured_vals + [store_value]
        ordered = sorted(pool) if metric.direction == "lower_is_better" else sorted(pool, reverse=True)
        store_rank = ordered.index(store_value) + 1
        domains_ranked = len(pool)
        if domains_ranked > 1:
            better_count = domains_ranked - store_rank
            store_percentile = (better_count / (domains_ranked - 1)) * 100

    return MetricComparison(
        key=metric.key, layer=metric.layer, label_nl=metric.label_nl, unit=metric.unit, direction=metric.direction,
        store_value=store_value, store_measured=store_measured,
        competitor_values=values, median=median, best=best, best_domain=best_domain, p25=p25,
        store_rank=store_rank, domains_ranked=domains_ranked, store_percentile=store_percentile,
        gap_to_median_abs=gap_abs, gap_to_median_pct=gap_pct,
        measured_domains=measured_domains, eligible_domains=eligible_count, total_domains=total_domains,
        coverage_label_nl=_coverage_label(metric, eligible_count, measured_domains, total_domains),
        sufficiency=sufficiency, unavailable_reasons=unavailable_reasons,
    )


def build_comparisons(store_snapshot: CompetitorSnapshot, competitor_snapshots: list[CompetitorSnapshot]) -> list[MetricComparison]:
    return [_build_one(metric, store_snapshot, competitor_snapshots) for metric in METRICS]


def _absolute_score(metric: ComparableMetric, value: float | None) -> float | None:
    if value is None:
        return None
    if metric.aggregation == "adoption_rate":
        return 100.0 if value >= 0.5 else 0.0
    thresholds = _ABSOLUTE_THRESHOLDS.get(metric.key)
    if thresholds is None:
        return None
    good, poor, higher_is_better = thresholds
    if higher_is_better:
        if value >= good:
            return 100.0
        if value <= poor:
            return 0.0
        return (value - poor) / (good - poor) * 100
    if value <= good:
        return 100.0
    if value >= poor:
        return 0.0
    return (poor - value) / (poor - good) * 100


def score_layers(comparisons: list[MetricComparison], store_snapshot: CompetitorSnapshot) -> tuple[list[LayerScore], float | None]:
    metrics_by_key = {m.key: m for m in METRICS}
    by_layer: dict[int, list[MetricComparison]] = {}
    for c in comparisons:
        by_layer.setdefault(c.layer, []).append(c)

    layer_scores: list[LayerScore] = []
    for layer in sorted(LAYER_NAMES_NL):
        layer_comparisons = by_layer.get(layer, [])
        metrics_used = sum(1 for c in layer_comparisons if c.store_measured)
        metrics_unavailable = sum(1 for c in layer_comparisons if not c.store_measured)

        rel_weighted_sum = 0.0
        rel_weight_total = 0.0
        abs_weighted_sum = 0.0
        abs_weight_total = 0.0
        for c in layer_comparisons:
            metric = metrics_by_key[c.key]
            if c.store_percentile is not None and c.sufficiency != "insufficient":
                rel_weighted_sum += c.store_percentile * metric.weight
                rel_weight_total += metric.weight
            abs_score = _absolute_score(metric, c.store_value)
            if abs_score is not None:
                abs_weighted_sum += abs_score * metric.weight
                abs_weight_total += metric.weight

        relative_score = (rel_weighted_sum / rel_weight_total) if rel_weight_total > 0 else None
        absolute_score = (abs_weighted_sum / abs_weight_total) if abs_weight_total > 0 else None

        if relative_score is not None and absolute_score is not None:
            summary = (
                f"Je scoort {relative_score:.0f}/100 t.o.v. je markt "
                f"(absoluut {absolute_score:.0f}/100)."
            )
            if absolute_score < 50 and relative_score > 60:
                summary += " Je hele markt zit onder de norm — dat is precies waar je voorsprong ligt als je dit oplost."
        elif relative_score is not None:
            summary = f"Je scoort {relative_score:.0f}/100 t.o.v. je markt."
        else:
            summary = "Onvoldoende gemeten concurrenten om deze laag te scoren."

        layer_scores.append(LayerScore(
            layer=layer, name_nl=LAYER_NAMES_NL[layer],
            relative_score=relative_score, absolute_score=absolute_score,
            metrics_used=metrics_used, metrics_unavailable=metrics_unavailable,
            rank_in_set=None,  # requires per-competitor layer scoring — not computed in v1
            summary_nl=summary,
        ))

    overall_weighted = 0.0
    overall_weight_total = 0.0
    for ls in layer_scores:
        if ls.relative_score is not None:
            w = LAYER_WEIGHTS[ls.layer]
            overall_weighted += ls.relative_score * w
            overall_weight_total += w
    overall_relative_score = (overall_weighted / overall_weight_total) if overall_weight_total > 0 else None

    return layer_scores, overall_relative_score

"""Declarative metric registry — applicability and aggregation are declared per
metric rather than guessed at render time. That's the structural guard against
silently averaging a Shopify-only metric (checkout) over non-Shopify competitors, or
presenting a two-domain "median" as if it were a market figure: `comparison.py`
reads these declarations to decide who counts as `eligible` vs `measured` for each
metric, and refuses to compute a median below the sufficiency threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from app.competitor_benchmark.schemas import CompetitorSnapshot
from app.full_audit.analyzers.performance import worst_mobile_lcp

Unit = Literal["ms", "s", "count", "pct", "score", "eur", "bool"]
Direction = Literal["lower_is_better", "higher_is_better"]
Applicability = Literal["universal", "shopify_only", "platform_dependent"]
Aggregation = Literal["median", "adoption_rate"]


@dataclass(frozen=True)
class ComparableMetric:
    key: str
    layer: int
    label_nl: str
    unit: Unit
    direction: Direction
    applicability: Applicability
    aggregation: Aggregation
    extract: Callable[[CompetitorSnapshot], float | None]
    extract_source: Callable[[CompetitorSnapshot], str | None] | None = None
    weight: float = 1.0
    headline: bool = False


def is_shopify(snapshot: CompetitorSnapshot) -> bool:
    platform = snapshot.platform.detected_platform if snapshot.platform else None
    return bool(platform and "shopify" in platform.lower())


def _bool_to_float(value: bool | None) -> float | None:
    return None if value is None else (1.0 if value else 0.0)


# --- layer 1: snelheid -------------------------------------------------------------

def _lcp_mobile_ms(s: CompetitorSnapshot) -> float | None:
    val, _source = worst_mobile_lcp(s.performance)
    return val


def _lcp_mobile_source(s: CompetitorSnapshot) -> str | None:
    _val, source = worst_mobile_lcp(s.performance)
    return source


def _lcp_moneypage_ms(s: CompetitorSnapshot) -> float | None:
    return s.performance.money_page_lcp_ms if s.performance else None


def _tbt_ms(s: CompetitorSnapshot) -> float | None:
    return s.performance.tbt_ms if s.performance else None


def _cls(s: CompetitorSnapshot) -> float | None:
    return s.performance.mobile.cls if (s.performance and s.performance.mobile) else None


def _lighthouse_performance(s: CompetitorSnapshot) -> float | None:
    if s.performance and s.performance.lighthouse and s.performance.lighthouse.performance is not None:
        return float(s.performance.lighthouse.performance)
    return None


def _page_weight_kb(s: CompetitorSnapshot) -> float | None:
    return s.performance.total_page_weight_kb if s.performance else None


# --- layer 2: stack ------------------------------------------------------------

def _third_party_domains(s: CompetitorSnapshot) -> float | None:
    if s.third_party and s.third_party.total_third_party_domains is not None:
        return float(s.third_party.total_third_party_domains)
    return None


def _third_party_blocking_ms(s: CompetitorSnapshot) -> float | None:
    return s.third_party.total_third_party_blocking_ms if s.third_party else None


def _monthly_app_cost_eur(s: CompetitorSnapshot) -> float | None:
    return s.cost.current_monthly_app_cost_eur if s.cost else None


# --- layer 3: checkout (shopify_only) -------------------------------------------

def _address_fields(s: CompetitorSnapshot) -> float | None:
    if s.checkout and s.checkout.fields_in_address_form is not None:
        return float(s.checkout.fields_in_address_form)
    return None


def _express_methods_count(s: CompetitorSnapshot) -> float | None:
    if s.checkout is None or s.checkout.probe_status != "ok":
        return None
    return float(len(s.checkout.express_checkout_methods))


def _guest_available(s: CompetitorSnapshot) -> float | None:
    if s.checkout is None or s.checkout.probe_status != "ok":
        return None
    return _bool_to_float(s.checkout.guest_checkout_available)


# --- layer 4: tracking/dns (universal) ------------------------------------------

def _attribution_loss_pct(s: CompetitorSnapshot) -> float | None:
    return s.tracking.est_attribution_loss_percent if s.tracking else None


def _server_side_detected(s: CompetitorSnapshot) -> float | None:
    return _bool_to_float(s.server_side_tracking.sgtm_detected if s.server_side_tracking else None)


def _dmarc_enforced(s: CompetitorSnapshot) -> float | None:
    if s.dns_email is None or s.dns_email.dmarc_policy is None:
        return None
    return _bool_to_float(s.dns_email.dmarc_policy in ("quarantine", "reject"))


def _spf_valid(s: CompetitorSnapshot) -> float | None:
    if s.dns_email is None or s.dns_email.spf_status is None:
        return None
    return _bool_to_float(s.dns_email.spf_status == "valid")


# --- layer 5: toekomst (universal) ----------------------------------------------

def _aggregate_rating(s: CompetitorSnapshot) -> float | None:
    return _bool_to_float(s.rich_results.has_aggregate_rating if s.rich_results else None)


def _product_schema(s: CompetitorSnapshot) -> float | None:
    return _bool_to_float(s.rich_results.has_product_schema if s.rich_results else None)


def _breadcrumb(s: CompetitorSnapshot) -> float | None:
    return _bool_to_float(s.rich_results.has_breadcrumb if s.rich_results else None)


def _feed_reachable(s: CompetitorSnapshot) -> float | None:
    return _bool_to_float(s.product_feeds.feed_endpoint_reachable if s.product_feeds else None)


def _a11y_score(s: CompetitorSnapshot) -> float | None:
    if s.accessibility and s.accessibility.lighthouse_score is not None:
        return float(s.accessibility.lighthouse_score)
    return None


METRICS: list[ComparableMetric] = [
    # Layer 1 — Snelheid
    ComparableMetric("speed.lcp_mobile_ms", 1, "Laadtijd mobiel (LCP)", "ms", "lower_is_better",
                      "universal", "median", _lcp_mobile_ms, extract_source=_lcp_mobile_source, weight=2.0, headline=True),
    ComparableMetric("speed.lcp_moneypage_ms", 1, "Laadtijd omzetpagina", "ms", "lower_is_better",
                      "universal", "median", _lcp_moneypage_ms),
    ComparableMetric("speed.tbt_ms", 1, "Reactietijd op klikken (TBT)", "ms", "lower_is_better",
                      "universal", "median", _tbt_ms),
    ComparableMetric("speed.cls", 1, "Layout-verspringing (CLS)", "score", "lower_is_better",
                      "universal", "median", _cls),
    ComparableMetric("speed.lighthouse_performance", 1, "Lighthouse performance-score", "score", "higher_is_better",
                      "universal", "median", _lighthouse_performance),
    ComparableMetric("speed.page_weight_kb", 1, "Paginagewicht", "count", "lower_is_better",
                      "universal", "median", _page_weight_kb),

    # Layer 2 — Stack
    ComparableMetric("stack.third_party_domains", 2, "Externe domeinen", "count", "lower_is_better",
                      "universal", "median", _third_party_domains, weight=2.0, headline=True),
    ComparableMetric("stack.third_party_blocking_ms", 2, "Blokkerende tijd door externe scripts", "ms", "lower_is_better",
                      "universal", "median", _third_party_blocking_ms),
    ComparableMetric("stack.est_monthly_app_cost_eur", 2, "Geschatte maandelijkse tool-kosten", "eur", "lower_is_better",
                      "universal", "median", _monthly_app_cost_eur),

    # Layer 3 — Checkout (Shopify-only: the probe only works against Shopify's cart/checkout endpoints)
    ComparableMetric("checkout.address_fields", 3, "Velden in adresformulier", "count", "lower_is_better",
                      "shopify_only", "median", _address_fields),
    ComparableMetric("checkout.express_methods_count", 3, "Aantal express-betaalmethodes", "count", "higher_is_better",
                      "shopify_only", "median", _express_methods_count, weight=2.0, headline=True),
    ComparableMetric("checkout.guest_available", 3, "Gastbestelling beschikbaar", "pct", "higher_is_better",
                      "shopify_only", "adoption_rate", _guest_available),

    # Layer 4 — Tracking & DNS
    ComparableMetric("tracking.est_attribution_loss_pct", 4, "Geschat attributieverlies", "pct", "lower_is_better",
                      "universal", "median", _attribution_loss_pct, weight=2.0, headline=True),
    ComparableMetric("tracking.server_side_detected", 4, "Server-side tracking aanwezig", "pct", "higher_is_better",
                      "universal", "adoption_rate", _server_side_detected),
    ComparableMetric("tracking.dmarc_enforced", 4, "DMARC afgedwongen", "pct", "higher_is_better",
                      "universal", "adoption_rate", _dmarc_enforced),
    ComparableMetric("tracking.spf_valid", 4, "SPF correct ingesteld", "pct", "higher_is_better",
                      "universal", "adoption_rate", _spf_valid),

    # Layer 5 — Toekomst
    ComparableMetric("future.aggregate_rating", 5, "Reviewsterren in schema", "pct", "higher_is_better",
                      "universal", "adoption_rate", _aggregate_rating, weight=2.0, headline=True),
    ComparableMetric("future.product_schema", 5, "Product-schema aanwezig", "pct", "higher_is_better",
                      "universal", "adoption_rate", _product_schema),
    ComparableMetric("future.breadcrumb", 5, "Breadcrumb-schema aanwezig", "pct", "higher_is_better",
                      "universal", "adoption_rate", _breadcrumb),
    ComparableMetric("future.feed_reachable", 5, "Productfeed bereikbaar", "pct", "higher_is_better",
                      "universal", "adoption_rate", _feed_reachable),
    ComparableMetric("future.a11y_score", 5, "Toegankelijkheidsscore", "score", "higher_is_better",
                      "universal", "median", _a11y_score),
]

METRICS_BY_KEY: dict[str, ComparableMetric] = {m.key: m for m in METRICS}

LAYER_NAMES_NL: dict[int, str] = {
    1: "Snelheid",
    2: "Stack & bloat",
    3: "Checkout-frictie",
    4: "Tracking & DNS",
    5: "Toekomstgereedheid",
}

LAYER_WEIGHTS: dict[int, float] = {1: 0.30, 2: 0.20, 3: 0.20, 4: 0.15, 5: 0.15}

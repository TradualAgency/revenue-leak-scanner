"""Funnel model: the single source of truth for "how much revenue moves through
this store", replacing the old `monthly_revenue = annual_revenue_eur / 12` +
`scale = monthly_revenue / 9_000` mechanism in revenue_leak.py.

The core problem this fixes: the old model trusted whichever revenue figure the
operator typed in, even when the operator's own sessions/CR/AOV inputs implied a
wildly different number (one real audit had €583k/mo from the revenue field vs
€26k/mo implied by 20,000 sessions x 2% CR x €66 AOV — a 22x gap that was never
surfaced, and every euro figure in the report was based on the larger, contradicted
number).

This module computes `monthly_revenue_eur = sessions * cr * aov` from whichever
inputs are real, and treats that as authoritative for all downstream loss
calculations. The operator-supplied revenue figure becomes context: if it disagrees
with the funnel by more than 35%, a `DataConflict` is raised instead of silently
picking a side.
"""

from __future__ import annotations

from app.full_audit.analyzers.benchmarks import (
    AD_SPEND_SHARE_OF_REVENUE,
    CITATIONS,
    DEFAULT_ANNUAL_REVENUE_EUR,
    FUNNEL_CHAIN_CR,
    FUNNEL_STAGE_RATES,
    MOBILE_SHARE_DEFAULT,
    PAID_SHARE_DEFAULT,
    aov_for_monthly_revenue,
)
from app.full_audit.schemas import (
    DataConflict,
    FunnelModel,
    FunnelStageModel,
    SeRankingTraffic,
)

_REVENUE_CONFLICT_RATIO = 1.35  # >35% apart triggers a conflict
_AD_SPEND_SHARE_WARN = 0.30  # ad spend above 30% of funnel revenue is a second signal


def _calibrate_stage_rates(cr: float) -> tuple[list[float], float]:
    """Scale the four benchmark stage exit-rates so their product equals the real
    (or benchmarked) conversion rate, preserving the relative shape of the funnel.
    `k = (cr / FUNNEL_CHAIN_CR) ** 0.25` applied uniformly to all four rates makes
    `product(k * rate_i) == cr` exactly, as long as no rate needs clamping.
    """
    base_rates = [
        FUNNEL_STAGE_RATES["session_to_product_view"],
        FUNNEL_STAGE_RATES["product_view_to_cart"],
        FUNNEL_STAGE_RATES["cart_to_checkout"],
        FUNNEL_STAGE_RATES["checkout_to_purchase"],
    ]
    if cr <= 0 or FUNNEL_CHAIN_CR <= 0:
        return base_rates, 1.0
    k = (cr / FUNNEL_CHAIN_CR) ** 0.25
    calibrated = [min(0.95, max(0.001, k * r)) for r in base_rates]
    return calibrated, k


def _funnel_stages(sessions: float, cr: float, purchases: float) -> list[FunnelStageModel]:
    rates, k = _calibrate_stage_rates(cr)
    clamped = abs(k - 1.0) > 0.001 and any(
        (k * r) != c for r, c in zip(
            [
                FUNNEL_STAGE_RATES["session_to_product_view"],
                FUNNEL_STAGE_RATES["product_view_to_cart"],
                FUNNEL_STAGE_RATES["cart_to_checkout"],
                FUNNEL_STAGE_RATES["checkout_to_purchase"],
            ],
            rates,
        )
    )
    citation_key = "LITTLEDATA_SHOPIFY_BENCHMARKS"
    exit_rate_source = "calibrated" if k != 1.0 else "benchmark"

    product_view = sessions * rates[0]
    add_to_cart = product_view * rates[1]
    reach_checkout = add_to_cart * rates[2]
    # `purchases` is the measured/derived anchor (sessions * cr); the calibrated chain
    # should land on it exactly unless clamping intervened at an extreme CR.
    stages = [
        FunnelStageModel(
            stage="session", entering=sessions, exit_rate=rates[0],
            exit_rate_source=exit_rate_source, citation=citation_key,
        ),
        FunnelStageModel(
            stage="product_view", entering=product_view, exit_rate=rates[1],
            exit_rate_source=exit_rate_source, citation=citation_key,
        ),
        FunnelStageModel(
            stage="add_to_cart", entering=add_to_cart, exit_rate=rates[2],
            exit_rate_source=exit_rate_source, citation="BAYMARD_CART_ABANDONMENT",
        ),
        FunnelStageModel(
            stage="reach_checkout", entering=reach_checkout, exit_rate=rates[3],
            exit_rate_source=exit_rate_source, citation="BAYMARD_CHECKOUT_ABANDONMENT",
        ),
        FunnelStageModel(
            stage="purchase", entering=purchases, exit_rate=1.0,
            exit_rate_source="measured" if exit_rate_source == "measured" else "calibrated",
            citation=None,
        ),
    ]
    if clamped:
        for s in stages[:4]:
            s.exit_rate_source = "benchmark"
    return stages


def build_funnel_model(
    annual_revenue_eur: float | None,
    traffic: SeRankingTraffic | None = None,
    aov_override: float | None = None,
    sessions_override: int | None = None,
    cr_override_pct: float | None = None,
    ad_spend_override: float | None = None,
) -> tuple[FunnelModel, list[DataConflict]]:
    conflicts: list[DataConflict] = []
    operator_monthly_revenue = (annual_revenue_eur / 12) if annual_revenue_eur else None

    # --- AOV: operator > revenue-bucket guess ---
    if aov_override:
        aov = aov_override
        aov_source = "operator"
    else:
        aov = aov_for_monthly_revenue(operator_monthly_revenue or DEFAULT_ANNUAL_REVENUE_EUR / 12)
        aov_source = "benchmark"

    # --- sessions: operator > SE Ranking > derived later from revenue/aov/cr ---
    sessions: float | None = None
    if sessions_override:
        sessions = float(sessions_override)
        sessions_source = "operator"
    elif traffic is not None:
        sessions = float(traffic.monthly_organic_sessions + traffic.monthly_paid_sessions)
        sessions_source = "seranking"
    else:
        sessions_source = "derived"

    # --- CR: operator > derived from real revenue+sessions+aov > chain benchmark ---
    if cr_override_pct is not None:
        cr = cr_override_pct / 100
        cr_source = "operator"
    elif sessions is not None and sessions > 0 and operator_monthly_revenue is not None:
        # Two real measurements (sessions, revenue) plus a real or guessed AOV imply a
        # CR — this is arithmetic on real inputs, not a fabricated constant.
        cr = max(0.001, min(0.30, operator_monthly_revenue / (sessions * aov)))
        cr_source = "derived"
    else:
        cr = FUNNEL_CHAIN_CR
        cr_source = "benchmark"

    # --- sessions, if still unknown: back out from revenue/aov/cr (old heuristic path) ---
    if sessions is None:
        base_revenue = operator_monthly_revenue or (DEFAULT_ANNUAL_REVENUE_EUR / 12)
        sessions = base_revenue / (aov * cr) if cr > 0 else 0.0

    monthly_revenue_eur = sessions * cr * aov
    monthly_purchases = sessions * cr

    # --- reconciliation: only meaningful when sessions/CR were NOT themselves derived
    # from the operator's revenue figure — otherwise funnel_revenue trivially equals
    # operator_revenue by construction and comparing them proves nothing. ---
    funnel_independently_specified = sessions_source in ("operator", "seranking") or cr_source == "operator"
    if (
        funnel_independently_specified
        and operator_monthly_revenue is not None
        and monthly_revenue_eur > 0
    ):
        ratio = operator_monthly_revenue / monthly_revenue_eur
        if ratio > _REVENUE_CONFLICT_RATIO or ratio < 1 / _REVENUE_CONFLICT_RATIO:
            conflicts.append(DataConflict(
                kind="revenue_vs_funnel",
                operator_value_eur=operator_monthly_revenue,
                model_value_eur=monthly_revenue_eur,
                ratio=ratio,
                severity="critical" if (ratio > 3 or ratio < 1 / 3) else "warning",
                message_nl=(
                    f"De opgegeven omzet (€{operator_monthly_revenue:,.0f}/mnd) is "
                    f"{ratio:.1f}x de omzet die volgt uit je eigen cijfers "
                    f"({sessions:,.0f} bezoekers x {cr * 100:.2f}% x €{aov:.0f} = "
                    f"€{monthly_revenue_eur:,.0f}/mnd). Alle bedragen in dit rapport "
                    "zijn berekend op basis van het tweede getal — daar zit de "
                    "meetbare onderbouwing. Controleer welke van de vier cijfers "
                    "niet klopt."
                ),
            ))

    # --- ad spend: operator > share of FUNNEL revenue (not operator revenue — an
    # inflated revenue figure must not inflate the ad-spend benchmark too) ---
    if ad_spend_override:
        ad_spend = ad_spend_override
        ad_spend_source = "operator"
    else:
        ad_spend = monthly_revenue_eur * AD_SPEND_SHARE_OF_REVENUE
        ad_spend_source = "benchmark"

    if ad_spend_source == "operator" and monthly_revenue_eur > 0:
        spend_share = ad_spend / monthly_revenue_eur
        if spend_share > _AD_SPEND_SHARE_WARN:
            conflicts.append(DataConflict(
                kind="ad_spend_vs_revenue",
                operator_value_eur=ad_spend,
                model_value_eur=monthly_revenue_eur * _AD_SPEND_SHARE_WARN,
                ratio=spend_share,
                severity="critical" if spend_share > 0.5 else "warning",
                message_nl=(
                    f"Het opgegeven advertentiebudget (€{ad_spend:,.0f}/mnd) is "
                    f"{spend_share * 100:.0f}% van de omzet die uit je eigen cijfers "
                    f"volgt (€{monthly_revenue_eur:,.0f}/mnd) — dat is ongebruikelijk "
                    "hoog en duidt op een tegenstrijdigheid in de opgegeven cijfers."
                ),
            ))

    # --- paid share, for splitting exposure between paid and organic/direct traffic ---
    if traffic is not None and (traffic.monthly_organic_sessions + traffic.monthly_paid_sessions) > 0:
        paid_share = traffic.monthly_paid_sessions / (
            traffic.monthly_organic_sessions + traffic.monthly_paid_sessions
        )
    else:
        paid_share = PAID_SHARE_DEFAULT

    has_real_signal = any([aov_override, sessions_override, cr_override_pct, ad_spend_override, traffic is not None])
    data_source = "measured" if has_real_signal else "heuristic"

    stages = _funnel_stages(sessions, cr, monthly_purchases)

    if data_source == "measured":
        methodology_note = (
            f"Omzet berekend uit funnel: {sessions:,.0f} sessies/mnd x {cr * 100:.2f}% "
            f"CVR x €{aov:.0f} AOV = €{monthly_revenue_eur:,.0f}/mnd. "
            f"(sessies: {sessions_source}, CVR: {cr_source}, AOV: {aov_source}, "
            f"ad spend: {ad_spend_source})."
        )
    else:
        methodology_note = (
            f"Geen operator-cijfers of meetbare traffic beschikbaar — heuristische "
            f"schatting op basis van een €{DEFAULT_ANNUAL_REVENUE_EUR:,.0f}/jr "
            f"default-winkel: €{monthly_revenue_eur:,.0f}/mnd omzet, "
            f"{sessions:,.0f} sessies/mnd, {cr * 100:.2f}% CVR."
        )

    funnel = FunnelModel(
        monthly_sessions=sessions,
        conversion_rate=cr,
        aov_eur=aov,
        monthly_revenue_eur=monthly_revenue_eur,
        monthly_purchases=monthly_purchases,
        monthly_ad_spend_eur=ad_spend,
        mobile_share=MOBILE_SHARE_DEFAULT,
        paid_share=paid_share,
        stages=stages,
        calibration_factor=_calibrate_stage_rates(cr)[1],
        sessions_source=sessions_source,
        cr_source=cr_source,
        aov_source=aov_source,
        ad_spend_source=ad_spend_source,
        operator_monthly_revenue_eur=operator_monthly_revenue,
        data_source=data_source,
        methodology_note=methodology_note,
    )
    return funnel, conflicts


def stage_population(funnel: FunnelModel, stage: str) -> float:
    """Number of sessions/users entering a given funnel stage — used by rule tables
    to express a finding's exposure as a headcount instead of a bare share."""
    for s in funnel.stages:
        if s.stage == stage:
            return s.entering
    return 0.0


__all__ = ["build_funnel_model", "stage_population", "CITATIONS"]

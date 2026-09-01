from __future__ import annotations

from app.full_audit.analyzers.funnel import build_funnel_model
from app.full_audit.analyzers.performance import lcp_source_caveat, worst_mobile_lcp
from app.full_audit.schemas import (
    AdTrafficImpact,
    Performance,
    SeRankingTraffic,
    ServerSideTracking,
    ThirdPartyScripts,
    TrackingDataQuality,
)

_BASELINE_BOUNCE_PCT = 45.0


def calculate_ad_traffic_impact(
    performance: Performance | None,
    third_party: ThirdPartyScripts | None,
    tracking: TrackingDataQuality | None,
    server_side: ServerSideTracking | None,
    annual_revenue_eur: float | None = None,
    traffic: SeRankingTraffic | None = None,
    aov_override: float | None = None,
    sessions_override: int | None = None,
    cr_override_pct: float | None = None,
    ad_spend_override: float | None = None,
) -> AdTrafficImpact | None:
    # Build the SAME funnel model revenue_leak.py builds from the same inputs, so
    # this analyzer's AOV/CR/sessions/paid-share can never drift from the rest of
    # the report the way the old BENCHMARK_CR=0.03-vs-0.02 split used to.
    funnel, _conflicts = build_funnel_model(
        annual_revenue_eur, traffic,
        aov_override=aov_override,
        sessions_override=sessions_override,
        cr_override_pct=cr_override_pct,
        ad_spend_override=ad_spend_override,
    )
    drivers: list[str] = []
    uplift = 0.0
    has_signals = False

    mobile = performance.mobile if performance else None

    # LCP: Google CrUX-correlatie — elke seconde boven 2.5s voegt ~12pp bounce toe (cap 60pp).
    # Uses the worst of the field measurement and the money-page lab run — the field
    # metric is homepage-only and can hide a much slower PDP/collection page.
    lcp_ms, lcp_source = worst_mobile_lcp(performance)
    if lcp_ms is not None:
        has_signals = True
        lcp_s = lcp_ms / 1000
        lcp_uplift = min(60.0, max(0.0, (lcp_s - 2.5) * 12))
        if lcp_uplift > 0:
            uplift += lcp_uplift
            drivers.append(
                f"LCP {lcp_s:.1f}s (grens 2.5s){lcp_source_caveat(performance, lcp_source)} "
                f"— +{lcp_uplift:.0f}pp bounce-uplift"
            )

    # INP: interactieresponsiviteit — traag = frustratie = afhaken
    if mobile and mobile.inp_ms is not None:
        has_signals = True
        if mobile.inp_ms > 500:
            inp_uplift = 10.0
            drivers.append(f"INP {mobile.inp_ms:.0f}ms (kritiek, grens 200ms) — +10pp bounce-uplift")
        elif mobile.inp_ms > 200:
            inp_uplift = 5.0
            drivers.append(f"INP {mobile.inp_ms:.0f}ms (traag, grens 200ms) — +5pp bounce-uplift")
        else:
            inp_uplift = 0.0
        uplift += inp_uplift

    # Third-party blocking: scripts die het laden blokkeren verhogen afhaken
    if third_party and third_party.total_third_party_blocking_ms is not None:
        has_signals = True
        blocking_ms = third_party.total_third_party_blocking_ms
        if blocking_ms > 2500:
            block_uplift = 10.0
            drivers.append(f"Third-party blocking {blocking_ms:.0f}ms — +10pp bounce-uplift")
        elif blocking_ms > 1000:
            block_uplift = 5.0
            drivers.append(f"Third-party blocking {blocking_ms:.0f}ms — +5pp bounce-uplift")
        else:
            block_uplift = 0.0
        uplift += block_uplift

    if not has_signals:
        return None

    bounce_pct = min(90.0, _BASELINE_BOUNCE_PCT + uplift)
    delta = max(0.0, bounce_pct - _BASELINE_BOUNCE_PCT)
    drop_off = round(delta / 100 * 1000) if delta > 0 else 0

    # Paid-session estimate: `funnel.paid_share` is measured (SE Ranking) when
    # available, else the shared PAID_SHARE_DEFAULT — the same split every other
    # paid-traffic-aware figure in the report uses, instead of a separate ad-hoc
    # "50-100% of all sessions" guess.
    ad_sessions_base = funnel.monthly_sessions * funnel.paid_share
    if funnel.sessions_source in ("operator", "seranking") and traffic is not None:
        ad_sessions_low = ad_sessions_high = ad_sessions_base
    else:
        ad_sessions_low, ad_sessions_high = ad_sessions_base * 0.5, ad_sessions_base * 1.5

    lost_low = round(ad_sessions_low * (delta / 100) * funnel.conversion_rate * funnel.aov_eur)
    lost_high = round(ad_sessions_high * (delta / 100) * funnel.conversion_rate * funnel.aov_eur)

    wasted_pct = tracking.est_attribution_loss_percent if tracking else None

    is_measured = funnel.data_source == "measured"
    if is_measured and traffic is not None:
        sessions_note = f"Gemeten via SE Ranking: {ad_sessions_low:,.0f} betaalde sessies/mnd."
    else:
        sessions_note = (
            f"Heuristisch afgeleid: {ad_sessions_low:,.0f}–{ad_sessions_high:,.0f} "
            f"ad-bezoeken/mnd (van €{funnel.monthly_revenue_eur:,.0f}/mnd omzet)."
        )

    return AdTrafficImpact(
        est_post_click_bounce_pct=round(bounce_pct, 1),
        bounce_baseline_pct=_BASELINE_BOUNCE_PCT,
        est_drop_off_per_1000_clicks=drop_off,
        est_monthly_lost_revenue_eur_low=float(lost_low) if delta > 0 else None,
        est_monthly_lost_revenue_eur_high=float(lost_high) if delta > 0 else None,
        est_wasted_ad_spend_pct=wasted_pct,
        bounce_drivers=drivers,
        methodology_note=(
            f"{'Gemeten' if is_measured else 'Heuristische'} schatting op basis van Google CrUX-correlaties (LCP/INP → bounce-rate). "
            f"{sessions_note} {funnel.conversion_rate * 100:.2f}% CVR, €{funnel.aov_eur:.0f} AOV. "
            "Gebruik als indicatie, niet als gemeten benchmark."
        ),
        data_source="measured" if is_measured else "heuristic",
    )

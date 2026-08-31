from __future__ import annotations

from app.full_audit.analyzers.benchmarks import (
    BENCHMARK_CR,
    DEFAULT_ANNUAL_REVENUE_EUR,
    aov_for_monthly_revenue,
)
from app.full_audit.schemas import (
    AdTrafficImpact,
    Performance,
    SeRankingTraffic,
    ServerSideTracking,
    ThirdPartyScripts,
    TrackingDataQuality,
)

_BASELINE_BOUNCE_PCT = 45.0


def _ad_benchmarks(
    annual_revenue_eur: float | None,
    traffic: SeRankingTraffic | None = None,
) -> dict:
    monthly = (annual_revenue_eur or DEFAULT_ANNUAL_REVENUE_EUR) / 12
    aov = aov_for_monthly_revenue(monthly)

    if traffic is not None:
        paid = float(traffic.monthly_paid_sessions)
        # When paid sessions are known, low == high (no range uncertainty).
        ad_sessions_low = paid
        ad_sessions_high = paid
        data_source = "measured"
    else:
        sessions = monthly / (aov * BENCHMARK_CR)
        ad_sessions_low = sessions * 0.50
        ad_sessions_high = sessions * 1.00
        data_source = "heuristic"

    return {
        "monthly_revenue": monthly,
        "aov": aov,
        "ad_sessions_low": ad_sessions_low,
        "ad_sessions_high": ad_sessions_high,
        "data_source": data_source,
    }


def calculate_ad_traffic_impact(
    performance: Performance | None,
    third_party: ThirdPartyScripts | None,
    tracking: TrackingDataQuality | None,
    server_side: ServerSideTracking | None,
    annual_revenue_eur: float | None = None,
    traffic: SeRankingTraffic | None = None,
) -> AdTrafficImpact | None:
    bench = _ad_benchmarks(annual_revenue_eur, traffic)
    drivers: list[str] = []
    uplift = 0.0
    has_signals = False

    mobile = performance.mobile if performance else None

    # LCP: Google CrUX-correlatie — elke seconde boven 2.5s voegt ~12pp bounce toe (cap 60pp)
    if mobile and mobile.lcp_ms is not None:
        has_signals = True
        lcp_s = mobile.lcp_ms / 1000
        lcp_uplift = min(60.0, max(0.0, (lcp_s - 2.5) * 12))
        if lcp_uplift > 0:
            uplift += lcp_uplift
            drivers.append(f"LCP {lcp_s:.1f}s (grens 2.5s) \u2014 +{lcp_uplift:.0f}pp bounce-uplift")

    # INP: interactieresponsiviteit — traag = frustratie = afhaken
    if mobile and mobile.inp_ms is not None:
        has_signals = True
        if mobile.inp_ms > 500:
            inp_uplift = 10.0
            drivers.append(f"INP {mobile.inp_ms:.0f}ms (kritiek, grens 200ms) \u2014 +10pp bounce-uplift")
        elif mobile.inp_ms > 200:
            inp_uplift = 5.0
            drivers.append(f"INP {mobile.inp_ms:.0f}ms (traag, grens 200ms) \u2014 +5pp bounce-uplift")
        else:
            inp_uplift = 0.0
        uplift += inp_uplift

    # Third-party blocking: scripts die het laden blokkeren verhogen afhaken
    if third_party and third_party.total_third_party_blocking_ms is not None:
        has_signals = True
        blocking_ms = third_party.total_third_party_blocking_ms
        if blocking_ms > 2500:
            block_uplift = 10.0
            drivers.append(f"Third-party blocking {blocking_ms:.0f}ms \u2014 +10pp bounce-uplift")
        elif blocking_ms > 1000:
            block_uplift = 5.0
            drivers.append(f"Third-party blocking {blocking_ms:.0f}ms \u2014 +5pp bounce-uplift")
        else:
            block_uplift = 0.0
        uplift += block_uplift

    if not has_signals:
        return None

    bounce_pct = min(90.0, _BASELINE_BOUNCE_PCT + uplift)
    delta = max(0.0, bounce_pct - _BASELINE_BOUNCE_PCT)
    drop_off = round(delta / 100 * 1000) if delta > 0 else 0

    lost_low = round(bench["ad_sessions_low"] * (delta / 100) * BENCHMARK_CR * bench["aov"])
    lost_high = round(bench["ad_sessions_high"] * (delta / 100) * BENCHMARK_CR * bench["aov"])

    wasted_pct = tracking.est_attribution_loss_percent if tracking else None

    is_measured = bench["data_source"] == "measured"
    if is_measured and bench["ad_sessions_low"] > 0:
        sessions_note = f"Gemeten via SE Ranking: {bench['ad_sessions_low']:,.0f} betaalde sessies/mnd."
    else:
        sessions_note = (
            f"Heuristisch afgeleid: {bench['ad_sessions_low']:,.0f}\u2013{bench['ad_sessions_high']:,.0f} "
            f"ad-bezoeken/mnd (van \u20ac{bench['monthly_revenue']:,.0f}/mnd omzet)."
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
            f"{'Gemeten' if is_measured else 'Heuristische'} schatting op basis van Google CrUX-correlaties (LCP/INP \u2192 bounce-rate). "
            f"{sessions_note} {BENCHMARK_CR * 100:.0f}% CVR, \u20ac{bench['aov']:.0f} AOV. "
            "Gebruik als indicatie, niet als gemeten benchmark."
        ),
        data_source="measured" if is_measured else "heuristic",
    )

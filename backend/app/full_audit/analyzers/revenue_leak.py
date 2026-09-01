"""Revenue-leak model.

Every euro figure in this module is `funnel.monthly_revenue_eur * exposure_share *
relative_uplift` (see analyzers/funnel.py and analyzers/findings.py) instead of the
old `count * arbitrary_eur_constant * (monthly_revenue / 9_000)`. Three structural
guarantees this rewrite adds that the old model did not have:

1. `funnel.monthly_revenue_eur` is reconciled against the operator-supplied revenue
   figure instead of trusting it blindly — see funnel.build_funnel_model(). A real
   audit had a 22x gap between the two that was silently invisible before.
2. Every finding is registered under a stable `finding_id` in a FindingsRegistry, so
   the same underlying issue detected by two analyzers (e.g. the checkout probe and
   the generic CRO scan both flagging ">12 address fields") is priced once, not
   twice.
3. Per-stage ceilings scale proportionally and raise a ModelWarning when they bind,
   instead of silently clamping to a constant that made "3 findings" and "30
   findings" produce an identical euro figure.

Layers 2 and 4 no longer contribute new revenue-loss euros. Layer 2's findings are
*causes* of the LCP/TBT loss already priced in layer 1 (third-party domain count,
unused JS, blocking scripts, TTFB are all upstream of "the page is slow" — pricing
them again would double-count layer 1's number under a different label); layer 2
instead reports tool-subscription cost savings. Layer 4's findings are three
restatements of the layer 1+3 total (theoretical CR, CPA, ROAS) — not new euros.
"""

from __future__ import annotations

from app.full_audit.analyzers.benchmarks import CITATIONS
from app.full_audit.analyzers.findings import FindingsRegistry, PricedFinding, cro_finding_id, price_findings
from app.full_audit.analyzers.funnel import build_funnel_model
from app.full_audit.schemas import (
    AccessibilityHealth,
    AdTrafficImpact,
    CeoTriggerKpi,
    CheckoutFlow,
    CostAnalysis,
    CroObservation,
    FunnelModel,
    MetricStatus,
    ModelWarning,
    OwnedChannels,
    Performance,
    ProductFeedHealth,
    RevenueLeakLayer,
    RevenueLeakMetric,
    RevenueLeakReport,
    RichResultsHealth,
    RoiCalculation,
    SeRankingTraffic,
    ThirdPartyScripts,
    TrackingDataQuality,
)

_STACK_REBUILD_COST = 35_000.0
_MODEL_VERSION = "2.0"


def _r(value: float) -> float:
    return float(round(value / 100) * 100)


def _pair(low: float | None, high: float | None) -> tuple[float | None, float | None, float | None]:
    """(low, high, midpoint) — midpoint feeds the legacy single-value fields so
    older consumers (sanity export, AI prompts, the `48900`-style test fixture)
    keep working through the migration without reading the new fields."""
    if low is None or high is None:
        return None, None, None
    return low, high, (low + high) / 2


def _layer_signals(metrics: list[RevenueLeakMetric]) -> tuple[list[str], list[str]]:
    good = [m.signal for m in metrics if m.status == "good" and m.signal]
    improve = [m.signal for m in metrics if m.status in ("warning", "critical") and m.signal]
    return good, improve


def _finalize_layer(
    layer: int,
    name: str,
    core_question: str,
    leads_to: str,
    metrics: list[RevenueLeakMetric],
    kind: str,
    unpriced_finding_count: int = 0,
) -> RevenueLeakLayer:
    priced_metrics = [m for m in metrics if m.monthly_loss_eur_low is not None]
    total_low = _r(sum(m.monthly_loss_eur_low or 0 for m in priced_metrics)) if priced_metrics else None
    total_high = _r(sum(m.monthly_loss_eur_high or 0 for m in priced_metrics)) if priced_metrics else None
    total_mid = _r((total_low + total_high) / 2) if (total_low is not None and total_high is not None) else 0.0

    good_signals, improvement_signals = _layer_signals(metrics)
    measured = sum(1 for m in metrics if m.status != "not-measured")
    good_count = sum(1 for m in metrics if m.status == "good")
    key_signals = [m.signal for m in metrics if m.signal and (m.monthly_loss_eur_high or 0) > 0]

    return RevenueLeakLayer(
        layer=layer,
        name=name,
        core_question=core_question,
        est_monthly_loss_eur=total_mid if kind in ("revenue", "cost") else None,
        est_annual_loss_eur=(total_mid * 12) if kind in ("revenue", "cost") else None,
        est_monthly_loss_eur_low=total_low,
        est_monthly_loss_eur_high=total_high,
        est_annual_loss_eur_low=(total_low * 12) if total_low is not None else None,
        est_annual_loss_eur_high=(total_high * 12) if total_high is not None else None,
        metric_count=len(metrics),
        leads_to=leads_to,
        key_signals=key_signals[:4],
        metrics=metrics,
        summary=f"{good_count} van {measured} gemeten metrics binnen benchmark" if measured else "Onvoldoende data",
        good_signals=good_signals,
        improvement_signals=improvement_signals,
        kind=kind,
        unpriced_finding_count=unpriced_finding_count,
    )


def _metric_from_finding(
    finding: PricedFinding,
    priced: dict[str, tuple[float, float]],
) -> RevenueLeakMetric:
    low, high = priced.get(finding.finding_id, (None, None))
    low, high, mid = _pair(low, high)
    return RevenueLeakMetric(
        metric=finding.metric,
        what_we_measure=finding.what_we_measure,
        priority=finding.priority,
        monthly_loss_eur=mid,
        annual_loss_eur=(mid * 12) if mid is not None else None,
        monthly_loss_eur_low=low,
        monthly_loss_eur_high=high,
        annual_loss_eur_low=(low * 12) if low is not None else None,
        annual_loss_eur_high=(high * 12) if high is not None else None,
        calculation_note=finding.calculation_note,
        signal=finding.signal,
        status=finding.status,
        finding_id=finding.finding_id,
        funnel_stage=finding.stage,
        exposure_share=finding.exposure_share,
        uplift_low=finding.uplift_low,
        uplift_high=finding.uplift_high,
        confidence=finding.confidence,
        kind=finding.kind,
        basis=finding.basis,
        citation=finding.citation,
        verify_manually=finding.verify_manually,
        pages_affected=finding.pages_affected,
    )


def _cost_metric(
    metric: str,
    what_we_measure: str,
    priority: str,
    calculation_note: str,
    signal: str | None,
    status: MetricStatus,
    monthly_value_eur: float | None,
) -> RevenueLeakMetric:
    return RevenueLeakMetric(
        metric=metric,
        what_we_measure=what_we_measure,
        priority=priority,  # type: ignore[arg-type]
        monthly_loss_eur=monthly_value_eur,
        annual_loss_eur=(monthly_value_eur * 12) if monthly_value_eur is not None else None,
        monthly_loss_eur_low=monthly_value_eur,
        monthly_loss_eur_high=monthly_value_eur,
        annual_loss_eur_low=(monthly_value_eur * 12) if monthly_value_eur is not None else None,
        annual_loss_eur_high=(monthly_value_eur * 12) if monthly_value_eur is not None else None,
        calculation_note=calculation_note,
        signal=signal,
        status=status,
        kind="cost",
        confidence="medium",
    )


def _diagnostic_metric(
    metric: str,
    what_we_measure: str,
    priority: str,
    calculation_note: str,
    signal: str | None,
    status: MetricStatus,
) -> RevenueLeakMetric:
    """For metrics that are NEVER independently priced, regardless of status — they
    are causes of a loss already priced elsewhere (layer 2's stack causes) or a
    restatement of one (the layer 3 mobile/desktop gap, the page-level rollup).
    Do not use this for a revenue-kind metric that simply has nothing wrong right
    now — use `_revenue_metric_no_finding` for that, or it renders as "diagnose"
    in the UI for a metric that would show "✓ geen verlies" the moment something
    IS wrong, which reads as if the metric was never revenue-relevant at all."""
    return RevenueLeakMetric(
        metric=metric,
        what_we_measure=what_we_measure,
        priority=priority,  # type: ignore[arg-type]
        monthly_loss_eur=None,
        annual_loss_eur=None,
        calculation_note=calculation_note,
        signal=signal,
        status=status,
        kind="diagnostic",
    )


def _revenue_metric_no_finding(
    metric: str,
    what_we_measure: str,
    priority: str,
    calculation_note: str,
    signal: str | None,
    status: MetricStatus,
) -> RevenueLeakMetric:
    """For a revenue-kind metric where no finding was registered — either because
    the underlying signal is fine (status='good', renders '✓ geen verlies') or
    because it wasn't measured at all (status='not-measured', renders 'strategisch').
    Keeping kind='revenue' here (never 'diagnostic') is what stops a metric that
    WOULD be priced if something were wrong from being mislabelled as if it were
    never eligible for pricing in the first place."""
    zero = status == "good"
    val = 0.0 if zero else None
    return RevenueLeakMetric(
        metric=metric,
        what_we_measure=what_we_measure,
        priority=priority,  # type: ignore[arg-type]
        monthly_loss_eur=val,
        annual_loss_eur=(val * 12) if val is not None else None,
        monthly_loss_eur_low=val,
        monthly_loss_eur_high=val,
        annual_loss_eur_low=(val * 12) if val is not None else None,
        annual_loss_eur_high=(val * 12) if val is not None else None,
        calculation_note=calculation_note,
        signal=signal,
        status=status,
        kind="revenue",
    )


# --- registration: performance & ad-traffic findings (layer 1 stages) --------------

def _register_performance_findings(
    registry: FindingsRegistry,
    performance: Performance | None,
    ad_traffic: AdTrafficImpact | None,
    funnel: FunnelModel,
) -> dict:
    """Registers perf.lcp_mobile, perf.inp_mobile, adtraffic.post_click_bounce.
    Returns the raw signal data layer 1's builder needs for copy/status that isn't
    itself part of the euro calculation (e.g. the exact LCP figure for the label)."""
    ctx: dict = {}
    organic_share = 1 - funnel.paid_share

    # — LCP —
    lcp_ms = None
    lcp_is_desktop_fallback = False
    if performance and performance.mobile:
        lcp_ms = performance.mobile.lcp_ms
    if lcp_ms is None and performance and performance.desktop_lcp_ms:
        lcp_ms = performance.desktop_lcp_ms
        lcp_is_desktop_fallback = True
    ctx["lcp_ms"] = lcp_ms
    ctx["lcp_is_desktop_fallback"] = lcp_is_desktop_fallback
    lcp_caveat = " (desktop-meting — mobiel niet gemeten, mobiel is meestal trager)" if lcp_is_desktop_fallback else ""

    if lcp_ms is not None and lcp_ms > 2_500:
        s_over = (lcp_ms - 2_500) / 1_000
        exposure = organic_share * funnel.mobile_share
        registry.register(PricedFinding(
            finding_id="perf.lcp_mobile", owning_layer=1, stage="session", kind="revenue",
            metric="Hoe snel zien bezoekers je producten?",
            what_we_measure="Hoe lang bezoekers wachten voor ze überhaupt iets te zien krijgen — elke seconde extra wachten kost klanten",
            priority="high",
            status="critical" if lcp_ms > 4_000 else "warning",
            calculation_note=(
                f"€{funnel.monthly_revenue_eur:,.0f} omzet x {exposure * 100:.0f}% "
                f"organisch/mobiel verkeer x {min(0.10, s_over * 0.02) * 100:.1f}–"
                f"{min(0.25, s_over * 0.05) * 100:.1f}% conversie-impact"
            ),
            signal=f"Bezoekers wachten {lcp_ms / 1000:.1f}s voor ze je producten zien{lcp_caveat} — te traag, ze haken af",
            exposure_share=exposure,
            uplift_low=min(0.10, s_over * 0.02),
            uplift_high=min(0.25, s_over * 0.05),
            confidence="medium",
            citation="DELOITTE_MS_MILLIONS",
        ), source="performance")
    else:
        signal = f"Producten zichtbaar in {lcp_ms / 1000:.1f}s{lcp_caveat} — bezoekers blijven hangen" if lcp_ms else None
        ctx["lcp_status"] = "good" if lcp_ms is not None else "not-measured"
        ctx["lcp_signal"] = signal

    # — INP (proxy via TBT) —
    tbt_ms = performance.tbt_ms if performance else None
    ctx["tbt_ms"] = tbt_ms
    if tbt_ms is not None and tbt_ms > 200:
        exposure = organic_share * funnel.mobile_share
        if tbt_ms > 500:
            uplift_low, uplift_high = 0.03, 0.06
        else:
            uplift_low, uplift_high = 0.01, 0.03
        registry.register(PricedFinding(
            finding_id="perf.inp_mobile", owning_layer=1, stage="product_view", kind="revenue",
            metric="Reageert de pagina meteen op klikken?",
            what_we_measure="Of klikken op knoppen en menu's direct werkt of dat bezoekers moeten wachten",
            priority="high",
            status="critical" if tbt_ms > 300 else "warning",
            calculation_note=(
                f"€{funnel.monthly_revenue_eur:,.0f} omzet x {exposure * 100:.0f}% "
                f"organisch/mobiel verkeer x {uplift_low * 100:.0f}–{uplift_high * 100:.0f}% conversie-impact"
            ),
            signal=f"Pagina reageert pas na {tbt_ms:.0f}ms op een klik — voelt traag en stuk",
            exposure_share=exposure,
            uplift_low=uplift_low,
            uplift_high=uplift_high,
            confidence="medium",
            citation="INTERNAL_ESTIMATE",
        ), source="performance")
    else:
        ctx["inp_signal"] = f"Pagina reageert direct in {tbt_ms:.0f}ms — voelt snel en soepel" if tbt_ms is not None else None
        ctx["inp_status"] = "good" if tbt_ms is not None else "not-measured"

    # — Post-click bounce (paid traffic) — ad_traffic.py already computed a real
    # low/high euro range from sessions x bounce-delta x CR x AOV; consume it
    # directly rather than re-deriving it from an exposure*uplift formula, but
    # still register it so it competes for the "session" stage ceiling alongside
    # perf.lcp_mobile instead of stacking on top of it unbounded.
    if ad_traffic and ad_traffic.est_post_click_bounce_pct is not None:
        bounce_delta = max(0.0, ad_traffic.est_post_click_bounce_pct - ad_traffic.bounce_baseline_pct)
        if bounce_delta > 0 and ad_traffic.est_monthly_lost_revenue_eur_low is not None:
            registry.register(PricedFinding(
                finding_id="adtraffic.post_click_bounce", owning_layer=1, stage="session", kind="revenue",
                metric="Hoeveel bezoekers vertrekken vóór ze iets zien?",
                what_we_measure="Het deel van je bezoekers dat direct wegklikt omdat de pagina te traag laadt",
                priority="high",
                status="critical" if ad_traffic.est_post_click_bounce_pct > 60 else "warning",
                calculation_note="Extra weglopers x betaalde sessies x conversiekans x gemiddelde bestelwaarde (ad_traffic model)",
                signal=f"{ad_traffic.est_post_click_bounce_pct:.0f}% vertrekt direct — {bounce_delta:.0f}% boven gezond, dat is verloren omzet",
                fixed_low_eur=ad_traffic.est_monthly_lost_revenue_eur_low,
                fixed_high_eur=ad_traffic.est_monthly_lost_revenue_eur_high,
                confidence="high" if ad_traffic.data_source == "measured" else "medium",
                citation="INTERNAL_ESTIMATE",
            ), source="ad_traffic")
            ctx["bounce_registered"] = True
        else:
            ctx["bounce_signal"] = f"{ad_traffic.est_post_click_bounce_pct:.0f}% vertrekt direct (gezond is ~{ad_traffic.bounce_baseline_pct:.0f}%)"
            ctx["bounce_status"] = "good"
    else:
        ctx["bounce_signal"] = None
        ctx["bounce_status"] = "not-measured"

    return ctx


def _layer1_deur(
    registry: FindingsRegistry,
    priced: dict[str, tuple[float, float]],
    ctx: dict,
    ad_traffic: AdTrafficImpact | None,
    funnel: FunnelModel,
) -> RevenueLeakLayer:
    metrics: list[RevenueLeakMetric] = []

    lcp_finding = registry.get("perf.lcp_mobile")
    if lcp_finding:
        metrics.append(_metric_from_finding(lcp_finding, priced))
    else:
        metrics.append(_revenue_metric_no_finding(
            metric="Hoe snel zien bezoekers je producten?",
            what_we_measure="Hoe lang bezoekers wachten voor ze überhaupt iets te zien krijgen — elke seconde extra wachten kost klanten",
            priority="high",
            calculation_note="Trage laadtijd → bezoekers haken af → omzet die je misloopt",
            signal=ctx.get("lcp_signal"),
            status=ctx.get("lcp_status", "not-measured"),
        ))

    inp_finding = registry.get("perf.inp_mobile")
    if inp_finding:
        metrics.append(_metric_from_finding(inp_finding, priced))
    else:
        metrics.append(_revenue_metric_no_finding(
            metric="Reageert de pagina meteen op klikken?",
            what_we_measure="Of klikken op knoppen en menu's direct werkt of dat bezoekers moeten wachten",
            priority="high",
            calculation_note="Trage reactie → bezoekers denken dat het kapot is → ze vertrekken",
            signal=ctx.get("inp_signal"),
            status=ctx.get("inp_status", "not-measured"),
        ))

    bounce_finding = registry.get("adtraffic.post_click_bounce")
    if bounce_finding:
        metrics.append(_metric_from_finding(bounce_finding, priced))
    else:
        metrics.append(_revenue_metric_no_finding(
            metric="Hoeveel bezoekers vertrekken vóór ze iets zien?",
            what_we_measure="Het deel van je bezoekers dat direct wegklikt omdat de pagina te traag laadt",
            priority="high",
            calculation_note="Extra weglopers × gemiddelde bestelwaarde × kans op aankoop = misgelopen omzet",
            signal=ctx.get("bounce_signal"),
            status=ctx.get("bounce_status", "not-measured"),
        ))

    # — Ad-spend-verdamping — a cost (money spent, not revenue lost), computed
    # directly from a real measured input (tracking's attribution-loss estimate)
    # rather than an arbitrary constant, so it does not need registry pricing.
    if ad_traffic and ad_traffic.est_wasted_ad_spend_pct is not None:
        ad_loss = _r(min(
            funnel.monthly_ad_spend_eur * 0.30,
            funnel.monthly_ad_spend_eur * ad_traffic.est_wasted_ad_spend_pct / 100,
        ))
        signal = f"{ad_traffic.est_wasted_ad_spend_pct:.0f}% van je advertentiebudget verbrandt — de klikker ziet je winkel nooit echt"
        ad_status: MetricStatus = "critical" if ad_traffic.est_wasted_ad_spend_pct > 30 else "warning"
    else:
        ad_loss = None
        signal = None
        ad_status = "not-measured"
    metrics.append(_cost_metric(
        metric="Hoeveel advertentiegeld verdampt vóór de pagina laadt?",
        what_we_measure="Het deel van je advertentiebudget waarvoor je betaalt maar geen klant terug krijgt — de klikker is weg vóór de pagina klaar is",
        priority="critical",
        calculation_note="Verdampt deel × maandelijks advertentiebudget = direct verbrand geld (kosten, geen omzetverlies)",
        signal=signal,
        status=ad_status,
        monthly_value_eur=ad_loss,
    ))

    return _finalize_layer(
        layer=1, name="De Deur",
        core_question="Hoeveel bezoekers verliezen we vóórdat ze iets kunnen doen?",
        leads_to="Stack Rebuild™ — Snelheid",
        metrics=metrics, kind="revenue",
    )


# --- registration: stack findings (layer 2 — diagnostic, no revenue euros) --------

def _layer2_motor(
    performance: Performance | None,
    third_party: ThirdPartyScripts | None,
    cost: CostAnalysis | None,
) -> RevenueLeakLayer:
    metrics: list[RevenueLeakMetric] = []

    # — Third-party embed count — diagnostic: a CAUSE of the LCP/TBT loss already
    # priced in layer 1, not an independent loss. Pricing it too would double-count
    # the same slowness under a second label.
    domains = (third_party.total_third_party_domains or 0) if third_party else 0
    domains_measured = third_party is not None and third_party.total_third_party_domains is not None
    if domains_measured and domains > 10:
        signal = f"{domains} externe diensten laden mee bij elke pagina (gezond is <10) — een van de oorzaken van de laadtijd hierboven"
        app_status: MetricStatus = "critical" if domains > 20 else "warning"
    elif domains_measured:
        signal = f"{domains} externe diensten actief — binnen gezonde grens"
        app_status = "good"
    else:
        signal = None
        app_status = "not-measured"
    metrics.append(_diagnostic_metric(
        metric="Hoeveel externe diensten vertragen je winkel?",
        what_we_measure="Aantal losse trackers, widgets en embeds dat op elke pagina meeladt — los van of het via een Shopify-app draait",
        priority="high",
        calculation_note="Oorzaak van de laadtijd in Laag 1 — geen apart bedrag, want dat zou hetzelfde verlies dubbel tellen",
        signal=signal,
        status=app_status,
    ))

    # — Theme-bloat —
    unused_js = (performance.unused_javascript_kb or 0) if performance else 0
    js_measured = performance is not None and performance.unused_javascript_kb is not None
    if js_measured and unused_js > 150:
        signal = f"{unused_js:.0f}KB code die nooit gebruikt wordt, maar elke bezoeker downloadt — pure ballast"
        bloat_status: MetricStatus = "critical" if unused_js > 400 else "warning"
    elif js_measured:
        signal = f"{unused_js:.0f}KB onnodige code — valt mee, weinig ballast"
        bloat_status = "good"
    else:
        signal = None
        bloat_status = "not-measured"
    metrics.append(_diagnostic_metric(
        metric="Hoeveel overbodige code sleept je winkel mee?",
        what_we_measure="Hoeveel onnodige code je theme meelaadt die niets toevoegt maar wel laadtijd kost",
        priority="high",
        calculation_note="Oorzaak van de laadtijd in Laag 1 — geen apart bedrag, want dat zou hetzelfde verlies dubbel tellen",
        signal=signal,
        status=bloat_status,
    ))

    # — Third-party scripts —
    blocking = (third_party.total_third_party_blocking_ms or 0) if third_party else 0
    blocking_measured = third_party is not None and third_party.total_third_party_blocking_ms is not None
    if blocking_measured and blocking > 200:
        signal = f"Externe scripts laten je winkel {blocking:.0f}ms wachten — verloren tijd bij elke bezoeker"
        script_status: MetricStatus = "critical" if blocking > 500 else "warning"
    elif blocking_measured:
        signal = f"Externe scripts wachten {blocking:.0f}ms — geen probleem"
        script_status = "good"
    else:
        signal = None
        script_status = "not-measured"
    metrics.append(_diagnostic_metric(
        metric="Hoeveel externe scripts blokkeren je winkel?",
        what_we_measure="Externe diensten (tracking, chat, reviews) die de winkel laten wachten voor ze klaar zijn",
        priority="medium",
        calculation_note="Oorzaak van de laadtijd in Laag 1 — geen apart bedrag, want dat zou hetzelfde verlies dubbel tellen",
        signal=signal,
        status=script_status,
    ))

    # — TTFB —
    mobile_ttfb = performance.mobile.ttfb_ms if (performance and performance.mobile) else None
    if mobile_ttfb is not None and mobile_ttfb > 600:
        signal = f"Server doet er {mobile_ttfb:.0f}ms over om iets terug te sturen — bezoeker wacht voor er iets begint"
        ttfb_status: MetricStatus = "critical" if mobile_ttfb > 1_200 else "warning"
    elif mobile_ttfb is not None:
        signal = f"Server reageert in {mobile_ttfb:.0f}ms — snel genoeg"
        ttfb_status = "good"
    else:
        signal = None
        ttfb_status = "not-measured"
    metrics.append(_diagnostic_metric(
        metric="Hoe snel reageert je server?",
        what_we_measure="Hoe lang Shopify zelf nodig heeft voor er ook maar iets terugkomt — vaak een hostings/plan-probleem",
        priority="medium",
        calculation_note="Oorzaak van de laadtijd in Laag 1 — geen apart bedrag, want dat zou hetzelfde verlies dubbel tellen",
        signal=signal,
        status=ttfb_status,
    ))

    # — Tool-subscription cost — the one genuine euro figure this layer owns: real
    # app/tool subscription savings from build_cost_analysis, independent of the
    # revenue-loss model entirely.
    savings = cost.est_monthly_savings_eur if cost else None
    if savings is not None and savings > 0:
        cost_signal = f"€{savings:,.0f}/mnd te besparen op overbodige tools en scripts"
        cost_status: MetricStatus = "warning"
    elif cost is not None:
        cost_signal = "Geen overbodige tool-kosten gevonden"
        cost_status = "good"
    else:
        cost_signal = None
        cost_status = "not-measured"
    metrics.append(_cost_metric(
        metric="Hoeveel geef je uit aan tools die niets opleveren?",
        what_we_measure="Overbodige of dubbele apps en scripts die maandelijks geld kosten, los van hun snelheidsimpact",
        priority="medium",
        calculation_note="Directe subscription-besparing op overbodige of dubbele tools",
        signal=cost_signal,
        status=cost_status,
        monthly_value_eur=savings,
    ))

    return _finalize_layer(
        layer=2, name="De Motor",
        core_question="Wat maakt je stack traag en wat kost dat?",
        leads_to="Stack Rebuild™ — Architectuur",
        metrics=metrics, kind="cost",
    )


# --- registration: checkout & CRO findings (layer 3) -------------------------------

def _register_checkout_and_cro_findings(
    registry: FindingsRegistry,
    checkout: CheckoutFlow | None,
    performance: Performance | None,
    cro_observations: list[CroObservation],
    funnel: FunnelModel,
) -> dict:
    ctx: dict = {}
    checkout_probed = checkout is not None and checkout.probe_status == "ok"
    no_guest = bool(checkout and checkout.guest_checkout_available is False)
    fields_count = checkout.fields_in_address_form if checkout else None
    ctx["checkout_probed"] = checkout_probed

    if checkout_probed:
        if no_guest:
            registry.register(PricedFinding(
                finding_id="checkout.no_guest", owning_layer=3, stage="reach_checkout", kind="revenue",
                metric="Lekt de betaalpagina klanten?",
                what_we_measure="Wrijving tussen 'in winkelmand' en 'bedankt voor je bestelling' — de duurste plek om klanten te verliezen",
                priority="critical", status="critical",
                calculation_note="Baymard: gedwongen accountaanmaak is een van de grootste checkout-afhaakredenen; blended schatting over alle checkout-bezoekers",
                signal="geen gastbestelling mogelijk — klant móet eerst account aanmaken",
                exposure_share=1.0, uplift_low=0.03, uplift_high=0.08,
                confidence="medium", citation="BAYMARD_CHECKOUT_ABANDONMENT",
                pages_affected=["Checkout"],
            ), source="checkout")

        if fields_count is not None and fields_count > 12:
            n_over = fields_count - 10
            registry.register(PricedFinding(
                finding_id="checkout.address_fields", owning_layer=3, stage="reach_checkout", kind="revenue",
                metric="Lekt de betaalpagina klanten?",
                what_we_measure="Wrijving tussen 'in winkelmand' en 'bedankt voor je bestelling' — de duurste plek om klanten te verliezen",
                priority="critical",
                status="critical" if fields_count > 20 else "warning",
                calculation_note=f"{fields_count} velden vs. optimaal 8-10 (Baymard) → {min(0.08, n_over * 0.005) * 100:.1f}–{min(0.15, n_over * 0.010) * 100:.1f}% conversie-impact op checkout-bezoekers",
                signal=f"{fields_count} velden in het adresformulier (optimaal is 8-10)",
                exposure_share=1.0,
                uplift_low=min(0.08, n_over * 0.005),
                uplift_high=min(0.15, n_over * 0.010),
                confidence="medium", citation="BAYMARD_CHECKOUT_ABANDONMENT",
                pages_affected=["Checkout"],
            ), source="checkout")

        if not (checkout.express_checkout_methods if checkout else []):
            registry.register(PricedFinding(
                finding_id="checkout.no_express_pay", owning_layer=3, stage="reach_checkout", kind="revenue",
                metric="Lekt de betaalpagina klanten?",
                what_we_measure="Wrijving tussen 'in winkelmand' en 'bedankt voor je bestelling' — de duurste plek om klanten te verliezen",
                priority="medium", status="warning",
                calculation_note="Geen Shop Pay/Apple Pay/Google Pay-knop gevonden in de server-HTML — Shopify rendert deze vaak client-side, dus dit kan een fout-positief zijn",
                signal="geen Shop Pay / Apple Pay / Google Pay-knop gevonden op winkelmand of betaalpagina",
                confidence="low", verify_manually=True,
                pages_affected=["Checkout"],
            ), source="checkout")

        redirects = checkout.redirects_before_payment if checkout else 0
        ctx["redirects_signal"] = f"{redirects} redirects voor de betaalpagina" if redirects and redirects > 2 else None
    else:
        ctx["checkout_signal"] = "Betaalpagina niet bereikbaar voor outside-only meting"

    # — CLS —
    cls_val = performance.mobile.cls if (performance and performance.mobile) else None
    ctx["cls_val"] = cls_val
    if cls_val is not None and cls_val > 0.1:
        if cls_val > 0.25:
            uplift_low, uplift_high = 0.03, 0.06
        else:
            uplift_low, uplift_high = 0.01, 0.03
        registry.register(PricedFinding(
            finding_id="perf.cls_mobile", owning_layer=3, stage="product_view", kind="revenue",
            metric="Springt de pagina onder de muis weg?",
            what_we_measure="Knoppen of plaatjes die verspringen terwijl bezoekers proberen te klikken — voelt onbetrouwbaar",
            priority="medium",
            status="critical" if cls_val > 0.25 else "warning",
            calculation_note=f"€{funnel.monthly_revenue_eur:,.0f} omzet x {funnel.mobile_share * 100:.0f}% mobiel verkeer x {uplift_low * 100:.0f}–{uplift_high * 100:.0f}% conversie-impact",
            signal=f"Pagina springt regelmatig onder de cursor weg (score {cls_val:.2f}) — bezoekers raken vertrouwen kwijt",
            exposure_share=funnel.mobile_share, uplift_low=uplift_low, uplift_high=uplift_high,
            confidence="medium", citation="INTERNAL_ESTIMATE",
        ), source="performance")
    else:
        ctx["cls_signal"] = f"Pagina blijft netjes staan tijdens het laden (score {cls_val:.2f}) — vertrouwen blijft intact" if cls_val is not None else None
        ctx["cls_status"] = "good" if cls_val is not None else "not-measured"

    # — Social proof — grouped across pages into one finding; deliberately unpriced
    # (see CITATIONS["SPIEGEL_REVIEWS"] — that study compares 0 vs 5 reviews, not
    # "our scraper found no widget in server-rendered HTML", and our own detection
    # has a known false-negative rate against client-side-rendered review apps).
    social_proof_pages = [
        o.page for o in cro_observations
        if cro_finding_id(o.observation) == "cro.social_proof"
    ]
    if social_proof_pages:
        registry.register(PricedFinding(
            finding_id="cro.social_proof", owning_layer=3, stage="product_view", kind="revenue",
            metric="Mist je winkel sociaal bewijs?",
            what_we_measure="Reviews, sterren of vertrouwenssignalen op je belangrijkste pagina's — een bewezen koopdrempel als ze ontbreken",
            priority="high", status="critical",
            calculation_note="Spiegel Research Center meet 0-vs-5-reviews, niet 'geen widget gevonden in server-HTML' — daarom hier geen bedrag, wel een bevinding om handmatig te checken",
            signal=f"Geen reviews, sterren of vertrouwenssignalen gedetecteerd op: {', '.join(sorted(set(social_proof_pages)))}",
            confidence="low", verify_manually=True, citation="SPIEGEL_REVIEWS",
            pages_affected=sorted(set(social_proof_pages)),
        ), source="cro")

    # Every high-severity CRO observation is surfaced as an informational count
    # rather than given its own euro figure — that was the double-counting bug:
    # the same address-form or LCP finding priced once here on top of its
    # layer-1/checkout price. Classified into three buckets so the rollup metric
    # can say what actually happened to each one, instead of a single "already
    # counted" bucket that would wrongly include the unpriced social-proof finding.
    high_cro = [o for o in cro_observations if o.severity == "high"]
    ctx["high_cro_total"] = len(high_cro)
    ctx["high_cro_observations"] = high_cro

    return ctx


def _layer3_lekkage(
    registry: FindingsRegistry,
    priced: dict[str, tuple[float, float]],
    ctx: dict,
    checkout: CheckoutFlow | None,
    performance: Performance | None,
) -> tuple[RevenueLeakLayer, int]:
    metrics: list[RevenueLeakMetric] = []

    checkout_findings = [
        registry.get(fid) for fid in ("checkout.no_guest", "checkout.address_fields", "checkout.no_express_pay")
    ]
    checkout_findings = [f for f in checkout_findings if f is not None]
    if checkout_findings:
        priceable = [f for f in checkout_findings if f.is_priceable]
        lows = [priced[f.finding_id][0] for f in priceable if f.finding_id in priced]
        highs = [priced[f.finding_id][1] for f in priceable if f.finding_id in priced]
        low = sum(lows) if lows else None
        high = sum(highs) if highs else None
        low, high, mid = _pair(low, high)
        signals = [f.signal for f in checkout_findings if f.signal]
        worst_status = "critical" if any(f.status == "critical" for f in checkout_findings) else "warning"
        metrics.append(RevenueLeakMetric(
            metric="Lekt de betaalpagina klanten?",
            what_we_measure="Wrijving tussen 'in winkelmand' en 'bedankt voor je bestelling' — de duurste plek om klanten te verliezen",
            priority="critical",
            monthly_loss_eur=mid, annual_loss_eur=(mid * 12) if mid is not None else None,
            monthly_loss_eur_low=low, monthly_loss_eur_high=high,
            annual_loss_eur_low=(low * 12) if low is not None else None,
            annual_loss_eur_high=(high * 12) if high is not None else None,
            calculation_note="Elke hindernis in de betaalpagina kost klanten die al wilden kopen — rechtstreeks omzetverlies",
            signal="; ".join(signals) if signals else "geen hindernissen gevonden in de betaalpagina",
            status=worst_status,
            kind="revenue",
            pages_affected=["Checkout"],
        ))
    elif ctx.get("checkout_probed"):
        metrics.append(_revenue_metric_no_finding(
            metric="Lekt de betaalpagina klanten?",
            what_we_measure="Wrijving tussen 'in winkelmand' en 'bedankt voor je bestelling' — de duurste plek om klanten te verliezen",
            priority="critical",
            calculation_note="Elke hindernis in de betaalpagina kost klanten die al wilden kopen — rechtstreeks omzetverlies",
            signal="geen hindernissen gevonden in de betaalpagina",
            status="good",
        ))
    else:
        metrics.append(_revenue_metric_no_finding(
            metric="Lekt de betaalpagina klanten?",
            what_we_measure="Wrijving tussen 'in winkelmand' en 'bedankt voor je bestelling' — de duurste plek om klanten te verliezen",
            priority="critical",
            calculation_note="Elke hindernis in de betaalpagina kost klanten die al wilden kopen — rechtstreeks omzetverlies",
            signal=ctx.get("checkout_signal"),
            status="not-measured",
        ))

    cls_finding = registry.get("perf.cls_mobile")
    if cls_finding:
        metrics.append(_metric_from_finding(cls_finding, priced))
    else:
        metrics.append(_revenue_metric_no_finding(
            metric="Springt de pagina onder de muis weg?",
            what_we_measure="Knoppen of plaatjes die verspringen terwijl bezoekers proberen te klikken — voelt onbetrouwbaar",
            priority="medium",
            calculation_note="Verspringende elementen → misclicks en frustratie → bezoekers geven het op → minder omzet",
            signal=ctx.get("cls_signal"),
            status=ctx.get("cls_status", "not-measured"),
        ))

    # — Mobile Performance Gap — diagnostic: collinear with perf.lcp_mobile (both
    # come from the same Lighthouse runs), so it is not priced separately.
    mob_score = performance.lighthouse.performance if (performance and performance.lighthouse) else None
    desk_score = performance.desktop_lighthouse.performance if (performance and performance.desktop_lighthouse) else None
    both_measured = mob_score is not None and desk_score is not None
    gap = (desk_score - mob_score) if both_measured else None
    if both_measured and gap > 20:
        mobile_signal = f"Mobiel scoort {mob_score}/100, desktop {desk_score}/100 — je beste klantenkanaal werkt het slechtst"
        mobile_status: MetricStatus = "critical" if gap > 40 else "warning"
    elif both_measured:
        mobile_signal = f"Mobiel en desktop scoren vergelijkbaar ({gap}pt verschil) — goed"
        mobile_status = "good"
    else:
        mobile_signal = None
        mobile_status = "not-measured"
    metrics.append(_diagnostic_metric(
        metric="Verliest mobiel veel meer dan desktop?",
        what_we_measure="Het verschil tussen je mobiele en desktopwinkel — de meeste bezoekers zijn mobiel, dus elk procent verschil telt dubbel",
        priority="critical",
        calculation_note="Zelfde oorzaak als de laadtijd hierboven — geen apart bedrag, want dat zou dubbel tellen",
        signal=mobile_signal,
        status=mobile_status,
    ))

    social_proof_finding = registry.get("cro.social_proof")
    if social_proof_finding:
        metrics.append(_metric_from_finding(social_proof_finding, priced))
    else:
        metrics.append(_revenue_metric_no_finding(
            metric="Mist je winkel sociaal bewijs?",
            what_we_measure="Reviews, sterren of vertrouwenssignalen op je belangrijkste pagina's — een bewezen koopdrempel als ze ontbreken",
            priority="high",
            calculation_note="Spiegel Research Center meet 0-vs-5-reviews, niet 'geen widget gevonden in server-HTML'",
            signal="reviews/sterren gevonden op de belangrijkste pagina's",
            status="good",
        ))

    # — Pagina-specifieke bevindingen (informational rollup, no separate euro) —
    # classify each high-severity CRO observation by what actually happened to it,
    # so this metric never implies a finding was priced when it wasn't (that
    # conflation was the double-counting bug: treating "mapped to a known
    # finding_id" as "already counted in euros", when the social-proof finding is
    # deliberately shown WITHOUT a price).
    high_cro_observations = ctx.get("high_cro_observations", [])
    total_high = len(high_cro_observations)
    priced_elsewhere = 0
    shown_without_price = 0
    not_shown_elsewhere = 0
    for o in high_cro_observations:
        fid = cro_finding_id(o.observation)
        if fid and fid in priced:
            priced_elsewhere += 1
        elif fid and registry.get(fid) is not None:
            shown_without_price += 1
        else:
            not_shown_elsewhere += 1

    if total_high:
        parts = []
        if priced_elsewhere:
            parts.append(f"{priced_elsewhere} al beprijsd hierboven")
        if shown_without_price:
            parts.append(f"{shown_without_price} als aparte bevinding zonder bedrag (zie hierboven)")
        if not_shown_elsewhere:
            parts.append(f"{not_shown_elsewhere} nog te verifiëren")
        signal = f"{total_high} bevindingen op je belangrijkste pagina's ({', '.join(parts)})" if parts else f"{total_high} bevindingen op je belangrijkste pagina's"
        page_status: MetricStatus = "critical" if not_shown_elsewhere >= 3 else ("warning" if not_shown_elsewhere else "good")
    else:
        signal = "geen grote conversieblokkades gevonden op je pagina's"
        page_status = "good"
    metrics.append(_diagnostic_metric(
        metric="Welke pagina's lekken het meeste omzet?",
        what_we_measure="Productpagina's, collectiepagina's en homepage met aantoonbare conversieblokkades",
        priority="high",
        calculation_note="Overzicht van bevindingen per pagina — elk bedrag staat al bij de bijbehorende metric hierboven, niet nog een keer opgeteld",
        signal=signal,
        status=page_status,
    ))

    layer = _finalize_layer(
        layer=3, name="De Lekkage",
        core_question="Waar lekt conversie weg door technische frictie?",
        leads_to="Stack Rebuild™ — Checkout & Mobile",
        metrics=metrics, kind="revenue",
        unpriced_finding_count=shown_without_price + not_shown_elsewhere,
    )
    return layer, not_shown_elsewhere


# --- layer 4: restatement of layers 1+3, no new euros -------------------------------

def _layer4_efficientie(
    funnel: FunnelModel,
    layer1: RevenueLeakLayer,
    layer3: RevenueLeakLayer,
) -> RevenueLeakLayer:
    metrics: list[RevenueLeakMetric] = []

    low_sum = (layer1.est_monthly_loss_eur_low or 0) + (layer3.est_monthly_loss_eur_low or 0)
    high_sum = (layer1.est_monthly_loss_eur_high or 0) + (layer3.est_monthly_loss_eur_high or 0)
    has_data = bool(low_sum or high_sum)
    mid_uplift_share = 0.0
    if has_data and funnel.monthly_revenue_eur > 0:
        mid_uplift_share = ((low_sum + high_sum) / 2) / funnel.monthly_revenue_eur

    cr_now = funnel.conversion_rate
    cr_after = cr_now * (1 + mid_uplift_share)
    metrics.append(RevenueLeakMetric(
        metric="Hoeveel meer bezoekers zouden kopen bij een snelle winkel?",
        what_we_measure="Herformulering van de bevindingen in Laag 1 en 3, uitgedrukt als conversieratio in plaats van euro's",
        priority="high",
        monthly_loss_eur=None, annual_loss_eur=None,
        calculation_note="Geen nieuw bedrag — dit is dezelfde Laag 1+3 uitkomst, anders uitgedrukt",
        signal=(f"Nu koopt naar schatting {cr_now * 100:.2f}% van je bezoekers — als de bevindingen "
                f"hierboven zijn opgelost, richting {cr_after * 100:.2f}%") if has_data else "Onvoldoende data om te berekenen",
        status="warning" if has_data else "not-measured",
        kind="restatement",
    ))

    extra_purchases = funnel.monthly_sessions * (cr_after - cr_now)
    ad_spend = funnel.monthly_ad_spend_eur
    purchases_now = funnel.monthly_purchases
    if has_data and purchases_now > 0 and ad_spend > 0:
        cpa_now = ad_spend / purchases_now
        cpa_after = ad_spend / (purchases_now + extra_purchases) if (purchases_now + extra_purchases) > 0 else cpa_now
        cpa_signal = f"Een nieuwe klant kost nu €{cpa_now:.0f} — als de bevindingen hierboven zijn opgelost, €{cpa_after:.0f} (zelfde advertentiebudget)"
        cpa_status: MetricStatus = "warning"
    else:
        cpa_signal = "Onvoldoende data om te berekenen" if ad_spend > 0 else "Geen advertentiebudget bekend"
        cpa_status = "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Hoeveel goedkoper wordt elke nieuwe klant?",
        what_we_measure="Herformulering van dezelfde bevindingen, uitgedrukt als werfkosten per klant",
        priority="high",
        monthly_loss_eur=None, annual_loss_eur=None,
        calculation_note="Geen nieuw bedrag — dezelfde Laag 1+3 uitkomst, uitgedrukt als CPA",
        signal=cpa_signal,
        status=cpa_status,
        kind="restatement",
    ))

    if has_data:
        roas_signal = f"Als je de bevindingen hierboven oplost, komt er +€{(mid_uplift_share * funnel.monthly_revenue_eur):,.0f}/mnd bij uit hetzelfde advertentiebudget — dit is dezelfde Laag 1+3 lek, niet een extra bedrag"
        roas_status: MetricStatus = "warning"
    else:
        roas_signal = "Onvoldoende data om te berekenen"
        roas_status = "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Hoeveel meer haal je uit hetzelfde advertentiebudget?",
        what_we_measure="Herformulering van dezelfde bevindingen, uitgedrukt als extra omzet per advertentie-euro",
        priority="high",
        monthly_loss_eur=None, annual_loss_eur=None,
        calculation_note="Geen nieuw bedrag — dezelfde Laag 1+3 uitkomst, uitgedrukt als ROAS-uplift",
        signal=roas_signal,
        status=roas_status,
        kind="restatement",
    ))

    return _finalize_layer(
        layer=4, name="De Efficiëntie",
        core_question="Hoeveel meer omzet zit er in bestaande traffic, uitgedrukt in de taal van marketing en finance?",
        leads_to="Performance Layer™",
        metrics=metrics, kind="restatement",
    )


def _layer5_toekomst(
    rich_results: RichResultsHealth | None,
    product_feeds: ProductFeedHealth | None,
    accessibility: AccessibilityHealth | None,
) -> RevenueLeakLayer:
    metrics: list[RevenueLeakMetric] = []
    sub_scores: list[float] = []

    # — Structured Data Score —
    checks = 0
    schema_score = 0
    if rich_results:
        checks = 3
        if rich_results.has_product_schema:
            schema_score += 1
        if rich_results.has_aggregate_rating:
            schema_score += 1
        if rich_results.has_breadcrumb:
            schema_score += 1
    missing = []
    if rich_results and not rich_results.has_product_schema:
        missing.append("productgegevens voor zoekmachines")
    if rich_results and not rich_results.has_aggregate_rating:
        missing.append("reviewscore in zoekresultaten")
    if rich_results and not rich_results.has_breadcrumb:
        missing.append("paginapad in zoekresultaten")
    sd_pct = (schema_score / checks * 100) if checks else 0
    sub_scores.append(sd_pct)
    sd_status: MetricStatus = "good" if sd_pct >= 75 else ("warning" if sd_pct >= 40 else ("critical" if checks else "not-measured"))
    metrics.append(RevenueLeakMetric(
        metric="Vindbaar in Google én ChatGPT?",
        what_we_measure="Of zoekmachines en AI-assistenten je producten goed begrijpen en kunnen aanbevelen",
        priority="high",
        monthly_loss_eur=None,
        annual_loss_eur=None,
        calculation_note="Ontbrekende info → minder zichtbaar in Google-resultaten en AI-aanbevelingen → minder organisch verkeer",
        signal=(f"Google ziet {schema_score} van {checks} productgegevens" + (f" — mist: {', '.join(missing)}" if missing else " — alles aanwezig")) if checks else "Niet gemeten",
        status=sd_status,
    ))

    # — Checkout Accessibility —
    a11y_score = accessibility.lighthouse_score if accessibility else None
    a11y_pct = float(a11y_score) if a11y_score is not None else 50.0
    sub_scores.append(a11y_pct)
    a11y_status: MetricStatus = "good" if a11y_pct >= 75 else ("warning" if a11y_pct >= 40 else ("critical" if a11y_score is not None else "not-measured"))
    metrics.append(RevenueLeakMetric(
        metric="Kunnen álle klanten je winkel gebruiken?",
        what_we_measure="Of klanten met een minder goed zicht, ouderen of mensen met motorische beperkingen ook kunnen bestellen — verloren omzet én juridisch risico",
        priority="high",
        monthly_loss_eur=None,
        annual_loss_eur=None,
        calculation_note="Lage toegankelijkheid sluit een deel van je klanten buiten — verloren omzet én reputatierisico",
        signal=f"Toegankelijkheid {a11y_score}/100 — {'goed, de meeste klanten kunnen bestellen' if a11y_pct >= 75 else 'een deel van je klanten kan niet bestellen'}" if a11y_score is not None else "Niet gemeten",
        status=a11y_status,
    ))

    # — AI-Agent Data Completeness —
    feed_status = product_feeds.google_merchant_ready_estimate if product_feeds else None
    feed_signal = f"Google Merchant: {feed_status}" if feed_status else "Niet gedetecteerd"
    ai_data_score = 0
    ai_data_max = 5
    if rich_results and rich_results.has_product_schema:
        ai_data_score += 1
    if rich_results and rich_results.has_aggregate_rating:
        ai_data_score += 1
    if product_feeds and product_feeds.google_merchant_ready_estimate == "ready":
        ai_data_score += 2
    elif product_feeds and product_feeds.google_merchant_ready_estimate == "partial":
        ai_data_score += 1
    if rich_results and rich_results.has_breadcrumb:
        ai_data_score += 1
    ai_pct = ai_data_score / ai_data_max * 100
    sub_scores.append(ai_pct)
    ai_status: MetricStatus = "good" if ai_pct >= 75 else ("warning" if ai_pct >= 40 else "critical")
    metrics.append(RevenueLeakMetric(
        metric="Klaar voor klanten die via AI shoppen?",
        what_we_measure="Of ChatGPT, Gemini en andere AI-assistenten je producten kunnen aanbevelen als klanten om advies vragen",
        priority="high",
        monthly_loss_eur=None,
        annual_loss_eur=None,
        calculation_note="Ontbrekende productdata → AI-assistenten kunnen je producten niet aanbevelen → gemiste verkopen",
        signal=f"{ai_data_score}/{ai_data_max} datapunten klaar voor AI-aanbevelingen — {feed_signal}",
        status=ai_status,
    ))

    # — MCP/Protocol Readiness —
    mcp_level = "hoog" if (rich_results and rich_results.has_product_schema and product_feeds and product_feeds.google_merchant_ready_estimate == "ready") else \
                "midden" if (rich_results and rich_results.has_product_schema) else "laag"
    mcp_pct = {"laag": 25.0, "midden": 60.0, "hoog": 90.0}[mcp_level]
    sub_scores.append(mcp_pct)
    mcp_status: MetricStatus = "good" if mcp_pct >= 75 else ("warning" if mcp_pct >= 40 else "critical")
    _mcp_signal = {
        "laag": "Nog niet klaar voor verkoop via AI-assistenten — basis ontbreekt",
        "midden": "Klaar voor AI-verkoop: gedeeltelijk — basis aanwezig, nog niet volledig",
        "hoog": "Goed klaar voor AI-verkoop — winkel zichtbaar voor AI-assistenten",
    }[mcp_level]
    metrics.append(RevenueLeakMetric(
        metric="Klaar voor verkoop via AI-assistenten?",
        what_we_measure="Of je winkel kan verkopen via AI-agents die straks namens klanten gaan kopen — nieuw verkoopkanaal in opkomst",
        priority="medium",
        monthly_loss_eur=None,
        annual_loss_eur=None,
        calculation_note="Niet klaar voor AI-kanalen → je concurrenten pakken straks die verkopen en jij niet",
        signal=_mcp_signal,
        status=mcp_status,
    ))

    readiness_score = round(sum(sub_scores) / len(sub_scores)) if sub_scores else 0
    key_signals = [m.signal for m in metrics if m.signal]
    good_signals, improvement_signals = _layer_signals(metrics)

    return RevenueLeakLayer(
        layer=5,
        name="De Toekomst",
        core_question="Hoe vindbaar en koopbaar ben je voor AI en nieuwe kanalen?",
        est_monthly_loss_eur=None,
        est_annual_loss_eur=None,
        metric_count=len(metrics),
        leads_to="Agentic Commerce Readiness™",
        key_signals=key_signals[:5],
        metrics=metrics,
        readiness_score=readiness_score,
        summary=f"AI/toekomst-gereedheid {readiness_score}/100",
        good_signals=good_signals,
        improvement_signals=improvement_signals,
        kind="readiness",
    )


def _detect_ceo_triggers(
    performance: Performance | None,
    ad_traffic: AdTrafficImpact | None,
    third_party: ThirdPartyScripts | None,
    checkout: CheckoutFlow | None,
    rich_results: RichResultsHealth | None,
    product_feeds: ProductFeedHealth | None,
) -> list[CeoTriggerKpi]:
    perf_score = performance.lighthouse.performance if (performance and performance.lighthouse) else None
    # `performance.lighthouse` is the MOBILE run; `performance.desktop_lighthouse` is the
    # separate DESKTOP run — two independent measurements, not one derived from the other.
    mob_score = perf_score
    desk_score = performance.desktop_lighthouse.performance if (performance and performance.desktop_lighthouse) else None
    mob_gap = (desk_score - mob_score) if (desk_score is not None and mob_score is not None) else 0

    triggers = [
        CeoTriggerKpi(
            category="Omzet & Groei",
            kpi="ROAS daalt terwijl ad spend stijgt",
            what_ceo_sees="Elke extra euro in ads levert minder op. Meer budget = niet meer omzet.",
            benchmark=None,
            alarm_signal="ROAS < 3x bij stijgende spend",
            real_meaning="De store lekt bezoekers vóórdat ze converteren. Meer traffic naar een lekkende funnel versterkt het probleem.",
            tradual_pitch="Je giet water in een emmer met gaten. Wij dichten de gaten zodat elke euro ad spend meer oplevert.",
            tradual_solution="Stack Rebuild™ + Performance Layer™",
            triggered=bool(ad_traffic and ad_traffic.est_wasted_ad_spend_pct and ad_traffic.est_wasted_ad_spend_pct > 20),
        ),
        CeoTriggerKpi(
            category="Conversie & Funnel",
            kpi="Mobile converteert dramatisch lager dan desktop",
            what_ceo_sees="Desktop converteert 2-3x beter dan mobiel, terwijl 70%+ van het traffic mobiel is.",
            benchmark="Max 30% lager dan desktop",
            alarm_signal="Mobiel CR < 50% van desktop CR",
            real_meaning="De mobiel-desktop gap is bijna nooit een UX-probleem. Het is een performance-probleem: mobiel is gevoeliger voor laadtijd.",
            tradual_pitch="70% van jullie bezoekers is mobiel. Als die helft zo slecht converteert, laten jullie het meeste geld liggen waar het meeste traffic zit.",
            tradual_solution="Stack Rebuild™ — mobile-first architectuur",
            triggered=mob_gap > 30,
        ),
        CeoTriggerKpi(
            category="Kosten & Efficiëntie",
            kpi="CPA stijgt structureel",
            what_ceo_sees="Het kost steeds meer om een nieuwe klant te werven. Marketing wordt duurder.",
            benchmark=None,
            alarm_signal="CPA stijgt >15% YoY",
            real_meaning="Als je funnel lekt, heb je meer klikken nodig per conversie — en elke klik kost geld.",
            tradual_pitch="Jullie CPA stijgt niet alleen omdat ads duurder worden. Fix de store en je CPA daalt — zonder je ad strategie te veranderen.",
            tradual_solution="Revenue Leak Audit™ → Stack Rebuild™",
            triggered=bool(perf_score and perf_score < 50 and ad_traffic and (ad_traffic.est_wasted_ad_spend_pct or 0) > 15),
        ),
        CeoTriggerKpi(
            category="Concurrentie & Toekomst",
            kpi="Geen organische groei ondanks SEO-investering",
            what_ceo_sees="SEO-inspanningen leveren niet op. Rankings stagneren of dalen.",
            benchmark=None,
            alarm_signal="Geen ranking-groei na 6 maanden SEO",
            real_meaning="Google beloont Core Web Vitals in de ranking. Een trage site verliest van een snelle concurrent.",
            tradual_pitch="Google rankt niet alleen op content. Ze ranken op ervaring. Jullie Core Web Vitals zijn een ranking-factor — en op dit moment werken ze tegen jullie.",
            tradual_solution="Stack Rebuild™ — Core Web Vitals",
            triggered=bool(perf_score and perf_score < 50 and rich_results and not rich_results.has_product_schema),
        ),
        CeoTriggerKpi(
            category="Concurrentie & Toekomst",
            kpi="Niet vindbaar via AI-assistenten",
            what_ceo_sees="Klanten vragen ChatGPT/Gemini om productadvies en jullie merk verschijnt niet.",
            benchmark=None,
            alarm_signal="Niet genoemd in AI-antwoorden",
            real_meaning="AI-agents vertrouwen op gestructureerde data en API-toegankelijkheid. Zonder dat ben je onzichtbaar.",
            tradual_pitch="Over 2 jaar start 30%+ van de productzoektochten bij een AI-agent. Als die agent jullie niet kan vinden, bestaan jullie niet in die wereld.",
            tradual_solution="Agentic Commerce Readiness™",
            triggered=bool(rich_results and not rich_results.has_product_schema) or bool(product_feeds and product_feeds.google_merchant_ready_estimate == "not-ready"),
        ),
        CeoTriggerKpi(
            category="Kosten & Efficiëntie",
            kpi="Externe diensten stapelen zich op zonder meetbaar resultaat",
            what_ceo_sees="Elke maand meer tools, meer subscriptions, maar geen meetbaar effect op omzet.",
            benchmark=None,
            alarm_signal=">15 externe diensten laden mee op elke pagina",
            real_meaning="Elke externe dienst voegt gewicht toe aan de store. Je betaalt mogelijk dubbel: de subscription + het conversieverlies dat de dienst veroorzaakt.",
            tradual_pitch="Jullie betalen per maand aan tools die jullie store vertragen. Sommige kosten meer aan conversieverlies dan ze opleveren aan functionaliteit.",
            tradual_solution="Revenue Leak Audit™ — Laag 2: De Motor",
            triggered=bool(third_party and third_party.total_third_party_domains and third_party.total_third_party_domains > 15),
        ),
        CeoTriggerKpi(
            category="Conversie & Funnel",
            kpi="Cart abandonment boven 75%",
            what_ceo_sees="3 van de 4 klanten die iets in hun winkelwagen doen, rekenen niet af.",
            benchmark="65–70%",
            alarm_signal="Abandonment > 75%",
            real_meaning="Checkout-latency en layout shifts breken het vertrouwen op het cruciale moment.",
            tradual_pitch="Jullie hebben de klant al overtuigd — die heeft op 'toevoegen' geklikt. En dan verliezen jullie ze in de checkout. Dat is het duurste verlies dat er is.",
            tradual_solution="Stack Rebuild™ — checkout-optimalisatie",
            triggered=bool(checkout and checkout.observed_friction),
        ),
        CeoTriggerKpi(
            category="Omzet & Groei",
            kpi="Omzet plateau ondanks meer traffic",
            what_ceo_sees="Het bezoekersaantal stijgt, maar de omzet groeit niet mee. Meer traffic = niet meer verkoop.",
            benchmark=None,
            alarm_signal="Traffic stijgt, omzet stagneert",
            real_meaning="Meer bezoekers vangen niet meer omzet omdat de funnel evenredig blijft lekken — het is een conversieprobleem, geen acquisitieprobleem. Extra traffic naar een lekkende funnel maakt de schade groter.",
            tradual_pitch="Jullie groeien in bezoekers maar niet in omzet. Dat betekent: de winkel zelf is het knelpunt, niet jullie marketing. Dicht de lekken en elke extra bezoeker levert eindelijk omzet op.",
            tradual_solution="Revenue Leak Audit™ → Stack Rebuild™",
            triggered=bool(perf_score and perf_score < 60),
        ),
        CeoTriggerKpi(
            category="Conversie & Funnel",
            kpi="Conversieratio onder branche-gemiddelde",
            what_ceo_sees="Van elke 100 bezoekers koopt er minder dan 2. Concurrenten halen meer uit hetzelfde traffic.",
            benchmark="DTC: 2.0–3.5%",
            alarm_signal="Geschatte conversieratio onder 2%",
            real_meaning="Een lage paginascore gecombineerd met een groot snelheidsverschil tussen mobiel en desktop drukt de conversieratio structureel onder het branche-gemiddelde. Funnel-frictie eet de conversie op.",
            tradual_pitch="Elke bezoeker die niet koopt is verloren acquisitiekosten. Bij een conversieratio onder de 2% laat je dagelijks omzet op tafel liggen die jullie concurrenten wél pakken.",
            tradual_solution="Revenue Leak Audit™ → Performance Layer™",
            triggered=bool(perf_score and perf_score < 70),
        ),
        CeoTriggerKpi(
            category="Conversie & Funnel",
            kpi="Hoge bounce op advertentieverkeer",
            what_ceo_sees="Meer dan de helft van de mensen die op een advertentie klikken, vertrekken direct zonder iets te doen.",
            benchmark="Paid traffic: <45%",
            alarm_signal="Geschatte post-click bounce > 50%",
            real_meaning="Meer dan de helft van de betaalde klikkers verlaat de pagina voordat die volledig geladen is — direct verbrand advertentiebudget zonder kans op een verkoop.",
            tradual_pitch="Jullie betalen voor elke klik, maar meer dan de helft van die klikkers ziet jullie winkel nooit echt. De pagina is te traag — en de advertentie-euro is dan meteen weg.",
            tradual_solution="Stack Rebuild™ — Snelheid",
            triggered=bool(ad_traffic and ad_traffic.est_post_click_bounce_pct and ad_traffic.est_post_click_bounce_pct > 50),
        ),
        CeoTriggerKpi(
            category="Kosten & Efficiëntie",
            kpi="Klantwaarde dekt werfkosten nauwelijks",
            what_ceo_sees="Het kost steeds meer om een klant te werven, maar die klant koopt niet genoeg terug om dat te rechtvaardigen.",
            benchmark="Gezonde DTC: 3:1 of hoger",
            alarm_signal="Klantwaarde/werfkosten ratio < 3",
            real_meaning="Bij stijgende werfkosten en een lekkende funnel daalt de klantwaarde t.o.v. acquisitiekosten. De unit-economics breken — elke klant kost relatief steeds meer.",
            tradual_pitch="Een gezond e-commercebedrijf verdient minimaal drie keer de werfkosten terug per klant. Als die verhouding daalt, kan het niet langer alleen aan de markt liggen — dan lekt de winkel zelf.",
            tradual_solution="Revenue Leak Audit™ → Performance Layer™",
            triggered=bool(perf_score and perf_score < 50 and ad_traffic and (ad_traffic.est_wasted_ad_spend_pct or 0) > 20),
        ),
    ]

    return triggers


def calculate_revenue_leak(
    performance: Performance | None,
    third_party: ThirdPartyScripts | None,
    tracking: TrackingDataQuality | None,
    checkout: CheckoutFlow | None,
    owned: OwnedChannels | None,
    cro_observations: list[CroObservation],
    rich_results: RichResultsHealth | None,
    product_feeds: ProductFeedHealth | None,
    accessibility: AccessibilityHealth | None,
    ad_traffic: AdTrafficImpact | None,
    annual_revenue_eur: float | None = None,
    traffic: SeRankingTraffic | None = None,
    aov_override: float | None = None,
    sessions_override: int | None = None,
    cr_override_pct: float | None = None,
    ad_spend_override: float | None = None,
    cost: CostAnalysis | None = None,
) -> RevenueLeakReport:
    funnel, data_conflicts = build_funnel_model(
        annual_revenue_eur, traffic,
        aov_override=aov_override,
        sessions_override=sessions_override,
        cr_override_pct=cr_override_pct,
        ad_spend_override=ad_spend_override,
    )

    registry = FindingsRegistry()
    layer1_ctx = _register_performance_findings(registry, performance, ad_traffic, funnel)
    layer3_ctx = _register_checkout_and_cro_findings(registry, checkout, performance, cro_observations, funnel)
    priced = price_findings(registry, funnel)

    layer1 = _layer1_deur(registry, priced, layer1_ctx, ad_traffic, funnel)
    layer2 = _layer2_motor(performance, third_party, cost)
    layer3, _unmapped_count = _layer3_lekkage(registry, priced, layer3_ctx, checkout, performance)
    layer4 = _layer4_efficientie(funnel, layer1, layer3)
    layer5 = _layer5_toekomst(rich_results, product_feeds, accessibility)

    layers = [layer1, layer2, layer3, layer4, layer5]

    # "Leak" counts money already leaving the store today — layers 1+3 (speed/ad-bounce,
    # checkout/mobile friction). Layer 2 is a cost line (tool subscriptions), tracked
    # separately in cost_monthly_eur. Layer 4 is a restatement of layers 1+3 in
    # marketing/finance language, not new euros — it must never be added to the leak
    # total, or the same problem gets counted as "you're losing this" (layers 1+3) and
    # "you could gain this" (layer 4) at once.
    monthly_low = _r((layer1.est_monthly_loss_eur_low or 0) + (layer3.est_monthly_loss_eur_low or 0))
    monthly_high = _r((layer1.est_monthly_loss_eur_high or 0) + (layer3.est_monthly_loss_eur_high or 0))
    monthly_mid = _r((monthly_low + monthly_high) / 2)
    annual_low, annual_high, annual_mid = monthly_low * 12, monthly_high * 12, monthly_mid * 12

    cost_monthly = _r(layer2.est_monthly_loss_eur or 0)

    leak_share_low = (monthly_low / funnel.monthly_revenue_eur) if funnel.monthly_revenue_eur > 0 else None
    leak_share_high = (monthly_high / funnel.monthly_revenue_eur) if funnel.monthly_revenue_eur > 0 else None

    # ROI/payback is framed against money currently leaking (the midpoint of the
    # low/high range), giving a best/worst-case payback window instead of one
    # falsely-precise number.
    roi: RoiCalculation | None = None
    if monthly_mid > 0:
        payback_best = round(_STACK_REBUILD_COST / monthly_high, 1) if monthly_high > 0 else None
        payback_worst = round(_STACK_REBUILD_COST / monthly_low, 1) if monthly_low > 0 else None
        year_one_low = annual_low - _STACK_REBUILD_COST
        year_one_high = annual_high - _STACK_REBUILD_COST
        roi = RoiCalculation(
            monthly_leak_eur=monthly_mid,
            annual_leak_eur=annual_mid,
            stack_rebuild_cost_eur=_STACK_REBUILD_COST,
            payback_months=round(_STACK_REBUILD_COST / monthly_mid, 1),
            year_one_net_return_eur=(annual_mid - _STACK_REBUILD_COST),
            monthly_leak_eur_low=monthly_low, monthly_leak_eur_high=monthly_high,
            annual_leak_eur_low=annual_low, annual_leak_eur_high=annual_high,
            payback_months_best=payback_best, payback_months_worst=payback_worst,
            year_one_net_return_eur_low=year_one_low, year_one_net_return_eur_high=year_one_high,
            pays_back_within_12_months=(payback_worst is not None and payback_worst <= 12),
        )
        if year_one_low < 0:
            registry.warnings.append(ModelWarning(
                kind="negative_payback",
                detail=(
                    f"Bij de ondergrens van de schatting (€{monthly_low:,.0f}/mnd) is de "
                    f"Stack Rebuild-investering (€{_STACK_REBUILD_COST:,.0f}) niet binnen "
                    "jaar 1 terugverdiend."
                ),
            ))

    ceo_triggers = _detect_ceo_triggers(
        performance, ad_traffic, third_party, checkout, rich_results, product_feeds
    )

    return RevenueLeakReport(
        layers=layers,
        total_monthly_loss_eur=monthly_mid,
        total_annual_loss_eur=annual_mid,
        direct_monthly_loss_eur=monthly_mid,
        direct_annual_loss_eur=annual_mid,
        efficiency_monthly_uplift_eur=0.0,
        efficiency_annual_uplift_eur=0.0,
        total_monthly_loss_eur_low=monthly_low, total_monthly_loss_eur_high=monthly_high,
        total_annual_loss_eur_low=annual_low, total_annual_loss_eur_high=annual_high,
        cost_monthly_eur=cost_monthly if cost_monthly > 0 else None,
        leak_share_of_revenue_low=leak_share_low, leak_share_of_revenue_high=leak_share_high,
        methodology_note=funnel.methodology_note,
        ceo_triggers=ceo_triggers,
        roi=roi,
        data_source=funnel.data_source,
        funnel=funnel,
        data_conflicts=data_conflicts,
        model_warnings=registry.warnings,
        model_version=_MODEL_VERSION,
    )


__all__ = ["calculate_revenue_leak", "CITATIONS"]

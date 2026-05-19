from __future__ import annotations

from app.full_audit.schemas import (
    AccessibilityHealth,
    AdTrafficImpact,
    CeoTriggerKpi,
    CheckoutFlow,
    CroObservation,
    MetricStatus,
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

_DEFAULT_ANNUAL_REVENUE = 108_000.0  # = €9k/mnd legacy benchmark
_STACK_REBUILD_COST = 35_000.0


def _benchmarks(
    annual_revenue_eur: float | None,
    traffic: SeRankingTraffic | None = None,
) -> dict:
    monthly = (annual_revenue_eur or _DEFAULT_ANNUAL_REVENUE) / 12
    aov = 75.0 if monthly < 50_000 else 95.0 if monthly < 250_000 else 120.0
    ad_spend = monthly * 0.15

    if traffic is not None:
        sessions = float(traffic.monthly_organic_sessions + traffic.monthly_paid_sessions)
        # Compute actual conversion rate from real sessions; clamp to plausible range.
        cr = max(0.005, min(0.25, monthly / (sessions * aov))) if sessions > 0 else 0.03
        data_source = "measured"
    else:
        cr = 0.03
        sessions = monthly / (aov * cr)
        data_source = "heuristic"

    scale = monthly / 9_000.0
    return {
        "monthly_revenue": monthly,
        "monthly_sessions": sessions,
        "aov": aov,
        "cr": cr,
        "monthly_ad_spend": ad_spend,
        "scale": scale,
        "data_source": data_source,
    }


def _r(value: float) -> float:
    return float(round(value / 100) * 100)


def _layer_signals(metrics: list[RevenueLeakMetric]) -> tuple[list[str], list[str]]:
    good = [m.signal for m in metrics if m.status == "good" and m.signal]
    improve = [m.signal for m in metrics if m.status in ("warning", "critical") and m.signal]
    return good, improve


def _layer1_deur(
    performance: Performance | None,
    ad_traffic: AdTrafficImpact | None,
    bench: dict,
) -> RevenueLeakLayer:
    metrics: list[RevenueLeakMetric] = []
    s = bench["scale"]

    # — LCP —
    lcp_ms = None
    if performance and performance.mobile:
        lcp_ms = performance.mobile.lcp_ms
    if lcp_ms is None and performance and performance.desktop_lcp_ms:
        lcp_ms = performance.desktop_lcp_ms
    if lcp_ms is not None and lcp_ms > 2_500:
        factor = min(0.25, (lcp_ms - 2_500) / 1_000 * 0.04)
        loss = _r(bench["monthly_revenue"] * factor)
        signal = f"Bezoekers wachten {lcp_ms / 1000:.1f}s voor ze je producten zien — te traag, ze haken af"
        lcp_status: MetricStatus = "critical" if lcp_ms > 4_000 else "warning"
    else:
        loss = 0.0
        signal = f"Producten zichtbaar in {lcp_ms / 1000:.1f}s — bezoekers blijven hangen" if lcp_ms else None
        lcp_status = "good" if lcp_ms is not None else "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Hoe snel zien bezoekers je producten?",
        what_we_measure="Hoe lang bezoekers wachten voor ze überhaupt iets te zien krijgen — elke seconde extra wachten kost klanten",
        priority="high",
        monthly_loss_eur=loss,
        annual_loss_eur=loss * 12,
        calculation_note="Trage laadtijd → bezoekers haken af → omzet die je misloopt",
        signal=signal,
        status=lcp_status,
    ))

    # — INP (proxy via TBT) —
    tbt_ms = performance.tbt_ms if performance else None
    if tbt_ms is not None and tbt_ms > 200:
        inp_loss = _r(min(1_500.0 * s, (tbt_ms - 200) / 100 * 60 * s))
        signal = f"Pagina reageert pas na {tbt_ms:.0f}ms op een klik — voelt traag en stuk"
        inp_status: MetricStatus = "critical" if tbt_ms > 300 else "warning"
    else:
        inp_loss = 0.0
        signal = f"Pagina reageert direct in {tbt_ms:.0f}ms — voelt snel en soepel" if tbt_ms is not None else None
        inp_status = "good" if tbt_ms is not None else "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Reageert de pagina meteen op klikken?",
        what_we_measure="Of klikken op knoppen en menu's direct werkt of dat bezoekers moeten wachten",
        priority="high",
        monthly_loss_eur=inp_loss,
        annual_loss_eur=inp_loss * 12,
        calculation_note="Trage reactie → bezoekers denken dat het kapot is → ze vertrekken",
        signal=signal,
        status=inp_status,
    ))

    # — Bounce-by-load-time —
    if ad_traffic and ad_traffic.est_post_click_bounce_pct is not None:
        bounce_delta = max(0.0, ad_traffic.est_post_click_bounce_pct - ad_traffic.bounce_baseline_pct)
        bounce_loss = _r(min(
            bench["monthly_revenue"] * 0.20,
            bounce_delta * bench["monthly_sessions"] / 100 * bench["aov"] * bench["cr"],
        ))
        if bounce_delta > 0:
            signal = f"{ad_traffic.est_post_click_bounce_pct:.0f}% vertrekt direct — {bounce_delta:.0f}% boven gezond, dat is verloren omzet"
        else:
            signal = f"{ad_traffic.est_post_click_bounce_pct:.0f}% vertrekt direct (gezond is ~{ad_traffic.bounce_baseline_pct:.0f}%)"
        bounce_status: MetricStatus = "critical" if ad_traffic.est_post_click_bounce_pct > 60 else ("warning" if bounce_delta > 0 else "good")
    else:
        bounce_loss = 0.0
        signal = None
        bounce_status = "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Hoeveel bezoekers vertrekken vóór ze iets zien?",
        what_we_measure="Het deel van je bezoekers dat direct wegklikt omdat de pagina te traag laadt",
        priority="high",
        monthly_loss_eur=bounce_loss,
        annual_loss_eur=bounce_loss * 12,
        calculation_note="Extra weglopers × gemiddelde bestelwaarde × kans op aankoop = misgelopen omzet",
        signal=signal,
        status=bounce_status,
    ))

    # — Ad-spend-verdamping —
    if ad_traffic and ad_traffic.est_wasted_ad_spend_pct is not None:
        ad_loss = _r(min(
            bench["monthly_ad_spend"] * 0.30,
            bench["monthly_ad_spend"] * ad_traffic.est_wasted_ad_spend_pct / 100,
        ))
        signal = f"{ad_traffic.est_wasted_ad_spend_pct:.0f}% van je advertentiebudget verbrandt — de klikker ziet je winkel nooit echt"
        ad_status: MetricStatus = "critical" if ad_traffic.est_wasted_ad_spend_pct > 30 else "warning"
    else:
        ad_loss = 0.0
        signal = None
        ad_status = "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Hoeveel advertentiegeld verdampt vóór de pagina laadt?",
        what_we_measure="Het deel van je advertentiebudget waarvoor je betaalt maar geen klant terug krijgt — de klikker is weg vóór de pagina klaar is",
        priority="critical",
        monthly_loss_eur=ad_loss,
        annual_loss_eur=ad_loss * 12,
        calculation_note="Verdampt deel × maandelijks advertentiebudget = direct verbrand geld",
        signal=signal,
        status=ad_status,
    ))

    total = _r(sum(m.monthly_loss_eur or 0 for m in metrics))
    key_signals = [m.signal for m in metrics if m.signal and (m.monthly_loss_eur or 0) > 0]
    good_signals, improvement_signals = _layer_signals(metrics)
    measured = sum(1 for m in metrics if m.status != "not-measured")
    good_count = sum(1 for m in metrics if m.status == "good")

    return RevenueLeakLayer(
        layer=1,
        name="De Deur",
        core_question="Hoeveel bezoekers verliezen we vóórdat ze iets kunnen doen?",
        est_monthly_loss_eur=total,
        est_annual_loss_eur=total * 12,
        metric_count=len(metrics),
        leads_to="Stack Rebuild™ — Snelheid",
        key_signals=key_signals[:4],
        metrics=metrics,
        summary=f"{good_count} van {measured} gemeten metrics binnen benchmark" if measured else "Onvoldoende data",
        good_signals=good_signals,
        improvement_signals=improvement_signals,
    )


def _layer2_motor(
    performance: Performance | None,
    third_party: ThirdPartyScripts | None,
    bench: dict,
) -> RevenueLeakLayer:
    metrics: list[RevenueLeakMetric] = []
    s = bench["scale"]

    # — App-impact —
    domains = (third_party.total_third_party_domains or 0) if third_party else 0
    domains_measured = third_party is not None
    if domains_measured and domains > 10:
        app_loss = _r(min(bench["monthly_revenue"] * 0.05, (domains - 10) * 50 * s))
        signal = f"{domains} apps draaien mee bij elke pagina (gezond is <10) — ze remmen de winkel af"
        app_status: MetricStatus = "critical" if domains > 20 else "warning"
    elif domains_measured:
        app_loss = 0.0
        signal = f"{domains} apps actief — binnen gezonde grens"
        app_status = "good"
    else:
        app_loss = 0.0
        signal = None
        app_status = "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Hoeveel apps vertragen je winkel?",
        what_we_measure="Of de Shopify-apps die je betaalt je winkel niet meer kosten in omzet dan ze opleveren",
        priority="high",
        monthly_loss_eur=app_loss,
        annual_loss_eur=app_loss * 12,
        calculation_note="Extra apps boven gezonde grens → trager → minder verkopen → omzetverlies",
        signal=signal,
        status=app_status,
    ))

    # — Theme-bloat —
    unused_js = (performance.unused_javascript_kb or 0) if performance else 0
    js_measured = performance is not None and performance.unused_javascript_kb is not None
    if js_measured and unused_js > 150:
        bloat_loss = _r(min(bench["monthly_revenue"] * 0.04, (unused_js - 150) / 100 * 45 * s))
        signal = f"{unused_js:.0f}KB code die nooit gebruikt wordt, maar elke bezoeker downloadt — pure ballast"
        bloat_status: MetricStatus = "critical" if unused_js > 400 else "warning"
    elif js_measured:
        bloat_loss = 0.0
        signal = f"{unused_js:.0f}KB onnodige code — valt mee, weinig ballast"
        bloat_status = "good"
    else:
        bloat_loss = 0.0
        signal = None
        bloat_status = "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Hoeveel overbodige code sleept je winkel mee?",
        what_we_measure="Hoeveel onnodige code je theme meelaadt die niets toevoegt maar wel laadtijd kost",
        priority="high",
        monthly_loss_eur=bloat_loss,
        annual_loss_eur=bloat_loss * 12,
        calculation_note="Overbodig gewicht → langere laadtijd → minder bestellingen → omzet weg",
        signal=signal,
        status=bloat_status,
    ))

    # — Third-party scripts —
    blocking = (third_party.total_third_party_blocking_ms or 0) if third_party else 0
    blocking_measured = third_party is not None and third_party.total_third_party_blocking_ms is not None
    if blocking_measured and blocking > 200:
        script_loss = _r(min(bench["monthly_revenue"] * 0.03, (blocking - 200) / 100 * 55 * s))
        signal = f"Externe scripts laten je winkel {blocking:.0f}ms wachten — verloren tijd bij elke bezoeker"
        script_status: MetricStatus = "critical" if blocking > 500 else "warning"
    elif blocking_measured:
        script_loss = 0.0
        signal = f"Externe scripts wachten {blocking:.0f}ms — geen probleem"
        script_status = "good"
    else:
        script_loss = 0.0
        signal = None
        script_status = "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Hoeveel externe scripts blokkeren je winkel?",
        what_we_measure="Externe diensten (tracking, chat, reviews) die de winkel laten wachten voor ze klaar zijn",
        priority="medium",
        monthly_loss_eur=script_loss,
        annual_loss_eur=script_loss * 12,
        calculation_note="Extra wachttijd door externe diensten → bezoekers haken af → minder omzet",
        signal=signal,
        status=script_status,
    ))

    # — TTFB —
    mobile_ttfb = performance.mobile.ttfb_ms if (performance and performance.mobile) else None
    if mobile_ttfb is not None and mobile_ttfb > 600:
        ttfb_loss = _r(min(bench["monthly_revenue"] * 0.02, (mobile_ttfb - 600) / 100 * 30 * s))
        signal = f"Server doet er {mobile_ttfb:.0f}ms over om iets terug te sturen — bezoeker wacht voor er iets begint"
        ttfb_status: MetricStatus = "critical" if mobile_ttfb > 1_200 else "warning"
    elif mobile_ttfb is not None:
        ttfb_loss = 0.0
        signal = f"Server reageert in {mobile_ttfb:.0f}ms — snel genoeg"
        ttfb_status = "good"
    else:
        ttfb_loss = 0.0
        signal = None
        ttfb_status = "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Hoe snel reageert je server?",
        what_we_measure="Hoe lang Shopify zelf nodig heeft voor er ook maar iets terugkomt — vaak een hostings/plan-probleem",
        priority="medium",
        monthly_loss_eur=ttfb_loss,
        annual_loss_eur=ttfb_loss * 12,
        calculation_note="Trage server → trage hele winkel → minder bestellingen → minder omzet",
        signal=signal,
        status=ttfb_status,
    ))

    total = _r(sum(m.monthly_loss_eur or 0 for m in metrics))
    key_signals = [m.signal for m in metrics if m.signal and (m.monthly_loss_eur or 0) > 0]
    good_signals, improvement_signals = _layer_signals(metrics)
    measured = sum(1 for m in metrics if m.status != "not-measured")
    good_count = sum(1 for m in metrics if m.status == "good")

    return RevenueLeakLayer(
        layer=2,
        name="De Motor",
        core_question="Wat maakt je stack traag en wat kost dat?",
        est_monthly_loss_eur=total,
        est_annual_loss_eur=total * 12,
        metric_count=len(metrics),
        leads_to="Stack Rebuild™ — Architectuur",
        key_signals=key_signals[:4],
        metrics=metrics,
        summary=f"{good_count} van {measured} gemeten metrics binnen benchmark" if measured else "Onvoldoende data",
        good_signals=good_signals,
        improvement_signals=improvement_signals,
    )


def _layer3_lekkage(
    performance: Performance | None,
    checkout: CheckoutFlow | None,
    cro_observations: list[CroObservation],
    bench: dict,
) -> RevenueLeakLayer:
    metrics: list[RevenueLeakMetric] = []
    s = bench["scale"]

    # — Checkout-latency —
    checkout_probed = checkout is not None and not checkout.errors_encountered
    friction_count = len(checkout.observed_friction) if checkout and checkout.observed_friction else 0
    no_guest = checkout and checkout.guest_checkout_available is False
    checkout_loss = 0.0
    checkout_signals: list[str] = []
    if checkout_probed:
        if no_guest:
            checkout_loss += min(bench["monthly_revenue"] * 0.08, 1_200.0 * s)
            checkout_signals.append("geen gastbestelling mogelijk — klant móet eerst account aanmaken")
        if friction_count:
            checkout_loss += min(bench["monthly_revenue"] * 0.10, friction_count * 300 * s)
            checkout_signals.append(f"{friction_count} hindernissen in de betaalpagina")
        checkout_loss = _r(checkout_loss)
        checkout_status: MetricStatus = "critical" if (no_guest or friction_count > 2) else ("warning" if friction_count else "good")
        checkout_signal = ", ".join(checkout_signals) if checkout_signals else "geen hindernissen gevonden in de betaalpagina"
    else:
        checkout_loss = 0.0
        checkout_status = "not-measured"
        checkout_signal = "Betaalpagina niet bereikbaar voor outside-only meting"
    metrics.append(RevenueLeakMetric(
        metric="Lekt de betaalpagina klanten?",
        what_we_measure="Wrijving tussen 'in winkelmand' en 'bedankt voor je bestelling' — de duurste plek om klanten te verliezen",
        priority="critical",
        monthly_loss_eur=checkout_loss,
        annual_loss_eur=checkout_loss * 12,
        calculation_note="Elke hindernis in de betaalpagina kost klanten die al wilden kopen — rechtstreeks omzetverlies",
        signal=checkout_signal,
        status=checkout_status,
    ))

    # — CLS —
    cls_val = None
    if performance and performance.mobile:
        cls_val = performance.mobile.cls
    if cls_val is not None and cls_val > 0.1:
        cls_loss = _r(min(bench["monthly_revenue"] * 0.03, (cls_val - 0.1) * 3_000 * s))
        signal = f"Pagina springt regelmatig onder de cursor weg (score {cls_val:.2f}) — bezoekers raken vertrouwen kwijt"
        cls_status: MetricStatus = "critical" if cls_val > 0.25 else "warning"
    elif cls_val is not None:
        cls_loss = 0.0
        signal = f"Pagina blijft netjes staan tijdens het laden (score {cls_val:.2f}) — vertrouwen blijft intact"
        cls_status = "good"
    else:
        cls_loss = 0.0
        signal = None
        cls_status = "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Springt de pagina onder de muis weg?",
        what_we_measure="Knoppen of plaatjes die verspringen terwijl bezoekers proberen te klikken — voelt onbetrouwbaar",
        priority="medium",
        monthly_loss_eur=cls_loss,
        annual_loss_eur=cls_loss * 12,
        calculation_note="Verspringende elementen → misclicks en frustratie → bezoekers geven het op → minder omzet",
        signal=signal,
        status=cls_status,
    ))

    # — Mobile Performance Gap —
    mob_score = None
    desk_score = None
    if performance and performance.lighthouse:
        desk_score = performance.lighthouse.performance
    if performance and performance.mobile:
        mob_lcp = performance.mobile.lcp_ms
        if mob_lcp is not None and desk_score is not None:
            mob_score = max(0, int(desk_score - (mob_lcp - 2500) / 100 * 2)) if mob_lcp > 2500 else desk_score
    gap = (desk_score - mob_score) if (desk_score is not None and mob_score is not None) else 0
    if gap > 20:
        mobile_loss = _r(min(bench["monthly_revenue"] * 0.10, gap * 60 * s))
        signal = f"Mobiel scoort {mob_score}/100, desktop {desk_score}/100 — je beste klantenkanaal werkt het slechtst"
        mobile_status: MetricStatus = "critical" if gap > 40 else "warning"
    elif desk_score is not None:
        mobile_loss = 0.0
        signal = f"Mobiel en desktop scoren vergelijkbaar ({gap}pt verschil) — goed"
        mobile_status = "good"
    else:
        mobile_loss = 0.0
        signal = None
        mobile_status = "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Verliest mobiel veel meer dan desktop?",
        what_we_measure="Het verschil tussen je mobiele en desktopwinkel — 70% van je bezoekers is mobiel, dus elk procent verschil telt dubbel",
        priority="critical",
        monthly_loss_eur=mobile_loss,
        annual_loss_eur=mobile_loss * 12,
        calculation_note="Groot verschil mobiel/desktop → meeste bezoekers op slechtst werkende versie → groot omzetverlies",
        signal=signal,
        status=mobile_status,
    ))

    # — Pagina-specifieke leakage (hoge CRO-bevindingen) —
    high_cro = [o for o in cro_observations if o.severity == "high"]
    if high_cro:
        page_loss = _r(min(bench["monthly_revenue"] * 0.10, len(high_cro) * 350 * s))
        signal = f"{len(high_cro)} dingen op je belangrijkste pagina's die bezoekers ervan weerhouden te bestellen"
        page_status: MetricStatus = "critical" if len(high_cro) >= 3 else "warning"
    else:
        page_loss = 0.0
        signal = "geen grote conversieblokkades gevonden op je pagina's"
        page_status = "good"
    metrics.append(RevenueLeakMetric(
        metric="Welke pagina's lekken het meeste omzet?",
        what_we_measure="Productpagina's, collectiepagina's en winkelmand-pagina's met aantoonbare conversieblokkades",
        priority="high",
        monthly_loss_eur=page_loss,
        annual_loss_eur=page_loss * 12,
        calculation_note="Conversieblokkades op je drukste pagina's → directe omzet die blijft liggen",
        signal=signal,
        status=page_status,
    ))

    total = _r(sum(m.monthly_loss_eur or 0 for m in metrics))
    key_signals = [m.signal for m in metrics if m.signal and (m.monthly_loss_eur or 0) > 0]
    good_signals, improvement_signals = _layer_signals(metrics)
    measured = sum(1 for m in metrics if m.status != "not-measured")
    good_count = sum(1 for m in metrics if m.status == "good")

    return RevenueLeakLayer(
        layer=3,
        name="De Lekkage",
        core_question="Waar lekt conversie weg door technische frictie?",
        est_monthly_loss_eur=total,
        est_annual_loss_eur=total * 12,
        metric_count=len(metrics),
        leads_to="Stack Rebuild™ — Checkout & Mobile",
        key_signals=key_signals[:4],
        metrics=metrics,
        summary=f"{good_count} van {measured} gemeten metrics binnen benchmark" if measured else "Onvoldoende data",
        good_signals=good_signals,
        improvement_signals=improvement_signals,
    )


def _layer4_efficientie(
    performance: Performance | None,
    bench: dict,
) -> RevenueLeakLayer:
    metrics: list[RevenueLeakMetric] = []

    # — Theoretische conversieratio —
    perf_score = performance.lighthouse.performance if (performance and performance.lighthouse) else None
    if perf_score is not None and perf_score < 70:
        est_current_cr = bench["cr"] * (perf_score / 100)
        cr_status: MetricStatus = "critical" if perf_score < 50 else "warning"
    else:
        est_current_cr = bench["cr"]
        cr_status = "good" if perf_score is not None else "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Hoeveel meer bezoekers zouden kopen bij een snelle winkel?",
        what_we_measure="Hoeveel % van je bezoekers nu koopt vs hoeveel er zouden kopen als je winkel even snel was als de concurrentie",
        priority="high",
        monthly_loss_eur=0.0,
        annual_loss_eur=0.0,
        calculation_note="Verschil in aankoopkans tussen jouw winkel en een snelle winkel → directe groeimogelijkheid",
        signal=f"Nu koopt {est_current_cr * 100:.1f}% van je bezoekers — bij benchmark-snelheid zou dat {bench['cr'] * 100:.1f}% zijn" if perf_score else "Geen data beschikbaar",
        status=cr_status,
    ))

    # — Revenue Gap —
    cr_delta = max(0.0, bench["cr"] - est_current_cr)
    rev_gap = _r(bench["monthly_sessions"] * cr_delta * bench["aov"])
    rev_status: MetricStatus = "critical" if rev_gap > bench["monthly_revenue"] * 0.10 else ("warning" if rev_gap > 0 else "good")
    metrics.append(RevenueLeakMetric(
        metric="Hoeveel omzet laat je liggen per maand?",
        what_we_measure="Het verschil tussen wat je nu verdient en wat je zou verdienen met dezelfde bezoekers maar een snelle winkel",
        priority="critical",
        monthly_loss_eur=rev_gap,
        annual_loss_eur=rev_gap * 12,
        calculation_note=f"~{bench['monthly_sessions']:,.0f} bezoekers × verschil in aankoopkans × €{bench['aov']:.0f} gemiddelde bestelling",
        signal=f"€{rev_gap:,.0f}/mnd extra omzet ligt op tafel — dezelfde bezoekers, betere winkel" if perf_score else "Onvoldoende data om te berekenen",
        status=rev_status if perf_score else "not-measured",
    ))

    # — CPA bij optimale performance —
    haalbare_conversies = bench["monthly_sessions"] * bench["cr"]
    huidige_conversies = bench["monthly_sessions"] * est_current_cr
    if huidige_conversies > 0 and haalbare_conversies > huidige_conversies:
        cpa_besparing = _r(bench["monthly_ad_spend"] / huidige_conversies - bench["monthly_ad_spend"] / haalbare_conversies)
        cpa_total = _r(cpa_besparing * huidige_conversies)
        signal = f"Een nieuwe klant kost nu €{bench['monthly_ad_spend'] / huidige_conversies:.0f} — bij een snelle winkel €{bench['monthly_ad_spend'] / haalbare_conversies:.0f} (zelfde advertentiebudget)"
        cpa_status: MetricStatus = "warning" if cpa_total > 0 else "good"
    else:
        cpa_total = 0.0
        signal = "Werfkosten al optimaal bij huidige prestaties"
        cpa_status = "good" if perf_score is not None else "not-measured"
    metrics.append(RevenueLeakMetric(
        metric="Hoeveel goedkoper wordt elke nieuwe klant?",
        what_we_measure="Wat het je nu kost om een nieuwe klant te werven vs wat dat zou zijn als de winkel niet lekt",
        priority="high",
        monthly_loss_eur=cpa_total,
        annual_loss_eur=cpa_total * 12,
        calculation_note="Minder weglopers → meer aankopen per euro advertentiebudget → lagere werfkosten per klant",
        signal=signal,
        status=cpa_status,
    ))

    # — ROAS-uplift —
    haalbare_omzet = bench["monthly_sessions"] * bench["cr"] * bench["aov"]
    huidige_omzet = bench["monthly_sessions"] * est_current_cr * bench["aov"]
    roas_delta = haalbare_omzet - huidige_omzet
    roas_uplift = _r(min(bench["monthly_revenue"] * 0.10, roas_delta * 0.5))
    roas_status: MetricStatus = "warning" if roas_uplift > 0 else ("good" if perf_score is not None else "not-measured")
    metrics.append(RevenueLeakMetric(
        metric="Hoeveel meer haal je uit hetzelfde advertentiebudget?",
        what_we_measure="Hoeveel extra omzet je advertentiebudget oplevert als bezoekers eenmaal binnen wél converteren",
        priority="high",
        monthly_loss_eur=roas_uplift,
        annual_loss_eur=roas_uplift * 12,
        calculation_note="Meer bezoekers die kopen bij zelfde ad spend → direct hogere omzet per advertentie-euro",
        signal=f"+€{roas_uplift:,.0f}/mnd extra omzet uit hetzelfde advertentiebudget — alleen al door de winkel sneller te maken" if roas_uplift > 0 else "Advertentiebudget al efficiënt ingezet",
        status=roas_status,
    ))

    total = _r(sum(m.monthly_loss_eur or 0 for m in metrics))
    key_signals = [m.signal for m in metrics if m.signal and (m.monthly_loss_eur or 0) > 0]
    good_signals, improvement_signals = _layer_signals(metrics)
    measured = sum(1 for m in metrics if m.status != "not-measured")
    good_count = sum(1 for m in metrics if m.status == "good")

    return RevenueLeakLayer(
        layer=4,
        name="De Efficiëntie",
        core_question="Hoeveel meer omzet zit er in bestaande traffic?",
        est_monthly_loss_eur=total,
        est_annual_loss_eur=total * 12,
        metric_count=len(metrics),
        leads_to="Performance Layer™",
        key_signals=key_signals[:4],
        metrics=metrics,
        summary=f"{good_count} van {measured} gemeten metrics binnen benchmark" if measured else "Onvoldoende data",
        good_signals=good_signals,
        improvement_signals=improvement_signals,
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

    # — Storefront API Responsiveness —
    sub_scores.append(50.0)
    metrics.append(RevenueLeakMetric(
        metric="Hoe snel haalt je winkel productdata op?",
        what_we_measure="Hoe vlot je productpagina's data ophalen — bepaalt of bezoekers blijven wachten of weglopen",
        priority="medium",
        monthly_loss_eur=None,
        annual_loss_eur=None,
        calculation_note="Trage data-ophaling → bezoekers wachten langer voor ze producten zien → ze haken af",
        signal="Vereist diepere meting (niet zichtbaar bij deze scan van buitenaf)",
        status="not-measured",
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
    mob_lcp = performance.mobile.lcp_ms if (performance and performance.mobile) else None
    desk_score = perf_score
    mob_score_est = max(0, int(desk_score - (mob_lcp - 2500) / 100 * 2)) if (mob_lcp and mob_lcp > 2500 and desk_score) else desk_score
    mob_gap = (desk_score - mob_score_est) if (desk_score and mob_score_est) else 0

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
            kpi="Marktaandeel daalt bij vergelijkbaar product",
            what_ceo_sees="Concurrenten met een vergelijkbaar product groeien sneller.",
            benchmark=None,
            alarm_signal="Marktaandeel daalt >2% YoY",
            real_meaning="Bij vergelijkbare producten wint de store met de beste koopervaring. Snelheid wordt de differentiator.",
            tradual_pitch="Jullie product is niet het probleem. Jullie winkelervaring is het probleem. De klant gaat naar de winkel waar het makkelijker en sneller is.",
            tradual_solution="Stack Rebuild™ — volledige commerce-infrastructuur",
            triggered=False,
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
            kpi="Shopify app-kosten stijgen maar resultaat niet",
            what_ceo_sees="Elke maand meer apps, meer subscriptions, maar geen meetbaar effect op omzet.",
            benchmark=None,
            alarm_signal=">15 apps geïnstalleerd",
            real_meaning="Elke app voegt gewicht toe aan de store. Je betaalt dubbel: de subscription + het conversieverlies dat de app veroorzaakt.",
            tradual_pitch="Jullie betalen per maand aan apps die jullie store vertragen. Sommige kosten meer aan conversieverlies dan ze opleveren aan functionaliteit.",
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
            category="Omzet & Groei",
            kpi="Gemiddelde orderwaarde daalt",
            what_ceo_sees="Klanten kopen steeds minder per bestelling, terwijl het assortiment niet kleiner is geworden.",
            benchmark=None,
            alarm_signal="AOV daalt >5% jaar-op-jaar",
            real_meaning="Een dalende gemiddelde orderwaarde bij gelijk aanbod duidt op cross-sell en upsell die niet werken — of een productpagina die bezoekers alleen naar het goedkoopste artikel stuurt.",
            tradual_pitch="Jullie laten omzet liggen bij elke bestelling. Een klant die al koopt is de makkelijkste klant om iets extra's aan te verkopen — maar de winkel doet er niets mee.",
            tradual_solution="CRO Sprint™ — productpagina & winkelmand",
            triggered=False,
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
) -> RevenueLeakReport:
    bench = _benchmarks(annual_revenue_eur, traffic)

    layers = [
        _layer1_deur(performance, ad_traffic, bench),
        _layer2_motor(performance, third_party, bench),
        _layer3_lekkage(performance, checkout, cro_observations, bench),
        _layer4_efficientie(performance, bench),
        _layer5_toekomst(rich_results, product_feeds, accessibility),
    ]

    monthly_total = sum(
        (layer.est_monthly_loss_eur or 0) for layer in layers
        if layer.est_monthly_loss_eur is not None
    )
    monthly_total = _r(monthly_total)
    annual_total = _r(monthly_total * 12)

    direct_monthly = _r(sum(
        (l.est_monthly_loss_eur or 0) for l in layers if l.layer in (1, 2, 3)
    ))
    direct_annual = _r(direct_monthly * 12)
    efficiency_monthly = _r(next(
        ((l.est_monthly_loss_eur or 0) for l in layers if l.layer == 4), 0.0
    ))
    efficiency_annual = _r(efficiency_monthly * 12)

    roi: RoiCalculation | None = None
    if monthly_total > 0:
        roi = RoiCalculation(
            monthly_leak_eur=monthly_total,
            annual_leak_eur=annual_total,
            stack_rebuild_cost_eur=_STACK_REBUILD_COST,
            payback_months=round(_STACK_REBUILD_COST / monthly_total, 1),
            year_one_net_return_eur=max(0.0, annual_total - _STACK_REBUILD_COST),
        )

    ceo_triggers = _detect_ceo_triggers(
        performance, ad_traffic, third_party, checkout, rich_results, product_feeds
    )

    revenue_source = "opgegeven door operator" if annual_revenue_eur else "fallback benchmark"
    is_measured = bench["data_source"] == "measured"
    if is_measured and traffic:
        traffic_note = (
            f"Gemeten via SE Ranking: {traffic.monthly_organic_sessions:,} organische + "
            f"{traffic.monthly_paid_sessions:,} betaalde sessies/mnd ({bench['monthly_sessions']:,.0f} totaal). "
            f"CVR {bench['cr'] * 100:.2f}% afgeleid uit gemeten traffic."
        )
    else:
        traffic_note = f"~{bench['monthly_sessions']:,.0f} sessies/mnd (afgeleid), {bench['cr'] * 100:.1f}% CVR (benchmark)."

    return RevenueLeakReport(
        layers=layers,
        total_monthly_loss_eur=monthly_total if monthly_total > 0 else 0.0,
        total_annual_loss_eur=annual_total if annual_total > 0 else 0.0,
        direct_monthly_loss_eur=direct_monthly if direct_monthly > 0 else 0.0,
        direct_annual_loss_eur=direct_annual if direct_annual > 0 else 0.0,
        efficiency_monthly_uplift_eur=efficiency_monthly if efficiency_monthly > 0 else 0.0,
        efficiency_annual_uplift_eur=efficiency_annual if efficiency_annual > 0 else 0.0,
        methodology_note=(
            f"{'Gemeten' if is_measured else 'Heuristische'} schatting. "
            f"Omzet: €{bench['monthly_revenue']:,.0f}/mnd ({revenue_source}). "
            f"{traffic_note} "
            f"€{bench['aov']:.0f} AOV, €{bench['monthly_ad_spend']:,.0f}/mnd ad spend. "
            "Gebaseerd op publiek meetbare signalen. Gebruik als indicatie, niet als definitieve audit-uitkomst."
        ),
        ceo_triggers=ceo_triggers,
        roi=roi,
        data_source="measured" if is_measured else "heuristic",
    )

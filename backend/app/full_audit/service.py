import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.funnel.service import walk_funnel
from app.agents.verifier.service import admin_client_for, run_verifier
from app.analysis.scraper import scrape_store
from app.database import AsyncSessionLocal
from app.full_audit.analyzers.accessibility import make_accessibility_report
from app.full_audit.analyzers.bloat import build_bloat_list
from app.full_audit.analyzers.checkout import probe_checkout
from app.full_audit.analyzers.competitor_benchmark import fetch_competitor_benchmark
from app.full_audit.analyzers.compliance_eu import analyze_eu_compliance
from app.full_audit.analyzers.cost import build_cost_analysis
from app.full_audit.analyzers.cro import make_cro_observations
from app.full_audit.analyzers.dns_email import analyze_dns_email
from app.full_audit.analyzers.domain_health import analyze_domain_health
from app.full_audit.analyzers.marketplaces import detect_marketplaces
from app.full_audit.analyzers.multi_region import detect_multi_region
from app.full_audit.analyzers.owned_channels import detect_owned_channels
from app.full_audit.analyzers.performance import analyze_performance, lcp_source_caveat, worst_mobile_lcp
from app.full_audit.analyzers.platform import detect_platform
from app.full_audit.analyzers.product_feeds import analyze_product_feeds
from app.full_audit.analyzers.retention import detect_retention
from app.full_audit.analyzers.returns import detect_returns
from app.full_audit.analyzers.rich_results import analyze_rich_results
from app.full_audit.analyzers.ad_traffic import calculate_ad_traffic_impact
from app.full_audit.analyzers.ai_analysis import enrich_top_summary, run_ai_analysis
from app.full_audit.analyzers.revenue_leak import calculate_revenue_leak
from app.full_audit.analyzers.seranking import fetch_traffic_estimates
from app.full_audit.sanity_export import build_sanity_export
from app.full_audit.analyzers.security import check_security
from app.full_audit.analyzers.seo import audit_seo
from app.full_audit.analyzers.server_side_tracking import analyze_server_side_tracking
from app.full_audit.analyzers.shipping import detect_shipping
from app.full_audit.analyzers.shopify_apps import detect_shopify_apps
from app.full_audit.analyzers.shopify_catalog import analyze_shopify_catalog
from app.full_audit.analyzers.site_search import detect_site_search
from app.full_audit.analyzers.third_party import apply_psi_third_party_measurements, scan_third_party
from app.full_audit.analyzers.tracking import detect_tracking
from app.full_audit.models import FullAudit
from app.full_audit.schemas import (
    BloatItem,
    CostAnalysis,
    DetectedStack,
    DnsEmailHealth,
    FullAuditData,
    Performance,
    PlatformArchitecture,
    RevenueLeakReport,
    RichResultsHealth,
    ThirdPartyScripts,
    TrackingDataQuality,
)

logger = logging.getLogger(__name__)


def _build_thesis(signal: dict, monthly_leak_eur: float | None) -> str:
    # `monthly_leak_eur` is only passed in when the winning signal itself has a priced
    # euro contribution (see _synthesize's impact ranking) — a signal with €0 measured
    # impact must never borrow the report-wide total, or the sentence claims credit for
    # money it didn't cause.
    leak_clause = f" Geschatte lekkage: €{monthly_leak_eur:,.0f} per maand." if monthly_leak_eur else ""
    kind = signal["kind"]
    lcp_caveat = signal.get("lcp_caveat", "")
    if kind == "lcp_critical":
        return (
            f"De mobiele pagina wordt pas na {signal['lcp_s']:.1f} seconden goed zichtbaar{lcp_caveat}. "
            f"Daardoor haken bezoekers af voordat ze iets kunnen kopen.{leak_clause}"
        )
    if kind == "lcp_warning":
        return (
            f"De mobiele pagina is met {signal['lcp_s']:.1f} seconden traag zichtbaar{lcp_caveat}. "
            f"Dat kost vooral mobiele bezoekers en remt de verkoop.{leak_clause}"
        )
    if kind == "inp_warning":
        return (
            f"De pagina reageert pas na {signal['tbt_ms']:.0f}ms op een klik. "
            f"Dat voelt traag en onbetrouwbaar, en kost bezoekers die al aan het kopen waren.{leak_clause}"
        )
    if kind == "third_party_blocking":
        return (
            f"Externe scripts houden de pagina ongeveer {signal['blocking_ms']:.0f} ms tegen. "
            f"Daardoor voelt de site trager en verlies je kopers voordat ze kunnen bestellen.{leak_clause}"
        )
    if kind == "attribution_loss":
        return (
            f"Ongeveer {signal['pct']:.0f}% van je bestellingen komt waarschijnlijk niet goed aan in Meta of Google. "
            f"Daardoor leren je advertenties van onvolledige data.{leak_clause}"
        )
    if kind == "pixel_gap":
        return (
            f"De advertentiemeting is niet compleet. Meta en Google missen daardoor verkoopsignalen "
            f"en sturen campagnes op te weinig informatie.{leak_clause}"
        )
    if kind == "dmarc":
        return (
            f"Je e-mailbeveiliging staat te zwak ingesteld. Daardoor is de kans groter dat nieuwsbrieven "
            f"of ordermails in spam belanden.{leak_clause}"
        )
    if kind == "spf":
        return (
            f"Je afzenderinstellingen voor e-mail zijn niet op orde. Daardoor kunnen nieuwsbrieven "
            f"en ordermails sneller in spam belanden.{leak_clause}"
        )
    return f"De scan wijst op concrete plekken waar omzet blijft liggen en herstel meetbaar voordeel kan opleveren.{leak_clause}"


# Maps a risk signal's "kind" to the revenue_leak finding_id whose priced euro impact
# should rank it. Signal kinds absent here (third-party blocking/domains, attribution
# loss, pixel gap, dmarc, spf) have no priced finding anywhere in the report — they
# rank at €0, same as a risk that was checked and found fine, rather than being able
# to out-rank a signal the report actually put a number on.
_SIGNAL_FINDING_ID = {
    "lcp_critical": "perf.lcp_mobile",
    "lcp_warning": "perf.lcp_mobile",
    "inp_warning": "perf.inp_mobile",
}


def _finding_impact_eur(revenue_leak: RevenueLeakReport | None) -> dict:
    """finding_id -> priced monthly midpoint, read straight from the Revenue Leak
    layers so the headline ranks on the exact same euros that section reports below
    it — not a second, independent scoring model that could disagree with it."""
    impact: dict[str, float] = {}
    if revenue_leak is None:
        return impact
    for layer in revenue_leak.layers:
        for m in layer.metrics:
            if m.finding_id and m.monthly_loss_eur:
                impact[m.finding_id] = m.monthly_loss_eur
    return impact


def _synthesize(
    performance: Performance | None,
    third_party: ThirdPartyScripts | None,
    tracking: TrackingDataQuality | None,
    cost: CostAnalysis | None,
    platform: PlatformArchitecture | None,
    dns_email: DnsEmailHealth | None,
    rich_results: RichResultsHealth | None,
    store_url: str,
    revenue_leak_monthly_eur: float | None = None,
    revenue_leak: RevenueLeakReport | None = None,
) -> dict:
    # Each entry is {"text": str, "signal": dict | None, "impact_eur": float}. Text and
    # signal used to live in two parallel lists (`risks`/`risk_signals`) that could
    # silently drift out of sync — third_party_domains only ever appended to `risks` —
    # so "biggest risk" and "core thesis" could describe two different findings. One
    # list of entries makes that structurally impossible.
    risk_entries: list[dict] = []
    opportunities: list[str] = []
    lift_pct: float | None = None
    impact_map = _finding_impact_eur(revenue_leak)

    def _impact(signal: dict | None) -> float:
        if not signal:
            return 0.0
        finding_id = _SIGNAL_FINDING_ID.get(signal["kind"])
        return impact_map.get(finding_id, 0.0) if finding_id else 0.0

    if performance:
        lcp_ms, lcp_source = worst_mobile_lcp(performance)
        lcp_caveat = lcp_source_caveat(performance, lcp_source)
        if lcp_ms and lcp_ms > 4000:
            risk_entries.append({
                "text": f"Mobiele bezoekers zien de belangrijkste content pas na {lcp_ms / 1000:.1f} seconden{lcp_caveat}",
                "signal": {"kind": "lcp_critical", "lcp_s": lcp_ms / 1000, "lcp_caveat": lcp_caveat},
            })
        elif lcp_ms and lcp_ms > 2500:
            risk_entries.append({
                "text": f"De mobiele pagina is pas na {lcp_ms / 1000:.1f} seconden goed zichtbaar{lcp_caveat}",
                "signal": {"kind": "lcp_warning", "lcp_s": lcp_ms / 1000, "lcp_caveat": lcp_caveat},
            })
        perf_score = performance.lighthouse.performance if performance.lighthouse else None
        if perf_score is not None:
            lift_pct = float(max(0, min(60, int((100 - perf_score) * 0.6))))

        tbt_ms = performance.tbt_ms
        if tbt_ms is not None and tbt_ms > 200:
            risk_entries.append({
                "text": f"De pagina reageert pas na {tbt_ms:.0f}ms op een klik — dat voelt traag en onbetrouwbaar",
                "signal": {"kind": "inp_warning", "tbt_ms": tbt_ms},
            })

    if third_party:
        if third_party.total_third_party_blocking_ms and third_party.total_third_party_blocking_ms > 500:
            risk_entries.append({
                "text": f"Externe scripts houden de pagina {third_party.total_third_party_blocking_ms:.0f} ms tegen bij het laden",
                "signal": {"kind": "third_party_blocking", "blocking_ms": third_party.total_third_party_blocking_ms},
            })
        if third_party.total_third_party_domains and third_party.total_third_party_domains > 15:
            risk_entries.append({
                "text": f"{third_party.total_third_party_domains} externe domeinen laden mee bij het openen van de pagina",
                "signal": {"kind": "third_party_domains", "domains": third_party.total_third_party_domains},
            })

    if tracking:
        if tracking.est_attribution_loss_percent and tracking.est_attribution_loss_percent > 25:
            risk_entries.append({
                "text": f"Ongeveer {tracking.est_attribution_loss_percent:.0f}% van je conversies komt waarschijnlijk niet goed aan in advertentieplatformen",
                "signal": {"kind": "attribution_loss", "pct": tracking.est_attribution_loss_percent},
            })
        if tracking.pixels_health in ("partial", "missing"):
            risk_entries.append({
                "text": "Meta en Google missen waarschijnlijk conversiedata door een onvolledige meetsetup",
                "signal": {"kind": "pixel_gap"},
            })

    if dns_email:
        if dns_email.dmarc_policy in ("missing", "none"):
            risk_entries.append({
                "text": "E-mailbeveiliging is zwak ingesteld, waardoor mail vaker in spam kan belanden",
                "signal": {"kind": "dmarc", "policy": dns_email.dmarc_policy},
            })
        if dns_email.spf_status and dns_email.spf_status != "valid":
            risk_entries.append({
                "text": "Afzendercontrole voor e-mail is niet goed ingesteld",
                "signal": {"kind": "spf", "status": dns_email.spf_status},
            })

    if rich_results and not rich_results.has_aggregate_rating:
        opportunities.append("Je reviews worden nog niet als sterren in Google getoond, waardoor je zoekresultaat minder snel opvalt")

    if cost and cost.est_monthly_savings_eur and cost.est_monthly_savings_eur > 100:
        opportunities.append(f"€{cost.est_monthly_savings_eur:.0f} per maand besparen door overbodige tools en scripts op te ruimen")

    if platform and platform.detected_platform:
        if platform.architecture_type == "monolith" and platform.detected_platform not in ("Shopify",):
            opportunities.append("Een modernere of beter geoptimaliseerde setup kan de site structureel sneller maken")

    # Rank on priced euro impact, not append order — a DMARC finding with €0 anywhere
    # in the report can no longer beat an LCP finding the Revenue Leak section put
    # thousands of euros on. Stable sort: ties keep their original (severity-authored)
    # order, so a report where nothing is priced behaves exactly as before.
    for entry in risk_entries:
        entry["impact_eur"] = _impact(entry["signal"])
    risk_entries.sort(key=lambda e: e["impact_eur"], reverse=True)

    biggest_risk = risk_entries[0]["text"] if risk_entries else None
    biggest_opportunity = opportunities[0] if opportunities else None

    platform_name = platform.detected_platform if platform and platform.detected_platform else "onbekend platform"
    core_thesis: str | None = None
    if risk_entries:
        top = risk_entries[0]
        # Only attach the report-wide leak figure when the winning signal itself has a
        # priced contribution to it — otherwise the sentence claims credit for money a
        # different finding (not this one) actually accounts for.
        thesis_leak = revenue_leak_monthly_eur if top["impact_eur"] > 0 else None
        core_thesis = _build_thesis(top["signal"], thesis_leak)

    n_issues = len(risk_entries)
    n_opp = len(opportunities)
    audit_summary = (
        f"Geautomatiseerde outside-only scan van {platform_name} store ({store_url}). "
        f"{n_issues} technische risico{'s' if n_issues != 1 else ''} en {n_opp} kans{'en' if n_opp != 1 else ''} geïdentificeerd."
    )

    return {
        "core_thesis": core_thesis,
        "biggest_tech_risk": biggest_risk,
        "biggest_tech_opportunity": biggest_opportunity,
        "est_performance_lift_percent": lift_pct,
        "audit_summary": audit_summary,
        "methodology_note": (
            "Geautomatiseerde outside-only scan zonder admin-toegang. Bronnen: HTTP-headers en "
            "DOM-analyse van publieke pagina's, DNS-records, Google PageSpeed Insights (CrUX-velddata "
            "waar beschikbaar, anders labmeting), een catalogus van third-party scripts, een "
            "checkout-probe (bij Shopify: één product in een testwinkelwagen, geen bestelling), "
            "verkeersschattingen van SE Ranking, concurrentie-data van DataForSEO, en "
            "Claude (Anthropic) voor de tekstuele analyse."
        ),
    }


# Audits run as in-process background tasks (one uvicorn worker). Kept here so an
# operator can stop one: `cancel_running_audit` cancels the task, which also tears down
# whatever it was awaiting (HTTP calls, PageSpeed, the funnel agent's browser).
_RUNNING: dict[uuid.UUID, asyncio.Task] = {}
_CANCEL_REQUESTED: set[uuid.UUID] = set()


def cancel_running_audit(audit_id: uuid.UUID) -> bool:
    """Cancel the audit's task if this process is running it. False when it isn't —
    e.g. it never started, or it was orphaned by a restart; the status change the
    caller makes is then all that's needed (and the pipeline's own check before
    persisting covers any other process)."""
    task = _RUNNING.get(audit_id)
    if task is None or task.done():
        return False
    _CANCEL_REQUESTED.add(audit_id)
    task.cancel()
    return True


async def run_full_audit(audit_id: uuid.UUID) -> None:
    task = asyncio.current_task()
    if task is not None:
        _RUNNING[audit_id] = task
    try:
        await _run_full_audit(audit_id)
    except asyncio.CancelledError:
        if audit_id not in _CANCEL_REQUESTED:
            raise  # server shutdown etc. — not ours to swallow
        logger.info("Full audit %s stopped by operator", audit_id)
    finally:
        _RUNNING.pop(audit_id, None)
        _CANCEL_REQUESTED.discard(audit_id)


async def _run_full_audit(audit_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(FullAudit).where(FullAudit.id == audit_id))
            audit = result.scalar_one()
            if audit.status == "cancelled":  # stopped while still queued
                return
            audit.status = "processing"
            await db.commit()
            store_url = audit.store_url

            # 1. Scrape
            scrape_result = await scrape_store(store_url)
            pages = scrape_result["pages"]
            if not pages:
                if scrape_result.get("blocked_reason"):
                    raise RuntimeError(
                        f"De winkel blokkeerde de scan ({scrape_result['blocked_reason']}): we kregen "
                        "een foutpagina of botbeveiliging terug in plaats van de homepage."
                    )
                raise RuntimeError(f"Could not scrape {store_url} — site unreachable or blocked")

            # 2. Run analyzers in parallel — return_exceptions=True so one failure doesn't abort
            results = await asyncio.gather(
                detect_platform(pages),               # 0
                analyze_performance(store_url, pages), # 1
                scan_third_party(pages),               # 2
                detect_tracking(pages),                # 3
                probe_checkout(store_url),             # 4
                detect_owned_channels(store_url, pages), # 5
                audit_seo(pages),                      # 6
                check_security(store_url, pages),      # 7
                analyze_dns_email(store_url),          # 8
                analyze_domain_health(store_url, pages), # 9
                analyze_rich_results(pages),           # 10
                analyze_server_side_tracking(store_url, pages), # 11
                analyze_product_feeds(store_url, pages), # 12
                detect_site_search(pages),             # 13
                detect_shipping(pages),                # 14
                detect_returns(pages),                 # 15
                detect_multi_region(store_url, pages), # 16
                detect_marketplaces(pages),            # 17
                analyze_shopify_catalog(store_url, pages), # 18
                detect_shopify_apps(pages),            # 19
                detect_retention(pages),               # 20
                analyze_eu_compliance(pages),           # 21
                walk_funnel(audit_id, store_url, pages), # 22 — funnel agent (mobile browser)
                return_exceptions=True,
            )

            # Everything below degrades instead of failing the audit: a broken analyzer or
            # rollup becomes None plus a line in `pipeline_warnings`, so the operator
            # sees what's missing instead of losing the whole (paid-for) run.
            pipeline_warnings: list[str] = []

            def _record(step: str, exc: BaseException) -> None:
                logger.warning("Full audit step %s failed for %s: %s", step, audit_id, exc)
                pipeline_warnings.append(f"{step}: {type(exc).__name__}: {exc}"[:300])

            if scrape_result.get("locale_redirect"):
                pipeline_warnings.append(
                    f"scrape: de winkel stuurde ons naar een andere taalversie ({scrape_result['locale_redirect']}); "
                    "bevindingen gelden voor die versie."
                )

            analyzer_names = [
                "platform", "performance", "third_party", "tracking", "checkout", "owned_channels",
                "seo", "security", "dns_email", "domain_health", "rich_results",
                "server_side_tracking", "product_feeds", "site_search", "shipping", "returns",
                "multi_region", "marketplaces", "shopify_catalog", "shopify_apps", "retention",
                "eu_compliance", "funnel_walk",
            ]

            def _safe(index: int, default=None):
                val = results[index]
                if isinstance(val, BaseException):
                    _record(analyzer_names[index], val)
                    return default
                return val

            def _step(step: str, fn, *args, default=None, **kwargs):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    _record(step, exc)
                    return default

            async def _astep(step: str, coro, default=None):
                try:
                    return await coro
                except Exception as exc:
                    _record(step, exc)
                    return default

            platform = _safe(0)
            performance_result = _safe(1)
            if performance_result is not None:
                performance, psi_third_party_summary = performance_result
            else:
                performance, psi_third_party_summary = None, {}
            third_party = _safe(2)
            third_party = _step(
                "third_party_psi_overlay", apply_psi_third_party_measurements,
                third_party, psi_third_party_summary, default=third_party,
            )
            tracking = _safe(3)
            checkout = _safe(4)
            owned = _safe(5)
            seo = _safe(6)
            security = _safe(7)
            dns_email = _safe(8)
            domain_health = _safe(9)
            rich_results = _safe(10)
            server_side_tracking = _safe(11)
            product_feeds = _safe(12)
            site_search = _safe(13)
            shipping = _safe(14)
            returns = _safe(15)
            multi_region = _safe(16)
            marketplaces = _safe(17)
            shopify_catalog = _safe(18)
            shopify_apps = _safe(19)
            retention = _safe(20)
            eu_compliance = _safe(21)
            funnel_walk = _safe(22)
            if funnel_walk is not None and funnel_walk.status == "failed":
                pipeline_warnings.extend(f"funnel_walk: {w}"[:300] for w in funnel_walk.warnings)

            # 3. Rollups (synchronous, depend on parallel results)
            cost = _step("cost_analysis", build_cost_analysis, third_party, platform)
            bloat = _step("bloat", build_bloat_list, third_party, cost, default=[])
            cro_obs = _step("cro_observations", make_cro_observations, pages, performance, checkout, rich_results, default=[])
            accessibility = _step("accessibility", make_accessibility_report, pages, performance)
            annual_rev = audit.estimated_annual_revenue_eur

            async def _load_seranking():
                # SE Ranking traffic lookup — cached per audit row (30-day TTL)
                from app.full_audit.schemas import SeRankingTraffic  # local import avoids circular
                _cache_age_days = None
                if audit.seranking_fetched_at:
                    _cache_age_days = (datetime.now(UTC) - audit.seranking_fetched_at).days
                if audit.seranking_traffic_json and _cache_age_days is not None and _cache_age_days < 30:
                    seranking_traffic = SeRankingTraffic(**audit.seranking_traffic_json)
                    logger.info("SE Ranking cache hit for %s (%d days old)", store_url, _cache_age_days)
                else:
                    seranking_traffic = await fetch_traffic_estimates(store_url)
                    if seranking_traffic is not None:
                        async with AsyncSessionLocal() as _db:
                            _row = await _db.get(FullAudit, audit.id)
                            if _row:
                                _row.seranking_traffic_json = seranking_traffic.model_dump(exclude={"raw_response"})
                                _row.seranking_fetched_at = datetime.now(UTC)
                                await _db.commit()
                return seranking_traffic

            async def _load_competitor_benchmark():
                # Competitor benchmark via DataForSEO — cached per audit row (30-day TTL).
                # Real per-call cost, so this is cached even more conservatively than SE Ranking.
                from app.full_audit.schemas import CompetitorBenchmarkReport  # local import avoids circular
                _comp_cache_age_days = None
                if audit.competitor_benchmark_fetched_at:
                    _comp_cache_age_days = (datetime.now(UTC) - audit.competitor_benchmark_fetched_at).days
                if audit.competitor_benchmark_json and _comp_cache_age_days is not None and _comp_cache_age_days < 30:
                    competitor_benchmark = CompetitorBenchmarkReport(**audit.competitor_benchmark_json)
                    logger.info("Competitor benchmark cache hit for %s (%d days old)", store_url, _comp_cache_age_days)
                else:
                    competitor_benchmark = await fetch_competitor_benchmark(store_url, pages)
                    if competitor_benchmark is not None:
                        async with AsyncSessionLocal() as _db:
                            _row = await _db.get(FullAudit, audit.id)
                            if _row:
                                _row.competitor_benchmark_json = competitor_benchmark.model_dump(mode="json")
                                _row.competitor_benchmark_fetched_at = datetime.now(UTC)
                                await _db.commit()
                return competitor_benchmark

            seranking_traffic = await _astep("seranking", _load_seranking())
            competitor_benchmark = await _astep("competitor_benchmark", _load_competitor_benchmark())

            ad_traffic_impact = _step(
                "ad_traffic_impact", calculate_ad_traffic_impact,
                performance, third_party, tracking, server_side_tracking,
                annual_revenue_eur=annual_rev,
                traffic=seranking_traffic,
                aov_override=audit.aov_eur,
                sessions_override=audit.monthly_sessions,
                cr_override_pct=audit.conversion_rate_pct,
                ad_spend_override=audit.monthly_ad_spend_eur,
                mobile_share_override_pct=audit.mobile_share_pct,
                mobile_cr_override_pct=audit.mobile_conversion_rate_pct,
            )
            def _leak(verdicts: dict[str, str] | None = None):
                return calculate_revenue_leak(
                    performance, third_party, checkout,
                    cro_obs or [], rich_results, product_feeds, accessibility,
                    ad_traffic_impact,
                    annual_revenue_eur=annual_rev,
                    traffic=seranking_traffic,
                    aov_override=audit.aov_eur,
                    sessions_override=audit.monthly_sessions,
                    cr_override_pct=audit.conversion_rate_pct,
                    ad_spend_override=audit.monthly_ad_spend_eur,
                    mobile_share_override_pct=audit.mobile_share_pct,
                    mobile_cr_override_pct=audit.mobile_conversion_rate_pct,
                    cost=cost,
                    shipping=shipping,
                    catalog=shopify_catalog,
                    owned=owned,
                    verdicts=verdicts,
                    funnel_walk=funnel_walk,
                )

            revenue_leak = _step("revenue_leak", _leak)

            # 4. Top-level synthesis
            # Use the low bound for the headline claim in the core thesis — a sales
            # claim should be the conservative end of the range, not the midpoint.
            def _synthesis(leak: RevenueLeakReport | None) -> dict:
                leak_for_thesis = (
                    (leak.total_monthly_loss_eur_low if leak.total_monthly_loss_eur_low is not None else leak.total_monthly_loss_eur)
                    if leak else None
                )
                return _synthesize(
                    performance, third_party, tracking, cost, platform, dns_email, rich_results, store_url,
                    revenue_leak_monthly_eur=leak_for_thesis,
                    revenue_leak=leak,
                )

            synthesis = _synthesis(revenue_leak)

            # 5. Build full data model
            detected_stack = DetectedStack(
                site_search=site_search,
                shipping=shipping,
                returns=returns,
                multi_region=multi_region,
                marketplaces=marketplaces,
            )
            audit_data = FullAuditData(
                store_url=store_url,
                company_name=audit.company_name,
                scan_level=audit.scan_level,  # type: ignore[arg-type]
                industry=audit.industry,
                contact_email=audit.contact_email,
                contact_person=audit.contact_person,
                estimated_annual_revenue_eur=audit.estimated_annual_revenue_eur,
                aov_eur=audit.aov_eur,
                monthly_sessions=audit.monthly_sessions,
                conversion_rate_pct=audit.conversion_rate_pct,
                monthly_ad_spend_eur=audit.monthly_ad_spend_eur,
                mobile_share_pct=audit.mobile_share_pct,
                mobile_conversion_rate_pct=audit.mobile_conversion_rate_pct,
                platform_architecture=platform,
                performance=performance,
                third_party_scripts=third_party,
                tracking_data_quality=tracking,
                checkout_flow=checkout,
                owned_channels=owned,
                seo_health=seo,
                security_compliance=security,
                cost_analysis=cost,
                cro_observations=cro_obs or [],
                bloat_what_must_go=bloat or [],
                dns_email=dns_email,
                domain_health=domain_health,
                rich_results=rich_results,
                server_side_tracking=server_side_tracking,
                accessibility=accessibility,
                product_feeds=product_feeds,
                detected_stack=detected_stack,
                shopify_catalog=shopify_catalog,
                shopify_apps=shopify_apps,
                retention=retention,
                eu_compliance=eu_compliance,
                ad_traffic_impact=ad_traffic_impact,
                revenue_leak=revenue_leak,
                seranking_traffic=seranking_traffic,
                competitor_benchmark=competitor_benchmark,
                funnel_walk=funnel_walk,
                pipeline_warnings=pipeline_warnings,
                **synthesis,
            )

            # 5b. Finding-verifier — an agent re-checks every priced finding on the live
            # store; refuted/unverifiable verdicts re-run the (deterministic) leak model so
            # everything downstream (summary, AI skills, Sanity) sees the checked euros.
            verification = await _astep(
                "verifier",
                run_verifier(audit_data, admin=admin_client_for(audit.shopify_shop_domain, audit.shopify_admin_token_enc)),
            )
            if verification:
                pipeline_warnings.extend(f"verifier: {err}"[:300] for err in verification.errors)
            if verification and audit_data.revenue_leak:
                verdicts = verification.verdict_map()
                if any(v != "confirmed" for v in verdicts.values()):
                    checked = _step("revenue_leak_verified", _leak, verdicts)
                    if checked is not None:
                        audit_data.revenue_leak = checked
                        for field, value in _synthesis(checked).items():
                            setattr(audit_data, field, value)
                audit_data.revenue_leak.verification = verification

            # 6. AI top summary — keep deterministic synthesis as fallback
            await _astep("ai_top_summary", enrich_top_summary(audit_data))

            # 7. AI skills — parallel Claude calls on the structured output
            audit_data.ai_analysis = await _astep("ai_analysis", run_ai_analysis(audit_data, pages=pages))
            if audit_data.ai_analysis and audit_data.ai_analysis.cro:
                audit_data.cro_observations.extend(audit_data.ai_analysis.cro.observations)

            # Merge AI bloat candidates into deterministic list (dedupe by item name)
            if audit_data.ai_analysis and audit_data.ai_analysis.bloat:
                existing_names = {b.item.lower() for b in audit_data.bloat_what_must_go}
                for candidate in audit_data.ai_analysis.bloat.candidates:
                    if candidate.item.lower() not in existing_names:
                        audit_data.bloat_what_must_go.append(BloatItem(
                            item=candidate.item,
                            category=candidate.category,
                            reason=candidate.reason,
                            est_savings_eur=candidate.est_savings_eur,
                            est_performance_gain_ms=candidate.est_performance_gain_ms,
                        ))
                        existing_names.add(candidate.item.lower())
                audit_data.bloat_what_must_go.sort(
                    key=lambda i: (-(i.est_savings_eur or 0), -(i.est_performance_gain_ms or 0))
                )

            # 8. Sanity export — deterministic mapping + prose prose generation
            audit_data.sanity_export = await _astep("sanity_export", build_sanity_export(audit_data))

            # Pydantic copied the list at construction; pick up the AI/Sanity steps too.
            audit_data.pipeline_warnings = list(pipeline_warnings)

            # 9. Persist — unless an operator stopped the audit meanwhile (the cancel
            # endpoint writes the status from another session, so re-read it).
            result2 = await db.execute(select(FullAudit).where(FullAudit.id == audit_id))
            row = result2.scalar_one()
            await db.refresh(row)
            if row.status == "cancelled":
                logger.info("Full audit %s was stopped; discarding its result", audit_id)
                return
            row.status = "ready_for_review"
            row.audit_data = audit_data.model_dump(mode="json")
            row.completed_at = datetime.now(UTC)
            await db.commit()
            logger.info("Full audit completed for %s", audit_id)

        except Exception as exc:
            logger.exception("Full audit failed for %s: %s", audit_id, exc)
            try:
                await db.rollback()
            except Exception:
                pass
            try:
                async with AsyncSessionLocal() as db2:
                    r = await db2.execute(select(FullAudit).where(FullAudit.id == audit_id))
                    row = r.scalar_one_or_none()
                    if row and row.status != "cancelled":
                        row.status = "failed"
                        row.error_message = str(exc)[:2000]
                        await db2.commit()
            except Exception:
                pass

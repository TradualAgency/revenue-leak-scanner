import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
            "Automated outside-only scan. Alle bevindingen zijn gebaseerd op publiek toegankelijke signalen: "
            "HTTP headers, DOM analyse, PageSpeed Insights API, en third-party script catalogus. "
            "Geen admin-toegang gebruikt."
        ),
    }


async def run_full_audit(audit_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        try:
            await _set_status(db, audit_id, "processing")

            result = await db.execute(select(FullAudit).where(FullAudit.id == audit_id))
            audit = result.scalar_one()
            store_url = audit.store_url

            # 1. Scrape
            scrape_result = await scrape_store(store_url)
            pages = scrape_result["pages"]
            if not pages:
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
                return_exceptions=True,
            )

            def _safe(val, default=None):
                if isinstance(val, BaseException):
                    logger.warning("Analyzer exception: %s", val)
                    return default
                return val

            platform = _safe(results[0])
            performance_result = _safe(results[1])
            if performance_result is not None:
                performance, psi_third_party_summary = performance_result
            else:
                performance, psi_third_party_summary = None, {}
            third_party = _safe(results[2])
            third_party = apply_psi_third_party_measurements(third_party, psi_third_party_summary)
            tracking = _safe(results[3])
            checkout = _safe(results[4])
            owned = _safe(results[5])
            seo = _safe(results[6])
            security = _safe(results[7])
            dns_email = _safe(results[8])
            domain_health = _safe(results[9])
            rich_results = _safe(results[10])
            server_side_tracking = _safe(results[11])
            product_feeds = _safe(results[12])
            site_search = _safe(results[13])
            shipping = _safe(results[14])
            returns = _safe(results[15])
            multi_region = _safe(results[16])
            marketplaces = _safe(results[17])
            shopify_catalog = _safe(results[18])
            shopify_apps = _safe(results[19])
            retention = _safe(results[20])
            eu_compliance = _safe(results[21])

            # 3. Rollups (synchronous, depend on parallel results)
            cost = build_cost_analysis(third_party, platform)
            bloat = build_bloat_list(third_party, cost)
            cro_obs = make_cro_observations(pages, performance, checkout, rich_results)
            accessibility = make_accessibility_report(pages, performance)
            annual_rev = audit.estimated_annual_revenue_eur

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

            ad_traffic_impact = calculate_ad_traffic_impact(
                performance, third_party, tracking, server_side_tracking,
                annual_revenue_eur=annual_rev,
                traffic=seranking_traffic,
                aov_override=audit.aov_eur,
                sessions_override=audit.monthly_sessions,
                cr_override_pct=audit.conversion_rate_pct,
                ad_spend_override=audit.monthly_ad_spend_eur,
            )
            revenue_leak = calculate_revenue_leak(
                performance, third_party, tracking, checkout, owned,
                cro_obs or [], rich_results, product_feeds, accessibility,
                ad_traffic_impact,
                annual_revenue_eur=annual_rev,
                traffic=seranking_traffic,
                aov_override=audit.aov_eur,
                sessions_override=audit.monthly_sessions,
                cr_override_pct=audit.conversion_rate_pct,
                ad_spend_override=audit.monthly_ad_spend_eur,
                cost=cost,
            )

            # 4. Top-level synthesis
            # Use the low bound for the headline claim in the core thesis — a sales
            # claim should be the conservative end of the range, not the midpoint.
            _leak_for_thesis = (
                (revenue_leak.total_monthly_loss_eur_low if revenue_leak.total_monthly_loss_eur_low is not None else revenue_leak.total_monthly_loss_eur)
                if revenue_leak else None
            )
            synthesis = _synthesize(
                performance, third_party, tracking, cost, platform, dns_email, rich_results, store_url,
                revenue_leak_monthly_eur=_leak_for_thesis,
                revenue_leak=revenue_leak,
            )

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
                **synthesis,
            )

            # 6. AI top summary — keep deterministic synthesis as fallback
            await enrich_top_summary(audit_data)

            # 7. AI skills — parallel Claude calls on the structured output
            audit_data.ai_analysis = await run_ai_analysis(audit_data, pages=pages)
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
            audit_data.sanity_export = await build_sanity_export(audit_data)

            # 9. Persist
            result2 = await db.execute(select(FullAudit).where(FullAudit.id == audit_id))
            row = result2.scalar_one()
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
                    if row:
                        row.status = "failed"
                        row.error_message = str(exc)[:2000]
                        await db2.commit()
            except Exception:
                pass


async def _set_status(db: AsyncSession, audit_id: uuid.UUID, status: str) -> None:
    result = await db.execute(select(FullAudit).where(FullAudit.id == audit_id))
    row = result.scalar_one_or_none()
    if row:
        row.status = status
        await db.commit()

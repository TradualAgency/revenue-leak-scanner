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
from app.full_audit.analyzers.cost import build_cost_analysis
from app.full_audit.analyzers.cro import make_cro_observations
from app.full_audit.analyzers.dns_email import analyze_dns_email
from app.full_audit.analyzers.domain_health import analyze_domain_health
from app.full_audit.analyzers.marketplaces import detect_marketplaces
from app.full_audit.analyzers.multi_region import detect_multi_region
from app.full_audit.analyzers.owned_channels import detect_owned_channels
from app.full_audit.analyzers.performance import analyze_performance
from app.full_audit.analyzers.platform import detect_platform
from app.full_audit.analyzers.product_feeds import analyze_product_feeds
from app.full_audit.analyzers.returns import detect_returns
from app.full_audit.analyzers.rich_results import analyze_rich_results
from app.full_audit.analyzers.ai_analysis import run_ai_analysis
from app.full_audit.analyzers.security import check_security
from app.full_audit.analyzers.seo import audit_seo
from app.full_audit.analyzers.server_side_tracking import analyze_server_side_tracking
from app.full_audit.analyzers.shipping import detect_shipping
from app.full_audit.analyzers.site_search import detect_site_search
from app.full_audit.analyzers.third_party import scan_third_party
from app.full_audit.analyzers.tracking import detect_tracking
from app.full_audit.models import FullAudit
from app.full_audit.schemas import (
    CostAnalysis,
    DnsEmailHealth,
    FullAuditData,
    Performance,
    PlatformArchitecture,
    RichResultsHealth,
    ThirdPartyScripts,
    TrackingDataQuality,
)

logger = logging.getLogger(__name__)


def _synthesize(
    performance: Performance | None,
    third_party: ThirdPartyScripts | None,
    tracking: TrackingDataQuality | None,
    cost: CostAnalysis | None,
    platform: PlatformArchitecture | None,
    dns_email: DnsEmailHealth | None,
    rich_results: RichResultsHealth | None,
    store_url: str,
) -> dict:
    risks: list[str] = []
    opportunities: list[str] = []
    lift_pct: float | None = None

    if performance:
        lcp = performance.mobile.lcp_ms if performance.mobile else None
        if lcp and lcp > 4000:
            risks.append(f"Kritieke mobile LCP van {lcp / 1000:.1f}s (grens: 4s)")
        elif lcp and lcp > 2500:
            risks.append(f"Mobile LCP van {lcp / 1000:.1f}s boven Google drempel van 2.5s")
        perf_score = performance.lighthouse.performance if performance.lighthouse else None
        if perf_score is not None:
            lift_pct = float(max(0, min(60, int((100 - perf_score) * 0.6))))

    if third_party:
        if third_party.total_third_party_blocking_ms and third_party.total_third_party_blocking_ms > 500:
            risks.append(
                f"Third-party scripts veroorzaken {third_party.total_third_party_blocking_ms:.0f}ms render-blocking"
            )
        if third_party.total_third_party_domains and third_party.total_third_party_domains > 15:
            risks.append(f"{third_party.total_third_party_domains} externe domeinen laden bij startup")

    if tracking:
        if tracking.est_attribution_loss_percent and tracking.est_attribution_loss_percent > 25:
            risks.append(f"{tracking.est_attribution_loss_percent:.0f}% geschatte attribution loss door tracking-gaps")
        if tracking.pixels_health in ("partial", "missing"):
            risks.append("Onvolledige pixel setup — ad-algoritmen missen conversie-data")

    if dns_email:
        if dns_email.dmarc_policy in ("missing", "none"):
            risks.append(f"DMARC {dns_email.dmarc_policy} — directe inbox placement en deliverability leak")
        if dns_email.spf_status and dns_email.spf_status != "valid":
            risks.append(f"SPF {dns_email.spf_status} — spoofing-risico en spam-classificatie")

    if rich_results and not rich_results.has_aggregate_rating:
        opportunities.append("Geen AggregateRating schema — sterren ontbreken in Google SERP, directe CTR-winst")

    if cost and cost.est_monthly_savings_eur and cost.est_monthly_savings_eur > 100:
        opportunities.append(f"€{cost.est_monthly_savings_eur:.0f}/maand tech-stack besparing door stack-optimalisatie")

    if platform and platform.detected_platform:
        if platform.architecture_type == "monolith" and platform.detected_platform not in ("Shopify",):
            opportunities.append("Overgang naar headless of geoptimaliseerde stack kan performance structureel verbeteren")

    biggest_risk = risks[0] if risks else None
    biggest_opportunity = opportunities[0] if opportunities else None

    platform_name = platform.detected_platform if platform and platform.detected_platform else "onbekend platform"
    core_thesis: str | None = None
    if biggest_risk:
        core_thesis = "De technische schuld is zichtbaar en meetbaar — aanpakken levert directe, aantoonbare conversiewinst."

    n_issues = len(risks)
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
                return_exceptions=True,
            )

            def _safe(val, default=None):
                if isinstance(val, BaseException):
                    logger.warning("Analyzer exception: %s", val)
                    return default
                return val

            platform = _safe(results[0])
            performance = _safe(results[1])
            third_party = _safe(results[2])
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

            # 3. Rollups (synchronous, depend on parallel results)
            cost = build_cost_analysis(third_party, platform)
            bloat = build_bloat_list(third_party, cost)
            cro_obs = make_cro_observations(pages, performance, checkout)
            accessibility = make_accessibility_report(pages, performance)

            # 4. Top-level synthesis
            synthesis = _synthesize(performance, third_party, tracking, cost, platform, dns_email, rich_results, store_url)

            # 5. Build full data model
            audit_data = FullAuditData(
                store_url=store_url,
                company_name=audit.company_name,
                scan_level=audit.scan_level,  # type: ignore[arg-type]
                industry=audit.industry,
                contact_email=audit.contact_email,
                contact_person=audit.contact_person,
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
                site_search=site_search,
                shipping=shipping,
                returns=returns,
                multi_region=multi_region,
                marketplaces=marketplaces,
                **synthesis,
            )

            # 6. AI skills — parallel Claude calls on the structured output
            audit_data.ai_analysis = await run_ai_analysis(audit_data)

            # 7. Persist
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

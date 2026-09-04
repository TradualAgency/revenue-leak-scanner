"""Per-domain measurement — reuses the full audit's own analyzers unchanged (they
already accept a bare URL and/or the generic scraped `pages` list, so nothing here
needed to know it's measuring a competitor rather than the audited store).

Deliberately excludes analyzers that don't feed a comparison layer (security,
EU compliance, owned channels, marketplaces, shipping, returns, retention, Shopify
catalog, CRO observations) — each one multiplies cost by the domain count for no
comparison value.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.analysis.scraper import scrape_store
from app.config import settings
from app.competitor_benchmark.schemas import CompetitorSnapshot
from app.full_audit.analyzers.accessibility import make_accessibility_report
from app.full_audit.analyzers.checkout import probe_checkout as _probe_checkout
from app.full_audit.analyzers.cost import build_cost_analysis
from app.full_audit.analyzers.dns_email import analyze_dns_email
from app.full_audit.analyzers.domain_health import analyze_domain_health
from app.full_audit.analyzers.performance import analyze_performance
from app.full_audit.analyzers.platform import detect_platform
from app.full_audit.analyzers.product_feeds import analyze_product_feeds
from app.full_audit.analyzers.rich_results import analyze_rich_results
from app.full_audit.analyzers.seo import audit_seo
from app.full_audit.analyzers.server_side_tracking import analyze_server_side_tracking
from app.full_audit.analyzers.third_party import apply_psi_third_party_measurements, scan_third_party
from app.full_audit.analyzers.tracking import detect_tracking

logger = logging.getLogger(__name__)


def _safe(val, default=None):
    if isinstance(val, BaseException):
        logger.warning("Competitor analyzer exception: %s", val)
        return default
    return val


async def _noop() -> None:
    return None


async def measure_domain(domain: str, *, probe_checkout: bool = False) -> CompetitorSnapshot:
    """Never raises — every failure mode degrades to a status field on the returned
    snapshot, so one bad competitor domain can't take down a whole benchmark run."""
    store_url = f"https://{domain}"
    unavailable: list[str] = []

    try:
        scrape_result = await scrape_store(store_url, max_pages=settings.COMPETITOR_SCRAPER_MAX_PAGES)
    except Exception as exc:
        logger.warning("Competitor scrape raised for %s: %s", domain, exc)
        scrape_result = {"pages": []}

    pages = scrape_result.get("pages") or []
    if not pages:
        return CompetitorSnapshot(domain=domain, measure_status="unreachable", measured_at=datetime.now(UTC))

    network_calls = [
        analyze_performance(store_url, pages, include_desktop=False),
        _probe_checkout(store_url) if probe_checkout else _noop(),
        analyze_dns_email(store_url),
        analyze_domain_health(store_url, pages),
        analyze_product_feeds(store_url, pages),
        analyze_server_side_tracking(store_url, pages),
    ]
    pure_calls = [
        detect_platform(pages),
        scan_third_party(pages),
        detect_tracking(pages),
        analyze_rich_results(pages),
        audit_seo(pages),
    ]

    network_results = await asyncio.gather(*network_calls, return_exceptions=True)
    pure_results = await asyncio.gather(*pure_calls, return_exceptions=True)

    performance_result = _safe(network_results[0])
    if performance_result is not None:
        performance, psi_third_party_summary = performance_result
    else:
        performance, psi_third_party_summary = None, {}
        unavailable.append("performance")

    checkout = _safe(network_results[1]) if probe_checkout else None
    if probe_checkout and checkout is None:
        unavailable.append("checkout")

    dns_email = _safe(network_results[2])
    if dns_email is None:
        unavailable.append("dns_email")
    domain_health = _safe(network_results[3])
    if domain_health is None:
        unavailable.append("domain_health")
    product_feeds = _safe(network_results[4])
    if product_feeds is None:
        unavailable.append("product_feeds")
    server_side_tracking = _safe(network_results[5])
    if server_side_tracking is None:
        unavailable.append("server_side_tracking")

    platform = _safe(pure_results[0])
    third_party = _safe(pure_results[1])
    third_party = apply_psi_third_party_measurements(third_party, psi_third_party_summary)
    tracking = _safe(pure_results[2])
    rich_results = _safe(pure_results[3])
    seo = _safe(pure_results[4])

    try:
        accessibility = make_accessibility_report(pages, performance)
    except Exception as exc:
        logger.warning("Competitor accessibility rollup failed for %s: %s", domain, exc)
        accessibility = None
        unavailable.append("accessibility")

    try:
        cost = build_cost_analysis(third_party, platform)
    except Exception as exc:
        logger.warning("Competitor cost rollup failed for %s: %s", domain, exc)
        cost = None

    return CompetitorSnapshot(
        domain=domain,
        measure_status="partial" if unavailable else "ok",
        measured_at=datetime.now(UTC),
        unavailable_metrics=unavailable,
        checkout_probed=probe_checkout,
        platform=platform,
        performance=performance,
        third_party=third_party,
        checkout=checkout,
        tracking=tracking,
        server_side_tracking=server_side_tracking,
        dns_email=dns_email,
        domain_health=domain_health,
        rich_results=rich_results,
        product_feeds=product_feeds,
        seo=seo,
        accessibility=accessibility,
        cost=cost,
    )


async def measure_all(domains: list[str], *, probe_checkout: bool = False) -> list[CompetitorSnapshot]:
    """Bounded concurrency + a hard per-domain timeout — kept low (see config.py's
    COMPETITOR_CONCURRENCY comment) because BackgroundTasks runs in the same process
    as the API server, so measuring domains too aggressively in parallel trades
    wall-clock for measurement failures under load, and each failure costs a data
    point in the eventual market median."""
    semaphore = asyncio.Semaphore(settings.COMPETITOR_CONCURRENCY)

    async def _bounded(domain: str) -> CompetitorSnapshot:
        async with semaphore:
            try:
                return await asyncio.wait_for(
                    measure_domain(domain, probe_checkout=probe_checkout),
                    timeout=settings.COMPETITOR_DOMAIN_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                logger.warning("Competitor measurement timed out for %s", domain)
                return CompetitorSnapshot(domain=domain, measure_status="timeout", measured_at=datetime.now(UTC))
            except Exception as exc:
                logger.warning("Competitor measurement raised unexpectedly for %s: %s", domain, exc)
                return CompetitorSnapshot(domain=domain, measure_status="unreachable", measured_at=datetime.now(UTC))

    return await asyncio.gather(*(_bounded(d) for d in domains))

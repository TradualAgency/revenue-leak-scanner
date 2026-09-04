"""Cheap SEO-only competitor view embedded in every full audit (4 DataForSEO calls,
no enrichment fetches, no AI ranking, no live measurement). For the full live
market-comparison feature — per-domain speed/checkout/tracking measurement, AI
relevance ranking, operator override, euro gap pricing — see the `app.competitor_benchmark`
package and its `/api/v1/competitor-benchmark` endpoints.

This module used to own its own DataForSEO client and competitor-selection logic.
That logic took DataForSEO's raw top-3 keyword-overlap domains, filtered only social
networks and same-brand matches, and deterministically surfaced mega-marketplaces
(amazon.com, ebay.com, etsy.com) for small niche stores — `competitors_domain` ranks
by shared-keyword *volume*, so the biggest domains in the market always won. It's now
a thin wrapper around `app.competitor_benchmark.discovery.discover_candidates`, whose
size-band filter (see `competitor_benchmark/filters.py`) is the structural fix: a
blocklist alone can never be complete, but comparing a candidate's size against the
store's own keeps mega-platforms out regardless of whether they're named anywhere.
"""

from __future__ import annotations

import logging

from app.competitor_benchmark.discovery import discover_candidates
from app.domains import extract_domain
from app.full_audit.schemas import CompetitorBenchmark, CompetitorBenchmarkReport

logger = logging.getLogger(__name__)

_RESULT_LIMIT = 3


async def fetch_competitor_benchmark(
    store_url: str,
    pages: list[dict] | None = None,
    location_code: int | None = None,
    language_code: str | None = None,
) -> CompetitorBenchmarkReport | None:
    market_override = (
        (location_code, language_code) if location_code is not None and language_code is not None else None
    )

    discovery = await discover_candidates(
        store_url, pages or [],
        market_override=market_override,
        use_ai_ranking=False,
        max_ranked=_RESULT_LIMIT,
    )
    if discovery is None:
        return None

    domain = extract_domain(store_url)
    competitors = [
        CompetitorBenchmark(
            domain=c.domain,
            avg_keyword_position=c.avg_keyword_position,
            organic_keywords_count=c.organic_keywords_count,
            est_organic_traffic_value_usd=c.est_organic_traffic_value_usd,
            intersecting_keywords=c.intersections,
        )
        for c in discovery.kept[:_RESULT_LIMIT]
    ]

    return CompetitorBenchmarkReport(
        store_domain=domain,
        store_organic_keywords_count=discovery.store_organic_keywords_count,
        store_est_organic_traffic_value_usd=discovery.store_est_organic_traffic_value_usd,
        competitors=competitors,
        location_code=discovery.market.location_code,
        language_code=discovery.market.language_code,
        notes=(
            f"Marktvergelijking via DataForSEO (organische zoekwoorden en geschatte "
            f"verkeerswaarde), markt: {discovery.market.language_code}-{discovery.market.location_code}. "
            f"Geen live snelheidsmeting van concurrenten — alleen zoekprestatie."
        ),
    )

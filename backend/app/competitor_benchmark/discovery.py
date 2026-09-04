"""Orchestrates competitor discovery: DataForSEO candidate fetch -> deterministic
filters (the structural fix, see filters.py) -> cheap enrichment -> optional AI
ranking pass. The deterministic filters are what keep mega-marketplaces out; the AI
step only ranks and labels what already survived, so an AI outage or a bad model
response degrades to "unranked but still correctly sized" rather than reintroducing
the amazon.com/ebay.com/etsy.com failure this module exists to fix.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

import aiohttp
import anthropic
from bs4 import BeautifulSoup
from pydantic import ValidationError

from app.analysis.scraper import HEADERS as SCRAPER_HEADERS
from app.config import settings
from app.competitor_benchmark import dataforseo
from app.competitor_benchmark.filters import StoreMetrics, apply_filters
from app.competitor_benchmark.market import MarketResolution, brand_label, resolve_market
from app.competitor_benchmark.schemas import (
    CandidateDomain,
    CompetitorRelevanceResponse,
    DiscoveryResult,
    MarketInfo,
    RejectedCandidate,
)
from app.domains import extract_domain
from app.full_audit.page_sampling import classify_page

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
_SKILLS_DIR = Path(__file__).parent / "skills"
_ENRICHMENT_TOP_N = 20
_ENRICHMENT_CONCURRENCY = 8
_ENRICHMENT_TIMEOUT = aiohttp.ClientTimeout(total=8, connect=4)
_ENRICHMENT_STAGE_TIMEOUT_S = 30
_MAX_PRODUCT_TITLES = 15
_MAX_COLLECTION_TITLES = 10

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_DESC_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', re.IGNORECASE,
)
_OG_SITE_NAME_RE = re.compile(
    r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\'](.*?)["\']', re.IGNORECASE,
)
_HTML_LANG_RE = re.compile(r'<html[^>]*\blang=["\']([a-zA-Z-]+)', re.IGNORECASE)

_PLATFORM_SIGNATURES = [
    ("cdn.shopify.com", "Shopify"),
    ("Shopify.theme", "Shopify"),
    ("woocommerce", "WooCommerce"),
    ("cdn.shopware.com", "Shopware"),
    ("lightspeed", "Lightspeed"),
    ("ccvshop", "CCV Shop"),
    ("magento", "Magento"),
]


def _load_skill(name: str) -> str:
    return (_SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _extract_json(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return inner.strip()
    return stripped


def _strip_html(text: str) -> str:
    return BeautifulSoup(text, "lxml").get_text(strip=True) if text else ""


def _collect_titles(pages: list[dict]) -> tuple[list[str], list[str]]:
    """Product/collection titles from whatever the store's own scrape already
    surfaced — no extra fetches, this reuses the full audit's existing page set."""
    product_titles: list[str] = []
    collection_titles: list[str] = []
    for i, page in enumerate(pages):
        ptype = classify_page(page.get("url", ""), is_first=(i == 0))
        if ptype not in ("pdp", "collection"):
            continue
        soup = BeautifulSoup(page.get("html", ""), "lxml")
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else None
        if not title and soup.title:
            title = soup.title.get_text(strip=True)
        if not title:
            continue
        if ptype == "pdp" and len(product_titles) < _MAX_PRODUCT_TITLES:
            product_titles.append(title)
        elif ptype == "collection" and len(collection_titles) < _MAX_COLLECTION_TITLES:
            collection_titles.append(title)
    return product_titles, collection_titles


# --- DataForSEO candidate normalization -------------------------------------------

def _normalize_competitors_domain(items: list[dict]) -> dict[str, dict]:
    normalized: dict[str, dict] = {}
    for item in items:
        domain = item.get("domain")
        if not domain:
            continue
        organic = (item.get("full_domain_metrics") or {}).get("organic", {})
        normalized[domain] = {
            "domain": domain,
            "discovery_source": "competitors_domain",
            "organic_keywords_count": organic.get("count"),
            "est_organic_traffic_value_usd": organic.get("etv"),
            "avg_keyword_position": item.get("avg_position"),
            "intersections": item.get("intersections"),
            "serp_keyword_hits": None,
        }
    return normalized


def _extract_ranked_keyword(item: dict) -> str | None:
    kw = item.get("keyword")
    if kw:
        return kw
    return (item.get("keyword_data") or {}).get("keyword")


def _normalize_serp_competitors(items: list[dict]) -> dict[str, dict]:
    # NOTE: field paths for serp_competitors are best-effort against DataForSEO Labs'
    # documented shape and defensively parsed with .get() — verify against a live
    # response before relying on this in production, per the plan's flagged risk.
    normalized: dict[str, dict] = {}
    for item in items:
        domain = item.get("domain")
        if not domain:
            continue
        organic = (item.get("full_domain_metrics") or {}).get("organic", {})
        hits = item.get("keywords_count") or item.get("intersections") or item.get("se_results_count")
        normalized[domain] = {
            "domain": domain,
            "discovery_source": "serp_competitors",
            "organic_keywords_count": organic.get("count"),
            "est_organic_traffic_value_usd": organic.get("etv"),
            "avg_keyword_position": item.get("avg_position"),
            "intersections": None,
            "serp_keyword_hits": hits,
        }
    return normalized


def _merge_candidates(from_competitors: dict[str, dict], from_serp: dict[str, dict]) -> list[dict]:
    merged: dict[str, dict] = dict(from_competitors)
    for domain, candidate in from_serp.items():
        if domain in merged:
            merged[domain]["discovery_source"] = "both"
            merged[domain]["serp_keyword_hits"] = candidate["serp_keyword_hits"]
        else:
            merged[domain] = candidate
    return list(merged.values())


def _pre_score(candidate: CandidateDomain, store_k: int | None) -> float:
    intersections_norm = min(1.0, (candidate.intersections or 0) / 50)
    if store_k and candidate.organic_keywords_count:
        size_penalty = min(1.0, abs(_log10_ratio(candidate.organic_keywords_count, store_k)) / 2)
    else:
        size_penalty = 0.5
    both_bonus = 1.0 if candidate.discovery_source == "both" else 0.0
    return 0.5 * intersections_norm + 0.3 * (1 - size_penalty) + 0.2 * both_bonus


def _log10_ratio(a: float, b: float) -> float:
    import math
    if a <= 0 or b <= 0:
        return 0.0
    return math.log10(a / b)


# --- enrichment ----------------------------------------------------------------

async def _enrich_one(session: aiohttp.ClientSession, candidate: CandidateDomain) -> CandidateDomain:
    url = f"https://{candidate.domain}"
    try:
        async with session.get(url, max_redirects=3, allow_redirects=True) as resp:
            if resp.status >= 400:
                return candidate.model_copy(update={"enrichment_status": "unreachable"})
            body = await resp.content.read(150_000)
            html = body.decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.debug("Enrichment fetch failed for %s: %s", candidate.domain, exc)
        return candidate.model_copy(update={"enrichment_status": "unreachable"})

    title_match = _TITLE_RE.search(html)
    desc_match = _META_DESC_RE.search(html)
    og_match = _OG_SITE_NAME_RE.search(html)
    lang_match = _HTML_LANG_RE.search(html)
    platform = None
    for needle, name in _PLATFORM_SIGNATURES:
        if needle.lower() in html.lower():
            platform = name
            break

    return candidate.model_copy(update={
        "enrichment_status": "ok",
        "title": _strip_html(title_match.group(1))[:200] if title_match else None,
        "meta_description": _strip_html(desc_match.group(1))[:300] if desc_match else None,
        "og_site_name": _strip_html(og_match.group(1))[:100] if og_match else None,
        "html_lang": lang_match.group(1) if lang_match else None,
        "platform_guess": platform,
    })


async def _enrich_candidates(candidates: list[CandidateDomain]) -> list[CandidateDomain]:
    semaphore = asyncio.Semaphore(_ENRICHMENT_CONCURRENCY)

    async def _bounded(session: aiohttp.ClientSession, c: CandidateDomain) -> CandidateDomain:
        async with semaphore:
            return await _enrich_one(session, c)

    async def _run() -> list[CandidateDomain]:
        async with aiohttp.ClientSession(timeout=_ENRICHMENT_TIMEOUT, headers=SCRAPER_HEADERS) as session:
            return await asyncio.gather(*(_bounded(session, c) for c in candidates))

    try:
        return await asyncio.wait_for(_run(), timeout=_ENRICHMENT_STAGE_TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning("Competitor enrichment stage timed out after %ss", _ENRICHMENT_STAGE_TIMEOUT_S)
        return candidates


# --- AI ranking ------------------------------------------------------------------

async def rank_candidates_with_ai(
    store_domain: str,
    company_name: str | None,
    industry: str | None,
    product_titles: list[str],
    collection_titles: list[str],
    market: MarketInfo,
    store_organic_keywords_count: int | None,
    candidates: list[CandidateDomain],
) -> CompetitorRelevanceResponse | None:
    if not settings.ANTHROPIC_API_KEY or not candidates:
        return None

    payload = json.dumps({
        "store": {
            "domain": store_domain,
            "company_name": company_name,
            "industry": industry,
            "product_titles": product_titles,
            "collection_titles": collection_titles,
            "market": {"location_code": market.location_code, "language_code": market.language_code},
            "organic_keywords_count": store_organic_keywords_count,
        },
        "candidates": [
            {
                "domain": c.domain,
                "title": c.title,
                "meta_description": c.meta_description,
                "og_site_name": c.og_site_name,
                "platform_guess": c.platform_guess,
                "lang": c.html_lang,
                "organic_keywords_count": c.organic_keywords_count,
                "est_organic_traffic_value_usd": c.est_organic_traffic_value_usd,
                "intersections": c.intersections,
                "discovery_source": c.discovery_source,
                "size_ratio_to_store": c.size_ratio_to_store,
            }
            for c in candidates
        ],
    }, ensure_ascii=False)

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=_load_skill("competitor_relevance"),
            messages=[{"role": "user", "content": payload}],
        )
        raw = message.content[0].text
        data = json.loads(_extract_json(raw))
        response = CompetitorRelevanceResponse.model_validate(data)
    except (json.JSONDecodeError, ValidationError, anthropic.APIError) as exc:
        logger.warning("Competitor relevance AI ranking failed: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Competitor relevance AI ranking failed unexpectedly: %s", exc)
        return None

    return _sanitize_ai_ranking(response, {c.domain for c in candidates})


def _sanitize_ai_ranking(response: CompetitorRelevanceResponse, valid_domains: set[str]) -> CompetitorRelevanceResponse:
    """Belt-and-braces server-side enforcement of the skill's own instructions — a
    hallucinated domain or a marketplace the model mis-ranked into `ranked` must not
    be able to reach the measured set."""
    from app.competitor_benchmark.schemas import AiExcludedCompetitor

    ranked = []
    excluded = [e for e in response.excluded if e.domain in valid_domains]
    for entry in response.ranked:
        if entry.domain not in valid_domains:
            continue
        if entry.classification in ("marketplace", "retailer", "irrelevant"):
            excluded.append(AiExcludedCompetitor(domain=entry.domain, classification=entry.classification, reason_nl=entry.reason_nl))
            continue
        ranked.append(entry)
    return CompetitorRelevanceResponse(ranked=ranked, excluded=excluded, market_note_nl=response.market_note_nl)


# --- orchestration ---------------------------------------------------------------

async def discover_candidates(
    store_url: str,
    pages: list[dict],
    *,
    company_name: str | None = None,
    industry: str | None = None,
    market_override: tuple[int, str] | None = None,
    use_ai_ranking: bool = True,
    max_ranked: int = 10,
) -> DiscoveryResult | None:
    if not dataforseo.credentials_configured():
        logger.debug("DataForSEO credentials not configured — skipping competitor discovery")
        return None

    store_domain = extract_domain(store_url)
    homepage_html = pages[0].get("html") if pages else None
    market_resolution: MarketResolution = resolve_market(store_domain, pages, override=market_override)
    market = MarketInfo(
        location_code=market_resolution.location_code,
        language_code=market_resolution.language_code,
        source=market_resolution.source,
        confidence=market_resolution.confidence,
    )

    async with dataforseo.new_session() as session:
        own = await dataforseo.fetch_domain_rank_overview(session, store_domain, market.location_code, market.language_code)
        competitors_items = await dataforseo.fetch_competitors_domain(session, store_domain, market.location_code, market.language_code)
        ranked_keywords_items = await dataforseo.fetch_ranked_keywords(session, store_domain, market.location_code, market.language_code)

        brand = brand_label(store_domain)
        seed_keywords = [
            kw for kw in (_extract_ranked_keyword(item) for item in ranked_keywords_items)
            if kw and brand not in kw.lower()
        ]
        serp_items = await dataforseo.fetch_serp_competitors(session, store_domain, seed_keywords, market.location_code, market.language_code)

    store_k = (own or {}).get("organic_keywords_count")
    store_etv = (own or {}).get("est_organic_traffic_value_usd")

    normalized = _merge_candidates(_normalize_competitors_domain(competitors_items), _normalize_serp_competitors(serp_items))
    store_metrics = StoreMetrics(domain=store_domain, organic_keywords_count=store_k, est_organic_traffic_value_usd=store_etv)
    kept, rejected = apply_filters(normalized, store_metrics, market_language_code=market.language_code)

    kept.sort(key=lambda c: _pre_score(c, store_k), reverse=True)
    top_candidates = kept[:_ENRICHMENT_TOP_N]

    if use_ai_ranking:
        # Enrichment (title/meta/platform fingerprint) only exists to feed the AI
        # ranking payload — skip the extra network round-trips entirely for the
        # deterministic-only path (the cheap SEO-only view embedded in every full
        # audit), which needs nothing beyond the DataForSEO metrics already fetched.
        enriched = await _enrich_candidates(top_candidates)
        unreachable = [c for c in enriched if c.enrichment_status == "unreachable"]
        reachable = [c for c in enriched if c.enrichment_status != "unreachable"]
        for c in unreachable:
            rejected.append(RejectedCandidate(domain=c.domain, reason_code="enrichment_unreachable", reason_nl="niet bereikbaar bij verificatie"))
    else:
        reachable = top_candidates

    ai_ranking_used = False
    market_note_nl = None
    if use_ai_ranking and reachable:
        product_titles, collection_titles = _collect_titles(pages)
        ai_response = await rank_candidates_with_ai(
            store_domain, company_name, industry, product_titles, collection_titles,
            market, store_k, reachable,
        )
        if ai_response is not None:
            ai_ranking_used = True
            market_note_nl = ai_response.market_note_nl
            by_domain = {c.domain: c for c in reachable}
            final: list[CandidateDomain] = []
            for entry in sorted(ai_response.ranked, key=lambda e: e.rank)[:max_ranked]:
                base = by_domain.get(entry.domain)
                if base is None:
                    continue
                final.append(base.model_copy(update={
                    "classification": entry.classification,
                    "relevance_score": entry.relevance_score,
                    "reason_nl": entry.reason_nl,
                    "rank": entry.rank,
                }))
            for excl in ai_response.excluded:
                base = by_domain.get(excl.domain)
                reason = excl.reason_nl
                if base is not None:
                    rejected.append(RejectedCandidate(domain=excl.domain, reason_code="ai_excluded", reason_nl=reason, category=excl.classification))
            reachable = final

    if not ai_ranking_used:
        # Deterministic fallback: pre-score ordering stands as-is. The size band
        # already did the load-bearing work of keeping mega-platforms out — this
        # path is "correctly sized but unranked", never "unfiltered".
        for i, c in enumerate(reachable[:max_ranked], start=1):
            reachable[i - 1] = c.model_copy(update={
                "classification": "category",
                "rank": i,
                "reason_nl": "Automatisch geselecteerd op zoekwoordoverlap en vergelijkbare omvang (AI-classificatie niet beschikbaar)",
            })
        reachable = reachable[:max_ranked]

    return DiscoveryResult(
        market=market,
        store_organic_keywords_count=store_k,
        store_est_organic_traffic_value_usd=store_etv,
        kept=reachable,
        rejected=rejected,
        market_note_nl=market_note_nl,
        ai_ranking_used=ai_ranking_used,
    )

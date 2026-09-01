from __future__ import annotations

import base64
import logging
import re

import aiohttp

from app.config import settings
from app.full_audit.analyzers.seranking import extract_domain
from app.full_audit.schemas import CompetitorBenchmark, CompetitorBenchmarkReport

logger = logging.getLogger(__name__)

_API_BASE = "https://api.dataforseo.com/v3"
_TIMEOUT = aiohttp.ClientTimeout(total=45.0)

# DataForSEO Labs endpoints require a specific location+language pair — there's no
# "worldwide" aggregate like SE Ranking's. Competitor/keyword-overlap analysis is
# inherently market-specific (Google.nl rankings != Google.com rankings), so forcing
# every audited store through one hardcoded market produces nonsense for stores that
# don't operate there — e.g. a US brand's own Benelux storefront showing up as its own
# "competitor" when queried against the Dutch market. Detect the store's actual market
# instead of assuming one.
_TLD_MARKETS: dict[str, tuple[int, str]] = {
    "nl": (2528, "nl"),
    "be": (2056, "nl"),
    "de": (2276, "de"),
    "at": (2040, "de"),
    "ch": (2756, "de"),
    "uk": (2826, "en"),
    "fr": (2250, "fr"),
    "es": (2724, "es"),
    "it": (2380, "it"),
    "us": (2840, "en"),
    "ca": (2124, "en"),
    "au": (2036, "en"),
}
_LANG_MARKETS: dict[str, tuple[int, str]] = {
    "nl": (2528, "nl"),
    "de": (2276, "de"),
    "fr": (2250, "fr"),
    "es": (2724, "es"),
    "it": (2380, "it"),
    "en": (2840, "en"),
}
_DEFAULT_MARKET = (2840, "en")  # US/English — the most common global default, not NL.

_HTML_LANG_RE = re.compile(r'<html[^>]*\blang=["\']([a-zA-Z-]+)', re.IGNORECASE)

# DataForSEO's competitors_domain endpoint ranks by keyword overlap, not "is a business
# competitor" — the target's own domain always appears (100% overlap with itself), and
# generic mega-platforms (YouTube, Wikipedia, social networks) routinely show up because
# they rank for the same broad terms without competing for the same customer. Over-fetch
# and filter both out before truncating to the final list.
_COMPETITOR_FETCH_LIMIT = 15
_COMPETITOR_RESULT_LIMIT = 3
_NON_COMPETITOR_DOMAINS = {
    "youtube.com", "wikipedia.org", "facebook.com", "instagram.com", "pinterest.com",
    "linkedin.com", "reddit.com", "tiktok.com", "twitter.com", "x.com",
}


def _brand_label(domain: str) -> str:
    """First label of a domain, e.g. "allbirds" from "allbirds.com" or "allbirdsbenelux.nl"."""
    return domain.split(".")[0].lower()


def detect_market(domain: str, homepage_html: str | None = None) -> tuple[int, str]:
    tld = domain.rsplit(".", 1)[-1].lower()
    if tld in _TLD_MARKETS:
        return _TLD_MARKETS[tld]
    if homepage_html:
        match = _HTML_LANG_RE.search(homepage_html)
        if match:
            lang = match.group(1).split("-")[0].lower()
            if lang in _LANG_MARKETS:
                return _LANG_MARKETS[lang]
    return _DEFAULT_MARKET


def _auth_header() -> dict[str, str]:
    token = base64.b64encode(f"{settings.DATAFORSEO_LOGIN}:{settings.DATAFORSEO_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


async def _post(session: aiohttp.ClientSession, path: str, body: list[dict]) -> dict | None:
    try:
        async with session.post(f"{_API_BASE}{path}", json=body) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.warning("DataForSEO %s returned %s: %s", path, resp.status, text[:300])
                return None
            data = await resp.json()
    except Exception as exc:
        # Observed in practice: some large domains cause DataForSEO Labs to return a
        # task-level 500 or simply hang well past a reasonable timeout. Either way this
        # is "no competitor data available", not a reason to fail the whole audit.
        logger.warning("DataForSEO request failed for %s: %s", path, exc)
        return None

    tasks = data.get("tasks") or []
    if not tasks or tasks[0].get("status_code") != 20000:
        logger.warning("DataForSEO task error for %s: %s", path, tasks[0].get("status_message") if tasks else "no tasks")
        return None
    return tasks[0]


async def fetch_competitor_benchmark(
    store_url: str,
    pages: list[dict] | None = None,
    location_code: int | None = None,
    language_code: str | None = None,
) -> CompetitorBenchmarkReport | None:
    if not settings.DATAFORSEO_LOGIN or not settings.DATAFORSEO_PASSWORD:
        logger.debug("DataForSEO credentials not configured — skipping competitor benchmark")
        return None

    domain = extract_domain(store_url)
    brand = _brand_label(domain)

    if location_code is None or language_code is None:
        homepage_html = pages[0].get("html") if pages else None
        detected_location, detected_language = detect_market(domain, homepage_html)
        location_code = location_code if location_code is not None else detected_location
        language_code = language_code if language_code is not None else detected_language

    async with aiohttp.ClientSession(timeout=_TIMEOUT, headers=_auth_header()) as session:
        own_task = await _post(
            session,
            "/dataforseo_labs/google/domain_rank_overview/live",
            [{"target": domain, "location_code": location_code, "language_code": language_code}],
        )
        competitors_task = await _post(
            session,
            "/dataforseo_labs/google/competitors_domain/live",
            [{"target": domain, "location_code": location_code, "language_code": language_code, "limit": _COMPETITOR_FETCH_LIMIT}],
        )

    if own_task is None and competitors_task is None:
        return None

    own_keywords: int | None = None
    own_etv: float | None = None
    own_result = (own_task or {}).get("result") or []
    if own_result and own_result[0] and own_result[0].get("items"):
        organic = own_result[0]["items"][0].get("metrics", {}).get("organic", {})
        own_keywords = organic.get("count")
        own_etv = organic.get("etv")

    competitors: list[CompetitorBenchmark] = []
    comp_result = (competitors_task or {}).get("result") or []
    if comp_result and comp_result[0] and comp_result[0].get("items"):
        for item in comp_result[0]["items"]:
            if len(competitors) >= _COMPETITOR_RESULT_LIMIT:
                break
            item_domain = item.get("domain", "")
            item_brand = _brand_label(item_domain)
            if not item_domain or item_domain == domain or item_domain in _NON_COMPETITOR_DOMAINS:
                continue
            # Same-brand regional storefronts (e.g. "allbirdsbenelux.nl" for
            # "allbirds.com") aren't competitors — they're the audited store itself.
            if brand and item_brand and (brand in item_brand or item_brand in brand):
                continue
            organic = (item.get("full_domain_metrics") or {}).get("organic", {})
            competitors.append(CompetitorBenchmark(
                domain=item_domain,
                avg_keyword_position=item.get("avg_position"),
                organic_keywords_count=organic.get("count"),
                est_organic_traffic_value_usd=organic.get("etv"),
                intersecting_keywords=item.get("intersections"),
            ))

    return CompetitorBenchmarkReport(
        store_domain=domain,
        store_organic_keywords_count=own_keywords,
        store_est_organic_traffic_value_usd=own_etv,
        competitors=competitors,
        location_code=location_code,
        language_code=language_code,
        notes=(
            f"Marktvergelijking via DataForSEO (organische zoekwoorden en geschatte "
            f"verkeerswaarde), markt: {language_code}-{location_code}. Geen live "
            f"snelheidsmeting van concurrenten — alleen zoekprestatie."
        ),
    )

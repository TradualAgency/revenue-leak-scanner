import logging

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

PAGESPEED_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


async def get_pagespeed_score(url: str, strategy: str = "mobile") -> dict | None:
    """
    Call Google PageSpeed Insights API for a given URL.

    Returns dict with performance_score and load_time_ms, or None on failure.
    """
    if not settings.PAGESPEED_API_KEY:
        return None

    params = {
        "url": url,
        "strategy": strategy,
        "key": settings.PAGESPEED_API_KEY,
        "category": "performance",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                PAGESPEED_API_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.warning("PageSpeed API returned %d for %s", resp.status, url)
                    return None
                data = await resp.json()

        lighthouse = data.get("lighthouseResult", {})
        categories = lighthouse.get("categories", {})
        performance_score = int(categories.get("performance", {}).get("score", 0) * 100)

        audits = lighthouse.get("audits", {})
        fcp = audits.get("first-contentful-paint", {}).get("numericValue", 0)
        lcp = audits.get("largest-contentful-paint", {}).get("numericValue", 0)
        load_time_ms = int(max(fcp, lcp))

        return {
            "performance_score": performance_score,
            "load_time_ms": load_time_ms,
        }

    except Exception as e:
        logger.warning("PageSpeed API error for %s: %s", url, e)
        return None


async def measure_pages(store_url: str, scraped_pages: list[dict]) -> dict:
    """
    Measure performance for key pages (homepage, first collection, first product).

    Falls back to aiohttp response times if no API key is configured.
    """
    if not settings.PAGESPEED_API_KEY:
        # Fallback: aiohttp measures TTFB only; multiply by ~8 to estimate full browser
        # page load time (TTFB is typically ~10-12% of total load time for e-commerce stores).
        load_times = [p["load_time_ms"] for p in scraped_pages if p.get("load_time_ms", 0) > 0]
        raw_avg = int(sum(load_times) / len(load_times)) if load_times else 1000
        estimated_ms = max(1500, min(raw_avg * 8, 12000))
        return {
            "performance_score": None,
            "avg_load_time_ms": estimated_ms,
            "source": "aiohttp_fallback",
        }

    # Select up to 3 key pages: homepage, a /collections/ page, a /products/ page
    key_urls = [store_url]
    for page in scraped_pages:
        url = page.get("url", "")
        if "/collections/" in url and len(key_urls) < 2:
            key_urls.append(url)
        elif "/products/" in url and len(key_urls) < 3:
            key_urls.append(url)

    scores = []
    load_times = []

    for url in key_urls[:3]:
        result = await get_pagespeed_score(url, strategy="mobile")
        if result:
            scores.append(result["performance_score"])
            load_times.append(result["load_time_ms"])

    if not scores:
        # Fallback if API calls all failed
        raw_times = [p["load_time_ms"] for p in scraped_pages if p.get("load_time_ms", 0) > 0]
        avg_ms = int(sum(raw_times) / len(raw_times)) if raw_times else 3000
        return {
            "performance_score": None,
            "avg_load_time_ms": avg_ms,
            "source": "aiohttp_fallback",
        }

    return {
        "performance_score": int(sum(scores) / len(scores)),
        "avg_load_time_ms": int(sum(load_times) / len(load_times)),
        "source": "pagespeed_api",
    }

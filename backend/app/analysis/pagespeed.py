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

    Requires PAGESPEED_API_KEY. The scraper's own fetch time is TTFB (time to first
    byte), not a browser page load — scaling it by a guessed multiplier presented a
    fabricated number as a measurement. Without PSI, or if every PSI call fails, page
    load time is genuinely unmeasured: avg_load_time_ms comes back None rather than a guess.
    """
    if not settings.PAGESPEED_API_KEY:
        return {"performance_score": None, "avg_load_time_ms": None, "source": "not_measured"}

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
        # All PSI calls failed — same "genuinely unmeasured" case as no API key.
        return {"performance_score": None, "avg_load_time_ms": None, "source": "not_measured"}

    return {
        "performance_score": int(sum(scores) / len(scores)),
        "avg_load_time_ms": int(sum(load_times) / len(load_times)),
        "source": "pagespeed_api",
    }

import asyncio
import logging
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; RevLeakBot/1.0; +https://revleak.io/bot)"
    )
}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[str, dict[str, str], int]:
    """Fetch a single page. Returns (html, headers, status_code)."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=settings.SCRAPER_TIMEOUT_SECONDS)) as resp:
            html = await resp.text(errors="replace")
            return html, dict(resp.headers), resp.status
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return "", {}, 0


def extract_internal_links(html: str, base_url: str, max_links: int = 30) -> list[str]:
    """Extract unique internal links from HTML."""
    soup = BeautifulSoup(html, "lxml")
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc

    links: list[str] = []
    seen: set[str] = set()

    for tag in soup.find_all("a", href=True):
        href = str(tag.get("href", "")).strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        if parsed.netloc != base_domain:
            continue
        if parsed.scheme not in ("http", "https"):
            continue

        clean = full_url.split("?")[0].split("#")[0].rstrip("/")
        if clean not in seen and clean != base_url.rstrip("/"):
            seen.add(clean)
            links.append(clean)

        if len(links) >= max_links:
            break

    return links


async def scrape_store(store_url: str) -> dict:
    """
    Scrape the store homepage and up to SCRAPER_MAX_PAGES internal pages.

    Returns:
        {
            "pages": [{"url": ..., "html": ..., "headers": ..., "load_time_ms": ...}],
            "avg_load_time_ms": int,
            "pages_discovered": int,
        }
    """
    connector = aiohttp.TCPConnector(limit=settings.SCRAPER_CONCURRENCY)
    timeout = aiohttp.ClientTimeout(total=settings.SCRAPER_TIMEOUT_SECONDS)

    results: list[dict] = []

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector, timeout=timeout) as session:
        # Fetch homepage
        import time

        start = time.monotonic()
        homepage_html, homepage_headers, _ = await fetch_page(session, store_url)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if not homepage_html:
            return {"pages": [], "avg_load_time_ms": 0, "pages_discovered": 0}

        results.append({
            "url": store_url,
            "html": homepage_html,
            "headers": homepage_headers,
            "load_time_ms": elapsed_ms,
        })

        # Discover internal links
        internal_links = extract_internal_links(homepage_html, store_url)
        max_additional = settings.SCRAPER_MAX_PAGES - 1

        # Fetch additional pages concurrently (up to SCRAPER_CONCURRENCY at a time)
        sem = asyncio.Semaphore(settings.SCRAPER_CONCURRENCY)

        async def fetch_with_timing(url: str) -> dict | None:
            async with sem:
                start = time.monotonic()
                html, headers, status = await fetch_page(session, url)
                elapsed_ms = int((time.monotonic() - start) * 1000)
                if not html:
                    return None
                return {"url": url, "html": html, "headers": headers, "load_time_ms": elapsed_ms}

        tasks = [fetch_with_timing(url) for url in internal_links[:max_additional]]
        page_results = await asyncio.gather(*tasks)

        for page in page_results:
            if page:
                results.append(page)

    load_times = [p["load_time_ms"] for p in results if p["load_time_ms"] > 0]
    avg_load_time_ms = int(sum(load_times) / len(load_times)) if load_times else 0

    return {
        "pages": results,
        "avg_load_time_ms": avg_load_time_ms,
        "pages_discovered": len(results),
    }

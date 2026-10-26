import asyncio
import logging
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)

# Browser-compatible prefix so storefronts serve their normal HTML, plus an honest
# product token and contact URL. The old "RevLeakBot" UA was blocked outright by many
# WAFs (anything matching "bot"), and the challenge page it got back was then analysed
# as if it were the store.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0 Safari/537.36 TradualAudit/1.0 (+https://tradual.com)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}

# Markers of a bot-challenge or interstitial page. Only trusted on a *small* page:
# Cloudflare and Imperva also inject scripts with similar names into normal storefront
# HTML, which is tens to hundreds of KB.
_CHALLENGE_MARKERS = (
    "<title>Just a moment...</title>",
    "cf-browser-verification",
    "cf-chl-",
    "_Incapsula_Resource",
    "px-captcha",
    "captcha-delivery.com",
    "Attention Required! | Cloudflare",
)
_CHALLENGE_MAX_BYTES = 50_000


def block_reason(status: int, html: str) -> str | None:
    """Why this response isn't the store's page, or None when it is."""
    if status >= 400:
        return f"HTTP {status}"
    if len(html) < _CHALLENGE_MAX_BYTES:
        for marker in _CHALLENGE_MARKERS:
            if marker in html:
                return f"botbeveiliging ({marker.strip('<>/')})"
    return None


def set_cookie_text(page: dict) -> str:
    """Every Set-Cookie header of a scraped page, newline-joined, for substring checks.
    Falls back to the single header the `headers` dict can hold."""
    cookies = page.get("set_cookies")
    if cookies:
        return "\n".join(cookies)
    return {k.lower(): v for k, v in (page.get("headers") or {}).items()}.get("set-cookie", "")


async def fetch_page(
    session: aiohttp.ClientSession, url: str,
) -> tuple[str, dict[str, str], int, list[str]]:
    """Fetch a single page. Returns (html, headers, status_code, set_cookies).

    `set_cookies` keeps every Set-Cookie header: `dict(resp.headers)` keeps only one,
    and the cookie-based detectors (ESP, Meta CAPI) need all of them."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=settings.SCRAPER_TIMEOUT_SECONDS)) as resp:
            html = await resp.text(errors="replace")
            return html, dict(resp.headers), resp.status, resp.headers.getall("Set-Cookie", [])
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return "", {}, 0, []


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


async def scrape_store(store_url: str, max_pages: int | None = None) -> dict:
    """
    Scrape the store homepage and up to `max_pages` (default SCRAPER_MAX_PAGES)
    internal pages.

    Returns:
        {
            "pages": [{"url", "html", "headers", "set_cookies", "status", "load_time_ms"}],
            "avg_load_time_ms": int,
            "pages_discovered": int,
            "blocked_reason": str | None,  # set when the homepage itself was blocked
            "blocked_pages": int,          # subpages dropped as error/challenge pages
        }

    Error and bot-challenge responses are dropped, not analysed: a 403 page has no
    tracking pixels and no reviews, and reporting that as the store's state was worse
    than reporting nothing.
    """
    effective_max_pages = max_pages if max_pages is not None else settings.SCRAPER_MAX_PAGES
    connector = aiohttp.TCPConnector(limit=settings.SCRAPER_CONCURRENCY)
    timeout = aiohttp.ClientTimeout(total=settings.SCRAPER_TIMEOUT_SECONDS)

    results: list[dict] = []

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector, timeout=timeout) as session:
        # Fetch homepage
        import time

        start = time.monotonic()
        homepage_html, homepage_headers, homepage_status, homepage_cookies = await fetch_page(session, store_url)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if not homepage_html:
            return {"pages": [], "avg_load_time_ms": 0, "pages_discovered": 0, "blocked_reason": None, "blocked_pages": 0}
        reason = block_reason(homepage_status, homepage_html)
        if reason:
            logger.warning("Homepage of %s blocked: %s", store_url, reason)
            return {"pages": [], "avg_load_time_ms": 0, "pages_discovered": 0, "blocked_reason": reason, "blocked_pages": 0}

        results.append({
            "url": store_url,
            "html": homepage_html,
            "headers": homepage_headers,
            "set_cookies": homepage_cookies,
            "status": homepage_status,
            "load_time_ms": elapsed_ms,
        })

        # Discover internal links
        internal_links = extract_internal_links(homepage_html, store_url)
        max_additional = effective_max_pages - 1

        # Fetch additional pages concurrently (up to SCRAPER_CONCURRENCY at a time)
        sem = asyncio.Semaphore(settings.SCRAPER_CONCURRENCY)

        async def fetch_with_timing(url: str) -> dict | None:
            async with sem:
                start = time.monotonic()
                html, headers, status, cookies = await fetch_page(session, url)
                elapsed_ms = int((time.monotonic() - start) * 1000)
                if not html:
                    return None
                return {
                    "url": url, "html": html, "headers": headers, "set_cookies": cookies,
                    "status": status, "load_time_ms": elapsed_ms,
                }

        tasks = [fetch_with_timing(url) for url in internal_links[:max_additional]]
        page_results = await asyncio.gather(*tasks)

        blocked_pages = 0
        for page in page_results:
            if not page:
                continue
            if block_reason(page["status"], page["html"]):
                blocked_pages += 1
                continue
            results.append(page)

    load_times = [p["load_time_ms"] for p in results if p["load_time_ms"] > 0]
    avg_load_time_ms = int(sum(load_times) / len(load_times)) if load_times else 0

    return {
        "pages": results,
        "avg_load_time_ms": avg_load_time_ms,
        "pages_discovered": len(results),
        "blocked_reason": None,
        "blocked_pages": blocked_pages,
    }

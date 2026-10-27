"""A mobile Playwright session that can't do harm.

Two guarantees, enforced on every request by `is_request_allowed` (a pure function,
so it's unit-tested without a browser):

1. No side effects on the store. Only GETs, plus POSTs to the store's own cart and
   search-suggest endpoints. Checkout submits, payments, newsletter/contact forms and
   account calls are aborted — no order, signup or message can ever go out.
2. No pollution of the client's data. Pixel and analytics hosts are aborted even for
   GETs, so the walk's add-to-carts never reach Meta/Google/TikTok or GA4.

Third-party GETs (review widgets, popups, chat, fonts) are allowed on purpose: the
agent has to see the page a real visitor sees, overlays included.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from app.analysis.scraper import url_locale

_SIGS_PATH = Path(__file__).parents[2] / "full_audit" / "data" / "tracker_signatures.json"

# Collect endpoints that aren't in the script patterns of tracker_signatures.json.
_EXTRA_TRACKER_HOSTS = {
    "google-analytics.com", "analytics.google.com", "googleadservices.com", "doubleclick.net",
    "googletagmanager.com", "facebook.com", "facebook.net", "analytics.tiktok.com",
    "ct.pinterest.com", "bat.bing.com", "clarity.ms", "hotjar.com", "hotjar.io",
    "snap.licdn.com", "px.ads.linkedin.com", "tr.snapchat.com", "sc-static.net",
    "monorail-edge.shopifysvc.com",  # Shopify's own analytics pipeline
}
# Store-relative paths that report analytics on the store's own domain.
_TRACKER_PATHS = ("/.well-known/shopify/monorail", "/api/collect", "/web-pixels")

# The only writes allowed, on the store's own host — optionally behind a market/locale
# prefix like /nl or /en-be: Shopify's AJAX cart, predictive search, and the Storefront
# API (headless/Hydrogen themes add to cart through its cartLinesAdd mutation; the agent
# never fills a form, so the customer/account mutations behind it aren't reachable).
_ALLOWED_POST_PATH = re.compile(
    r"^(/[a-z]{2}(-[a-z]{2})?)?"
    r"(/cart/(add|change|update)(\.js)?|/cart\.js|/search/suggest(\.json)?|/api/[a-z0-9_-]+/graphql\.json)$"
)


def _tracker_hosts() -> frozenset[str]:
    hosts = set(_EXTRA_TRACKER_HOSTS)
    try:
        sigs = json.loads(_SIGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset(hosts)
    for entry in sigs.get("analytics", []):
        for pattern in entry.get("script_patterns", []):
            host = pattern.split("/", 1)[0]
            if "." in host and " " not in host:
                hosts.add(host.removeprefix("www."))
    return frozenset(hosts)


TRACKER_HOSTS = _tracker_hosts()


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _matches(host: str, domains) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def is_request_allowed(method: str, url: str, store_hosts: set[str]) -> bool:
    host = _host(url)
    path = urlparse(url).path.lower()
    if not host:
        return urlparse(url).scheme in ("data", "blob")
    if _matches(host, TRACKER_HOSTS):
        return False
    own = host in store_hosts
    if own and path.startswith(_TRACKER_PATHS):
        return False
    method = method.upper()
    if method in ("GET", "HEAD", "OPTIONS"):
        return True
    return own and method == "POST" and bool(_ALLOWED_POST_PATH.match(path))


def is_checkout_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return "/checkouts/" in path or path.rstrip("/").endswith("/checkout")


@dataclass
class Screenshot:
    id: str
    image: bytes
    caption: str
    page_url: str


@dataclass
class BrowserSession:
    """Created by `open_session`; holds the page, the screenshots taken so far, and a
    log of blocked requests (shown to the operator as proof nothing went out)."""
    store_url: str
    page: object = None
    context: object = None
    browser: object = None
    playwright: object = None
    screenshots: dict[str, Screenshot] = field(default_factory=dict)
    blocked: list[str] = field(default_factory=list)
    cart_responses: list[float] = field(default_factory=list)  # monotonic times of cart POST responses
    # Machine-recorded facts (see EVIDENCE_* in browser_tools.py). A priced issue needs
    # its fact here; the model's word alone never carries a euro.
    evidence: set[str] = field(default_factory=set)

    @property
    def store_hosts(self) -> set[str]:
        return {_host(self.store_url)}

    def new_screenshot_id(self) -> str:
        return str(uuid.uuid4())


async def open_session(store_url: str, *, headless: bool = True) -> BrowserSession:
    from playwright.async_api import async_playwright

    session = BrowserSession(store_url=store_url)
    session.playwright = await async_playwright().start()
    device = session.playwright.devices["iPhone 14"]
    session.browser = await session.playwright.chromium.launch(headless=headless)
    # Browse in the storefront's own language, so `/de` isn't redirected to `/nl`.
    lang, _, region = (url_locale(store_url) or "nl-nl").partition("-")
    locale = f"{lang}-{region.upper()}" if region else lang
    session.context = await session.browser.new_context(**device, locale=locale, timezone_id="Europe/Amsterdam")

    async def guard(route):
        request = route.request
        if is_request_allowed(request.method, request.url, session.store_hosts):
            await route.continue_()
        else:
            if len(session.blocked) < 200:
                session.blocked.append(f"{request.method} {request.url[:200]}")
            await route.abort()

    await session.context.route("**/*", guard)

    def on_response(response):
        request = response.request
        if request.method != "POST":
            return
        path = urlparse(response.url).path
        if "/cart/" in path or path.endswith("/cart.js") or (
            path.endswith("/graphql.json") and "cart" in (request.post_data or "").lower()
        ):
            session.cart_responses.append(time.monotonic())

    session.page = await session.context.new_page()
    session.page.on("response", on_response)
    return session


async def close_session(session: BrowserSession) -> None:
    for closer in (session.context, session.browser):
        if closer is not None:
            try:
                await closer.close()
            except Exception:
                pass
    if session.playwright is not None:
        await session.playwright.stop()

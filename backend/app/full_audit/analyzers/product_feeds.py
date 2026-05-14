import json
import logging
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from app.full_audit.schemas import ProductFeedHealth

logger = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=10)
_GOOD_JSONLD_FIELDS = {"gtin", "sku", "brand", "mpn"}

_FEED_ENDPOINTS = [
    "/products.json?limit=1",        # Shopify
    "/wp-json/wc/store/products",     # WooCommerce
]


async def analyze_product_feeds(store_url: str, pages: list[dict]) -> ProductFeedHealth:
    try:
        parsed = urlparse(store_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        feed_endpoint: str | None = None
        feed_reachable: bool | None = None

        async with aiohttp.ClientSession() as session:
            for path in _FEED_ENDPOINTS:
                url = f"{base}{path}"
                try:
                    async with session.get(url, timeout=_TIMEOUT, allow_redirects=True) as r:
                        if r.status == 200:
                            feed_endpoint = url
                            feed_reachable = True
                            break
                        elif r.status not in (404, 410):
                            feed_reachable = False
                except Exception:
                    pass

        # OG product tags + JSON-LD on a PDP page
        og_present = False
        jsonld_complete: bool | None = None
        missing_fields: list[str] = []

        pdp_page = None
        for page in pages:
            url = page.get("url", "")
            if any(seg in url for seg in ("/product/", "/products/", "/p/", "/shop/", "/item/")):
                pdp_page = page
                break
        check_page = pdp_page or (pages[0] if pages else None)

        if check_page:
            html = check_page.get("html", "")
            soup = BeautifulSoup(html, "lxml")

            og_tags = [
                t for t in soup.find_all("meta")
                if str(t.get("property", "")).startswith("product:")
            ]
            og_present = len(og_tags) > 0

            for tag in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(tag.string or tag.get_text())
                    items = data.get("@graph", [data]) if isinstance(data, dict) else (data if isinstance(data, list) else [data])
                    for item in items:
                        if isinstance(item, dict) and item.get("@type") == "Product":
                            present_keys = {k.lower() for k in item}
                            missing_fields = [f for f in _GOOD_JSONLD_FIELDS if f not in present_keys]
                            jsonld_complete = len(missing_fields) == 0
                            break
                except Exception:
                    pass

        score = sum([
            (feed_reachable or 0) * 2,
            int(og_present),
            2 if jsonld_complete is True else (1 if jsonld_complete is False else 0),
        ])
        estimate = "not-ready" if score <= 1 else "partial" if score <= 3 else "ready"

        return ProductFeedHealth(
            platform_feed_endpoint=feed_endpoint,
            feed_endpoint_reachable=feed_reachable,
            og_product_tags_present=og_present,
            jsonld_product_complete=jsonld_complete,
            missing_fields=missing_fields,
            google_merchant_ready_estimate=estimate,  # type: ignore[arg-type]
        )
    except Exception as exc:
        logger.warning("product_feeds analyzer failed: %s", exc)
        return ProductFeedHealth()

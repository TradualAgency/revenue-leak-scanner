import logging
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from app.full_audit.analyzers.jsonld import PRODUCT_TYPES, jsonld_nodes, node_types, product_keys
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

            product = next((n for n in jsonld_nodes(html) if node_types(n) & PRODUCT_TYPES), None)
            if product is not None:
                present = product_keys(product)
                missing_fields = [
                    f for f in sorted(_GOOD_JSONLD_FIELDS)
                    # gtin8/12/13/14 all satisfy "has a GTIN"
                    if not (f in present or (f == "gtin" and any(k.startswith("gtin") for k in present)))
                ]
                jsonld_complete = len(missing_fields) == 0

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

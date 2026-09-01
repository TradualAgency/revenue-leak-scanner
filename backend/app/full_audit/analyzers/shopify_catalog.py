import json
import logging
import re

import aiohttp

from app.full_audit.schemas import ShopifyCatalogHealth

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TradualAuditBot/1.0)"}

# Shopify embeds a `Shopify.theme = {...}` object on every storefront page. There is no
# public, unauthenticated endpoint that exposes a theme *version* — only the Admin API
# does, which is out of scope for an outside-only scan — so name/id is the ceiling here.
_THEME_RE = re.compile(r"Shopify\.theme\s*=\s*(\{.*?\})\s*;", re.DOTALL)

_TAG_RE = re.compile(r"<[^>]+>")


def _extract_theme(html: str) -> tuple[str | None, int | None]:
    match = _THEME_RE.search(html)
    if not match:
        return None, None
    try:
        data = json.loads(match.group(1))
    except Exception:
        return None, None
    theme_id = data.get("id")
    return data.get("name"), theme_id if isinstance(theme_id, int) else None


async def analyze_shopify_catalog(store_url: str, pages: list[dict]) -> ShopifyCatalogHealth | None:
    base = store_url.rstrip("/")
    homepage_html = pages[0]["html"] if pages else ""
    theme_name, theme_id = _extract_theme(homepage_html)

    detected = False
    products_sampled = 0
    out_of_stock = 0
    missing_images = 0
    missing_description = 0
    collections_sampled: int | None = None

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
            # Public, unauthenticated Shopify storefront endpoint — max 250 per page.
            # One page only: this is a sample for out-of-stock/content-gap signal, not a
            # claim about total catalog size.
            async with session.get(f"{base}/products.json?limit=250") as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    products = data.get("products", []) if isinstance(data, dict) else []
                    detected = True
                    products_sampled = len(products)
                    for product in products:
                        variants = product.get("variants", [])
                        if variants and all(not v.get("available") for v in variants):
                            out_of_stock += 1
                        if not product.get("images"):
                            missing_images += 1
                        body_text = _TAG_RE.sub("", product.get("body_html") or "").strip()
                        if len(body_text) < 20:
                            missing_description += 1

            async with session.get(f"{base}/collections.json?limit=250") as resp:
                if resp.status == 200:
                    cdata = await resp.json(content_type=None)
                    collections = cdata.get("collections", []) if isinstance(cdata, dict) else []
                    collections_sampled = len(collections)
    except Exception as exc:
        logger.warning("Shopify catalog probe failed for %s: %s", store_url, exc)

    if not detected and theme_name is None:
        # Neither the products feed nor the theme object responded — this almost
        # certainly isn't a Shopify store (or it's blocking both signals), so there's
        # nothing honest to report here.
        return None

    out_of_stock_pct = round(out_of_stock / products_sampled * 100, 1) if products_sampled else None

    evidence_parts = []
    if detected:
        evidence_parts.append(f"/products.json: {products_sampled} producten gesampled")
    if theme_name:
        evidence_parts.append(f"Thema: {theme_name}" + (f" (id {theme_id})" if theme_id else ""))

    return ShopifyCatalogHealth(
        detected=detected,
        product_count_sampled=products_sampled if detected else None,
        products_out_of_stock=out_of_stock if detected else None,
        out_of_stock_ratio_pct=out_of_stock_pct,
        products_missing_images=missing_images if detected else None,
        products_missing_description=missing_description if detected else None,
        collection_count_sampled=collections_sampled,
        theme_name=theme_name,
        theme_id=theme_id,
        evidence="; ".join(evidence_parts) if evidence_parts else None,
    )

import json
import logging

from bs4 import BeautifulSoup

from app.full_audit.schemas import RichResultsHealth

logger = logging.getLogger(__name__)

_RICH_TYPES = {
    "Organization", "WebSite", "Product", "AggregateRating", "Review",
    "BreadcrumbList", "FAQPage", "ItemList", "Article", "LocalBusiness",
    "VideoObject", "Event",
}


def _parse_schemas(html: str) -> set[str]:
    found: set[str] = set()
    try:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                raw = tag.string or tag.get_text()
                data = json.loads(raw)
                items = data.get("@graph", [data]) if isinstance(data, dict) else (data if isinstance(data, list) else [data])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    t = item.get("@type", "")
                    if isinstance(t, list):
                        found.update(t)
                    elif t:
                        found.add(t)
                    # AggregateRating nested under Product
                    if isinstance(item.get("aggregateRating"), dict):
                        found.add("AggregateRating")
            except Exception:
                pass
    except Exception:
        pass
    return found


async def analyze_rich_results(pages: list[dict]) -> RichResultsHealth:
    try:
        all_schemas: set[str] = set()
        pdp_url: str | None = None

        for page in pages:
            url = page.get("url", "")
            html = page.get("html", "")
            schemas = _parse_schemas(html)
            all_schemas.update(schemas)
            if not pdp_url and any(seg in url for seg in ("/product/", "/products/", "/p/", "/shop/", "/item/")):
                pdp_url = url

        detected = sorted(all_schemas & _RICH_TYPES)
        has_product = "Product" in all_schemas
        has_aggregate_rating = "AggregateRating" in all_schemas
        has_breadcrumb = "BreadcrumbList" in all_schemas
        has_faq = "FAQPage" in all_schemas

        recs: list[str] = []
        if not has_product:
            recs.append("Voeg Product schema toe op PDP's voor Google Shopping eligibility")
        if not has_aggregate_rating:
            recs.append("Voeg AggregateRating toe voor sterren in Google zoekresultaten")
        if not has_breadcrumb:
            recs.append("Voeg BreadcrumbList toe voor betere SERP navigatie")

        return RichResultsHealth(
            schemas_detected=detected,
            has_product_schema=has_product,
            has_aggregate_rating=has_aggregate_rating,
            has_breadcrumb=has_breadcrumb,
            has_faq=has_faq,
            pdp_sampled_url=pdp_url,
            recommendations=recs,
        )
    except Exception as exc:
        logger.warning("rich_results analyzer failed: %s", exc)
        return RichResultsHealth()

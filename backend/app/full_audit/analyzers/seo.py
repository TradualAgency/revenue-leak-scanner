import json
import re
from collections import Counter
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.full_audit.schemas import HreflangSetup, SeoHealth, TrafficTrend


def _has_schema_markup(html: str) -> tuple[bool, str | None]:
    soup = BeautifulSoup(html, "lxml")
    ld_scripts = soup.find_all("script", type="application/ld+json")
    if not ld_scripts:
        return False, "No JSON-LD schema markup detected"
    types_found = []
    for script in ld_scripts:
        try:
            data = json.loads(script.string or "")
            schema_type = data.get("@type") or (
                data.get("@graph", [{}])[0].get("@type") if isinstance(data.get("@graph"), list) else None
            )
            if schema_type:
                types_found.append(schema_type if isinstance(schema_type, str) else str(schema_type))
        except Exception:
            types_found.append("unparseable")
    if types_found:
        return True, None
    return False, "JSON-LD script found but empty or unparseable"


def _detect_hreflang(html: str) -> HreflangSetup:
    soup = BeautifulSoup(html, "lxml")
    hreflang_tags = soup.find_all("link", rel="alternate", hreflang=True)
    if not hreflang_tags:
        # Check if the site looks international by looking for language indicators in URLs
        lang_paths = re.findall(r'href=["\']/([a-z]{2})/', html)
        if lang_paths:
            return "incorrect"
        return "n-a"
    # Has hreflang — check for x-default
    has_x_default = any(str(t.get("hreflang", "")) == "x-default" for t in hreflang_tags)
    return "correct" if has_x_default else "incorrect"


def _detect_programmatic(pages: list[dict]) -> tuple[bool, str | None]:
    all_urls = [p.get("url", "") for p in pages]
    paths = [urlparse(u).path for u in all_urls if u]

    # Count path prefixes
    prefix_counts: Counter = Counter()
    for path in paths:
        parts = [p for p in path.split("/") if p]
        if parts:
            prefix_counts[parts[0]] += 1

    # If any prefix has 5+ pages, likely programmatic
    for prefix, count in prefix_counts.items():
        if count >= 5 and prefix in ("products", "collections", "categories", "blog", "artikel"):
            return True, f"/{prefix}/ pattern detected ({count} pages scraped)"

    return False, None


async def audit_seo(pages: list[dict]) -> SeoHealth:
    if not pages:
        return SeoHealth()

    homepage_html = pages[0].get("html", "")

    has_schema, schema_issue = _has_schema_markup(homepage_html)
    hreflang = _detect_hreflang(homepage_html)
    programmatic, prog_quality = _detect_programmatic(pages)

    return SeoHealth(
        organic_traffic_trend="unknown",
        organic_traffic_source="Not available without GSC access",
        branded_vs_nonbranded_ratio=None,
        has_schema_markup=has_schema,
        schema_issues=schema_issue,
        programmatic_pages_detected=programmatic,
        programmatic_quality=prog_quality,
        hreflang_setup=hreflang,
        notes="Traffic metrics require Google Search Console access.",
    )

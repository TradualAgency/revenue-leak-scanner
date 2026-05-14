import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.full_audit.schemas import ArchitectureType, DetectionConfidence, PlatformArchitecture

_SHOPIFY_SIGNALS = [
    (r"Shopify\.theme", "inline JS: Shopify.theme global"),
    (r"cdn\.shopify\.com", "script/asset domain cdn.shopify.com"),
    (r"shopify-analytics", "script src: shopify-analytics"),
    (r"<meta[^>]+generator[^>]+Shopify", "meta generator: Shopify"),
]
_WOOCOMMERCE_SIGNALS = [
    (r"woocommerce", "body class or script: woocommerce"),
    (r"wc-ajax", "AJAX endpoint: wc-ajax"),
    (r"wp-content/plugins/woocommerce", "plugin path: woocommerce"),
]
_MAGENTO_SIGNALS = [
    (r"Magento", "inline global: Magento"),
    (r"/static/version\d+/", "asset path: /static/versionN/"),
    (r"mage/", "RequireJS: mage/"),
]
_NEXTJS_SIGNALS = [
    (r"__NEXT_DATA__", "inline JSON: __NEXT_DATA__"),
    (r"/_next/static/", "asset path: /_next/static/"),
]
_NUXT_SIGNALS = [
    (r"__NUXT__", "inline JSON: __NUXT__"),
    (r"/_nuxt/", "asset path: /_nuxt/"),
]
_GATSBY_SIGNALS = [
    (r"___gatsby", "data attribute: ___gatsby"),
    (r"/static/gatsby-", "asset path: gatsby-"),
]

_CDN_HEADERS = {
    "cloudflare": "Cloudflare (server header)",
    "cloudfront": "Amazon CloudFront (via)",
    "fastly": "Fastly (x-served-by)",
    "akamai": "Akamai (x-check-cacheable)",
    "bunnycdn": "BunnyCDN (cdn-requestid)",
    "vercel": "Vercel Edge Network",
}


def _first_headers(pages: list[dict]) -> dict[str, str]:
    for p in pages:
        if p.get("headers"):
            return {k.lower(): v for k, v in p["headers"].items()}
    return {}


def _all_html(pages: list[dict]) -> str:
    return " ".join(p.get("html", "") for p in pages)


def _detect_cdn(headers: dict[str, str]) -> tuple[str | None, str | None]:
    server = headers.get("server", "").lower()
    via = headers.get("via", "").lower()
    x_cache = headers.get("x-cache", "").lower()

    if "cloudflare" in server:
        return "Cloudflare", f"server: {headers.get('server')}"
    if "cloudfront" in via or "cloudfront" in x_cache:
        return "Amazon CloudFront", f"via: {headers.get('via', '')} / x-cache: {headers.get('x-cache', '')}"
    if "fastly" in via or headers.get("x-served-by", ""):
        return "Fastly", f"via: {headers.get('via', '')}"
    if "akamai" in server or headers.get("x-akamai-transformed"):
        return "Akamai", "x-akamai-transformed header present"
    if headers.get("cdn-requestid"):
        return "BunnyCDN", "cdn-requestid header present"
    if headers.get("x-vercel-id") or "vercel" in server:
        return "Vercel Edge", f"x-vercel-id: {headers.get('x-vercel-id', 'present')}"
    return None, None


def _rate(signals: list[tuple[str, str]], html: str) -> tuple[bool, list[str]]:
    hits = []
    for pattern, desc in signals:
        if re.search(pattern, html, re.IGNORECASE):
            hits.append(desc)
    return bool(hits), hits


async def detect_platform(pages: list[dict]) -> PlatformArchitecture:
    if not pages:
        return PlatformArchitecture()

    headers = _first_headers(pages)
    html = _all_html(pages)
    homepage = pages[0]
    base_url = homepage.get("url", "")

    # Platform detection
    detected_platform: str | None = None
    confidence: DetectionConfidence = "unknown"
    evidence_parts: list[str] = []

    shopify_hit, shopify_ev = _rate(_SHOPIFY_SIGNALS, html)
    woo_hit, woo_ev = _rate(_WOOCOMMERCE_SIGNALS, html)
    magento_hit, magento_ev = _rate(_MAGENTO_SIGNALS, html)
    next_hit, next_ev = _rate(_NEXTJS_SIGNALS, html)
    nuxt_hit, nuxt_ev = _rate(_NUXT_SIGNALS, html)
    gatsby_hit, gatsby_ev = _rate(_GATSBY_SIGNALS, html)

    if shopify_hit:
        detected_platform = "Shopify"
        confidence = "confirmed" if len(shopify_ev) >= 2 else "probable"
        evidence_parts = shopify_ev
    elif woo_hit:
        detected_platform = "WooCommerce"
        confidence = "confirmed" if len(woo_ev) >= 2 else "probable"
        evidence_parts = woo_ev
    elif magento_hit:
        detected_platform = "Magento 2"
        confidence = "confirmed" if len(magento_ev) >= 2 else "probable"
        evidence_parts = magento_ev
    elif next_hit:
        detected_platform = "Custom Next.js"
        confidence = "probable"
        evidence_parts = next_ev
    elif nuxt_hit:
        detected_platform = "Custom Nuxt.js"
        confidence = "probable"
        evidence_parts = nuxt_ev
    elif gatsby_hit:
        detected_platform = "Custom Gatsby"
        confidence = "probable"
        evidence_parts = gatsby_ev

    # Hosting detection from headers
    hosting: str | None = None
    hosting_ev: str | None = None
    server_header = headers.get("server", "")
    powered_by = headers.get("x-powered-by", "")

    if "shopify" in server_header.lower():
        hosting = "Shopify Cloud"
        hosting_ev = f"server: {server_header}"
    elif "vercel" in server_header.lower() or headers.get("x-vercel-id"):
        hosting = "Vercel"
        hosting_ev = f"server: {server_header}"
    elif "netlify" in server_header.lower() or headers.get("x-nf-request-id"):
        hosting = "Netlify"
        hosting_ev = "x-nf-request-id header present"
    elif "nginx" in server_header.lower():
        hosting = "Nginx (self-hosted or VPS)"
        hosting_ev = f"server: {server_header}"
    elif "apache" in server_header.lower():
        hosting = "Apache"
        hosting_ev = f"server: {server_header}"
    elif powered_by:
        hosting = powered_by
        hosting_ev = f"x-powered-by: {powered_by}"

    cdn, cdn_ev = _detect_cdn(headers)

    # Architecture type
    architecture_type: ArchitectureType = "monolith"
    arch_rationale = "Monolithic rendering assumed (server-renders HTML directly)."
    if next_hit or nuxt_hit or gatsby_hit:
        architecture_type = "headless"
        arch_rationale = "Detected JS framework signals suggest headless or hybrid architecture."
    elif shopify_hit and next_hit:
        architecture_type = "hybrid"
        arch_rationale = "Shopify backend with Next.js storefront detected."

    recommended_architecture: str | None = None
    arch_assessment: str | None = None
    if architecture_type == "monolith" and detected_platform == "Shopify":
        recommended_architecture = "monolith"
        arch_assessment = "Shopify monolith is fine for most stores. Headless adds complexity without guaranteed performance gain unless traffic exceeds ~100k monthly sessions."
    elif architecture_type == "monolith" and detected_platform in ("WooCommerce", "Magento 2"):
        recommended_architecture = "headless"
        arch_assessment = "Monolithic WooCommerce/Magento stores benefit significantly from headless or static-first architecture for performance."

    soup = BeautifulSoup(homepage.get("html", ""), "lxml")
    theme_tag = soup.find("meta", attrs={"name": "theme-color"})
    theme = None
    if next_hit:
        theme = "Next.js"
    elif nuxt_hit:
        theme = "Nuxt.js"
    elif gatsby_hit:
        theme = "Gatsby"

    return PlatformArchitecture(
        detected_platform=detected_platform,
        detection_confidence=confidence,
        detection_evidence="; ".join(evidence_parts) if evidence_parts else None,
        hosting=hosting,
        hosting_detection_evidence=hosting_ev,
        cdn_detected=cdn,
        cdn_evidence=cdn_ev,
        server_location=None,
        theme_or_framework=theme,
        architecture_type=architecture_type,
        architecture_rationale=arch_rationale,
        recommended_architecture=recommended_architecture,  # type: ignore[arg-type]
        architecture_assessment=arch_assessment,
    )

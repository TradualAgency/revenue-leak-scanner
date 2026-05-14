import logging
import re

from bs4 import BeautifulSoup

from app.full_audit.schemas import MultiRegionHealth

logger = logging.getLogger(__name__)

_CURRENCY_SYMBOLS = re.compile(r"[\$€£¥₹\$]", re.UNICODE)
_CURRENCY_SWITCHER_PATTERNS = [
    re.compile(r"currency.?switcher|currency.?selector|change.?currency", re.IGNORECASE),
    re.compile(r'data-currency|class="[^"]*currency[^"]*"', re.IGNORECASE),
    re.compile(r"<select[^>]*currency", re.IGNORECASE),
]
_CURRENCY_CODE_RE = re.compile(r"\b(EUR|USD|GBP|CAD|AUD|CHF|SEK|NOK|DKK|PLN|CZK|HUF)\b")


async def detect_multi_region(store_url: str, pages: list[dict]) -> MultiRegionHealth:
    try:
        html_combined = "\n".join(p.get("html", "") for p in pages[:3])

        # Currency switcher detection
        currency_switcher = any(p.search(html_combined) for p in _CURRENCY_SWITCHER_PATTERNS)

        # Currencies mentioned
        currencies = list(set(_CURRENCY_CODE_RE.findall(html_combined)))[:10]

        # Hreflang count (from all pages)
        hreflang_count = 0
        for page in pages:
            try:
                soup = BeautifulSoup(page.get("html", ""), "lxml")
                hreflang_count += len(soup.find_all("link", rel="alternate", hreflang=True))
            except Exception:
                pass

        # Vary: Accept-Language from response headers
        vary_al = False
        for page in pages:
            hdrs = {k.lower(): v for k, v in (page.get("headers", {}) or {}).items()}
            vary = hdrs.get("vary", "")
            if "accept-language" in vary.lower():
                vary_al = True
                break

        # Geo redirect heuristic: Content-Language header set differently from domain TLD
        geo_redirect: bool | None = None
        content_lang = None
        if pages:
            hp_hdrs = {k.lower(): v for k, v in (pages[0].get("headers", {}) or {}).items()}
            content_lang = hp_hdrs.get("content-language")
            cf_country = hp_hdrs.get("cf-ipcountry")  # Cloudflare passes country through
            if content_lang and cf_country:
                geo_redirect = True

        evidence_parts = []
        if currency_switcher:
            evidence_parts.append("currency-switcher gevonden in DOM")
        if currencies:
            evidence_parts.append(f"valuta: {', '.join(currencies[:5])}")
        if hreflang_count:
            evidence_parts.append(f"{hreflang_count} hreflang tags")

        return MultiRegionHealth(
            currency_switcher_detected=currency_switcher,
            currencies_detected=currencies,
            hreflang_count=hreflang_count or None,
            vary_accept_language=vary_al,
            geo_redirect_detected=geo_redirect,
            evidence="; ".join(evidence_parts) if evidence_parts else None,
        )
    except Exception as exc:
        logger.warning("multi_region analyzer failed: %s", exc)
        return MultiRegionHealth()

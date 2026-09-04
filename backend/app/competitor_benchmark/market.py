from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# DataForSEO Labs endpoints require a specific location+language pair — there's no
# "worldwide" aggregate like SE Ranking's. Competitor/keyword-overlap analysis is
# inherently market-specific (Google.nl rankings != Google.com rankings), so forcing
# every audited store through one hardcoded market produces nonsense for stores that
# don't operate there.
TLD_MARKETS: dict[str, tuple[int, str]] = {
    "nl": (2528, "nl"),
    "be": (2056, "nl"),
    "de": (2276, "de"),
    "at": (2040, "de"),
    "ch": (2756, "de"),
    "uk": (2826, "en"),
    "fr": (2250, "fr"),
    "es": (2724, "es"),
    "it": (2380, "it"),
    "us": (2840, "en"),
    "ca": (2124, "en"),
    "au": (2036, "en"),
}
LANG_MARKETS: dict[str, tuple[int, str]] = {
    "nl": (2528, "nl"),
    "de": (2276, "de"),
    "fr": (2250, "fr"),
    "es": (2724, "es"),
    "it": (2380, "it"),
    "en": (2840, "en"),
}
# US/English — the most common global default, not NL. Confidence is deliberately
# marked "low" for this branch so the operator UI knows to double-check it: a `.com`
# store that falls all the way through to here is precisely the case that produced
# the amazon/ebay/etsy failure (US/EN is where mega-marketplaces dominate every
# commercial keyword cluster).
DEFAULT_MARKET = (2840, "en")

_HTML_LANG_RE = re.compile(r'<html[^>]*\blang=["\']([a-zA-Z-]+)', re.IGNORECASE)
_HREFLANG_RE = re.compile(r'hreflang=["\']([a-zA-Z-]+)["\']', re.IGNORECASE)
_OG_LOCALE_RE = re.compile(r'<meta[^>]+property=["\']og:locale["\'][^>]+content=["\']([a-zA-Z_-]+)["\']', re.IGNORECASE)
_SHOPIFY_COUNTRY_RE = re.compile(r'Shopify\.country\s*=\s*["\']([A-Z]{2})["\']')
_SHOPIFY_CURRENCY_RE = re.compile(r'"active"\s*:\s*"([A-Z]{3})"')

TLDS_BY_LANGUAGE: dict[str, set[str]] = {}
for _tld_key, (_loc, _lang) in TLD_MARKETS.items():
    TLDS_BY_LANGUAGE.setdefault(_lang, set()).add(_tld_key)

_CURRENCY_TO_MARKET: dict[str, tuple[int, str]] = {
    "EUR": (2528, "nl"),  # ambiguous within the eurozone — only used as a low-confidence tiebreaker
    "GBP": (2826, "en"),
    "USD": (2840, "en"),
}
_COUNTRY_TO_MARKET: dict[str, tuple[int, str]] = {
    "NL": (2528, "nl"), "BE": (2056, "nl"), "DE": (2276, "de"), "AT": (2040, "de"),
    "CH": (2756, "de"), "GB": (2826, "en"), "FR": (2250, "fr"), "ES": (2724, "es"),
    "IT": (2380, "it"), "US": (2840, "en"), "CA": (2124, "en"), "AU": (2036, "en"),
}

Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class MarketResolution:
    location_code: int
    language_code: str
    source: str
    confidence: Confidence


def _tld(domain: str) -> str:
    return domain.rsplit(".", 1)[-1].lower()


def resolve_market(
    domain: str,
    pages: list[dict] | None = None,
    override: tuple[int, str] | None = None,
) -> MarketResolution:
    if override is not None:
        return MarketResolution(location_code=override[0], language_code=override[1], source="operator", confidence="high")

    tld = _tld(domain)
    if tld in TLD_MARKETS:
        loc, lang = TLD_MARKETS[tld]
        return MarketResolution(location_code=loc, language_code=lang, source="tld", confidence="high")

    homepage_html = pages[0].get("html", "") if pages else ""

    if homepage_html:
        hreflang_matches = _HREFLANG_RE.findall(homepage_html)
        if hreflang_matches:
            # Majority region among hreflang alternates, e.g. mostly "nl-NL"/"nl-BE".
            counts: dict[str, int] = {}
            for tag in hreflang_matches:
                lang = tag.split("-")[0].lower()
                if lang in LANG_MARKETS:
                    counts[lang] = counts.get(lang, 0) + 1
            if counts:
                top_lang = max(counts, key=lambda k: counts[k])
                loc, lang = LANG_MARKETS[top_lang]
                return MarketResolution(location_code=loc, language_code=lang, source="hreflang", confidence="medium")

        og_match = _OG_LOCALE_RE.search(homepage_html)
        if og_match:
            country = og_match.group(1).split("_")[-1].upper()
            if country in _COUNTRY_TO_MARKET:
                loc, lang = _COUNTRY_TO_MARKET[country]
                return MarketResolution(location_code=loc, language_code=lang, source="og_locale", confidence="medium")

        shopify_country = _SHOPIFY_COUNTRY_RE.search(homepage_html)
        if shopify_country and shopify_country.group(1) in _COUNTRY_TO_MARKET:
            loc, lang = _COUNTRY_TO_MARKET[shopify_country.group(1)]
            return MarketResolution(location_code=loc, language_code=lang, source="shopify_country", confidence="high")

        html_lang_match = _HTML_LANG_RE.search(homepage_html)
        if html_lang_match:
            lang = html_lang_match.group(1).split("-")[0].lower()
            if lang in LANG_MARKETS:
                loc, lang_code = LANG_MARKETS[lang]
                return MarketResolution(location_code=loc, language_code=lang_code, source="html_lang", confidence="medium")

        shopify_currency = _SHOPIFY_CURRENCY_RE.search(homepage_html)
        if shopify_currency and shopify_currency.group(1) in _CURRENCY_TO_MARKET:
            loc, lang = _CURRENCY_TO_MARKET[shopify_currency.group(1)]
            return MarketResolution(location_code=loc, language_code=lang, source="currency", confidence="low")

    loc, lang = DEFAULT_MARKET
    return MarketResolution(location_code=loc, language_code=lang, source="default_fallback", confidence="low")


# Subdomain prefixes that don't carry brand identity — stripping them before the
# same-brand check fixes a live bug: `_brand_label("shop.example.nl")` used to return
# "shop", which then substring-matched (and silently dropped) any competitor whose
# domain happened to contain "shop" anywhere.
_NON_BRAND_PREFIXES = {"www", "shop", "store", "webshop", "nl", "en", "de", "fr", "be", "eu", "shopnl", "shopeu"}


def brand_label(domain: str) -> str:
    """Registrable brand label, e.g. "allbirds" from "allbirds.com" or
    "shop.allbirdsbenelux.nl" — subdomain prefixes that aren't part of the brand name
    are stripped first so they can't cause spurious substring matches."""
    labels = [l for l in domain.lower().split(".") if l]
    if len(labels) <= 2:
        return labels[0] if labels else ""
    # everything except the last two labels (registrable domain + TLD) is a subdomain
    candidate_labels = labels[:-2]
    brand_labels = [l for l in candidate_labels if l not in _NON_BRAND_PREFIXES]
    return (brand_labels[0] if brand_labels else labels[-2])


def is_same_brand(domain_a: str, domain_b: str) -> bool:
    a, b = brand_label(domain_a), brand_label(domain_b)
    if not a or not b:
        return False
    return a in b or b in a

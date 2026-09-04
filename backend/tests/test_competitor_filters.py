"""Regression anchor for the amazon.com/ebay.com/etsy.com incident: DataForSEO's
competitors_domain endpoint ranks by shared-keyword volume, so — with only a
social-network blocklist and a same-brand check — a niche Shopify store deterministically
got mega-marketplaces as its "competitors". These tests prove the size-band filter in
filters.py is what actually fixes this, not the blocklist (which can never be complete).
"""

from unittest.mock import patch

from app.competitor_benchmark.filters import StoreMetrics, apply_filters

# The real incident: olafhussein.com, 89 organic keywords, got amazon.com (39,044,800
# keywords — a 438,706x ratio), ebay.com, and etsy.com as its "competitors".
_STORE = StoreMetrics(domain="olafhussein.com", organic_keywords_count=89, est_organic_traffic_value_usd=40.0)

_MEGA_MARKETPLACES = [
    {"domain": "amazon.com", "discovery_source": "competitors_domain", "organic_keywords_count": 39_044_800,
     "est_organic_traffic_value_usd": 285_227_104, "intersections": 74},
    {"domain": "ebay.com", "discovery_source": "competitors_domain", "organic_keywords_count": 28_054_017,
     "est_organic_traffic_value_usd": 76_648_981, "intersections": 61},
    {"domain": "etsy.com", "discovery_source": "competitors_domain", "organic_keywords_count": 13_980_014,
     "est_organic_traffic_value_usd": 23_213_074, "intersections": 58},
]
_NICHE_PEER = {
    "domain": "niche-menswear.com", "discovery_source": "competitors_domain",
    "organic_keywords_count": 240, "est_organic_traffic_value_usd": 120.0, "intersections": 12,
}


def test_size_band_alone_rejects_mega_marketplaces_when_blocklist_disabled():
    """The structural fix: with the blocklist disabled, the size-band filter alone
    must still reject Amazon/eBay/Etsy — proving the fix isn't just a longer denylist."""
    candidates = [*_MEGA_MARKETPLACES, _NICHE_PEER]
    with patch("app.competitor_benchmark.filters.blocklist_match", return_value=None):
        kept, rejected = apply_filters(candidates, _STORE, market_language_code="en")

    kept_domains = {c.domain for c in kept}
    rejected_by_domain = {r.domain: r.reason_code for r in rejected}

    assert kept_domains == {"niche-menswear.com"}
    for mega in _MEGA_MARKETPLACES:
        assert rejected_by_domain[mega["domain"]] == "size_band"


def test_blocklist_alone_still_catches_them_when_store_metrics_are_missing():
    """When the store's own DataForSEO lookup fails (no k_store to compare against),
    the blocklist is the safety net that still keeps known mega-platforms out."""
    store_no_metrics = StoreMetrics(domain="olafhussein.com", organic_keywords_count=None, est_organic_traffic_value_usd=None)
    candidates = [*_MEGA_MARKETPLACES, _NICHE_PEER]

    kept, rejected = apply_filters(candidates, store_no_metrics, market_language_code="en")

    kept_domains = {c.domain for c in kept}
    rejected_by_domain = {r.domain: r.reason_code for r in rejected}

    assert "niche-menswear.com" in kept_domains
    for mega in _MEGA_MARKETPLACES:
        assert rejected_by_domain[mega["domain"]] == "blocklist"


def test_median_fallback_rejects_outlier_when_store_metrics_missing_and_not_on_blocklist():
    """A mega-domain that isn't on the blocklist still gets caught by the
    median-of-candidate-set fallback when the store itself has no keyword count."""
    store_no_metrics = StoreMetrics(domain="somestore.com", organic_keywords_count=None)
    candidates = [
        {"domain": "totally-unlisted-giant.com", "discovery_source": "competitors_domain",
         "organic_keywords_count": 5_000_000, "intersections": 50},
        {"domain": "peer-a.com", "discovery_source": "competitors_domain", "organic_keywords_count": 300, "intersections": 10},
        {"domain": "peer-b.com", "discovery_source": "competitors_domain", "organic_keywords_count": 400, "intersections": 10},
        {"domain": "peer-c.com", "discovery_source": "competitors_domain", "organic_keywords_count": 350, "intersections": 10},
    ]
    kept, rejected = apply_filters(candidates, store_no_metrics, market_language_code="en")

    kept_domains = {c.domain for c in kept}
    rejected_by_domain = {r.domain: r.reason_code for r in rejected}

    assert "totally-unlisted-giant.com" not in kept_domains
    assert rejected_by_domain["totally-unlisted-giant.com"] == "size_band"
    assert {"peer-a.com", "peer-b.com", "peer-c.com"}.issubset(kept_domains)


def test_self_and_same_brand_are_excluded():
    candidates = [
        {"domain": "olafhussein.com", "discovery_source": "competitors_domain", "organic_keywords_count": 89, "intersections": 89},
        {"domain": "shop.olafhussein.nl", "discovery_source": "competitors_domain", "organic_keywords_count": 50, "intersections": 20},
        _NICHE_PEER,
    ]
    kept, rejected = apply_filters(candidates, _STORE, market_language_code="en")
    reasons = {r.domain: r.reason_code for r in rejected}
    assert reasons["olafhussein.com"] == "self"
    assert reasons["shop.olafhussein.nl"] == "same_brand"
    assert "niche-menswear.com" in {c.domain for c in kept}


def test_min_intersections_rejects_coincidental_overlap():
    low_overlap = {"domain": "coincidence.example", "discovery_source": "competitors_domain",
                   "organic_keywords_count": 200, "intersections": 1}
    kept, rejected = apply_filters([low_overlap], _STORE, market_language_code="en")
    assert kept == []
    assert rejected[0].reason_code == "min_intersections"


def test_market_coherence_rejects_incoherent_tld():
    candidate = {"domain": "niche-menswear.ru", "discovery_source": "competitors_domain",
                 "organic_keywords_count": 240, "intersections": 12}
    kept, rejected = apply_filters([candidate], _STORE, market_language_code="en")
    assert kept == []
    assert rejected[0].reason_code == "market_coherence"


def test_size_ratio_is_recorded_on_kept_candidates():
    kept, _ = apply_filters([_NICHE_PEER], _STORE, market_language_code="en")
    assert len(kept) == 1
    assert kept[0].size_ratio_to_store == 240 / 89

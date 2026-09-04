from app.competitor_benchmark.market import brand_label, is_same_brand, resolve_market


def test_com_domain_with_dutch_html_lang_resolves_to_nl_not_default_us():
    """A `.com` store falling through to the US/English default is exactly what
    produced the amazon/ebay/etsy failure for a Dutch store — the market default
    must not win when the page itself signals a real market."""
    pages = [{"url": "https://example.com", "html": '<html lang="nl-NL"><head></head></html>'}]
    result = resolve_market("example.com", pages)
    assert (result.location_code, result.language_code) == (2528, "nl")
    assert result.source == "html_lang"
    assert result.confidence != "low"


def test_cctld_wins_over_everything():
    result = resolve_market("example.nl", pages=None)
    assert (result.location_code, result.language_code) == (2528, "nl")
    assert result.source == "tld"
    assert result.confidence == "high"


def test_no_signals_falls_back_to_default_with_low_confidence():
    result = resolve_market("example.com", pages=[])
    assert (result.location_code, result.language_code) == (2840, "en")
    assert result.source == "default_fallback"
    assert result.confidence == "low"


def test_operator_override_wins_over_everything():
    pages = [{"url": "https://example.com", "html": '<html lang="nl-NL">'}]
    result = resolve_market("example.com", pages, override=(2276, "de"))
    assert (result.location_code, result.language_code) == (2276, "de")
    assert result.source == "operator"
    assert result.confidence == "high"


def test_hreflang_majority_picks_dominant_region():
    pages = [{
        "url": "https://example.com",
        "html": (
            '<link rel="alternate" hreflang="nl-NL">'
            '<link rel="alternate" hreflang="nl-BE">'
            '<link rel="alternate" hreflang="fr-FR">'
        ),
    }]
    result = resolve_market("example.com", pages)
    assert result.language_code == "nl"
    assert result.source == "hreflang"


def test_brand_label_strips_subdomain_prefix_not_brand_name():
    """Regression: the original _brand_label("shop.example.nl") returned "shop",
    which then substring-matched (and silently dropped) any competitor whose domain
    happened to contain "shop" anywhere."""
    assert brand_label("shop.example.nl") == "example"
    assert brand_label("allbirds.com") == "allbirds"
    assert brand_label("allbirdsbenelux.nl") == "allbirdsbenelux"


def test_is_same_brand_matches_regional_storefront():
    assert is_same_brand("allbirds.com", "allbirdsbenelux.nl") is True
    assert is_same_brand("allbirds.com", "shop.allbirdsbenelux.nl") is True


def test_is_same_brand_does_not_match_unrelated_shops():
    assert is_same_brand("allbirds.com", "nike.com") is False
    # the fixed brand_label must not turn "shop" into a false-positive brand match
    assert is_same_brand("shop.storeone.nl", "shop.storetwo.nl") is False

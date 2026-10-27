"""Detector regressions: small HTML/DNS fixtures pinned against false positives and
negatives that reached real reports."""

import asyncio

import pytest

from app.full_audit.analyzers import dns_email
from app.full_audit.analyzers.platform import detect_platform


def _page(html: str, headers: dict | None = None) -> dict:
    return {"url": "https://store.nl/", "html": html, "headers": headers or {}, "load_time_ms": 100}


def test_image_paths_are_not_a_magento_signal():
    html = '<html><body><img src="/image/png/hero.png"><link href="/assets/image/logo.svg"></body></html>'
    result = asyncio.run(detect_platform([_page(html)]))
    assert "magento" not in (result.detected_platform or "").lower()


def test_requirejs_mage_path_still_detects_magento():
    html = '<script>require(["jquery", "mage/cookies"]);</script><script src="/static/version1712/frontend/x.js"></script>'
    result = asyncio.run(detect_platform([_page(html)]))
    assert "magento" in (result.detected_platform or "").lower()


def test_mail_records_are_queried_on_the_apex_not_on_www(monkeypatch):
    queried: list[tuple[str, str]] = []

    async def fake_resolve(domain: str, rdtype: str) -> list[str]:
        queried.append((domain, rdtype))
        return []

    async def fake_registrable_domain(url: str) -> str:
        assert url == "https://www.shop.nl"
        return "shop.nl"

    monkeypatch.setattr(dns_email, "_resolve", fake_resolve)
    monkeypatch.setattr(dns_email, "registrable_domain", fake_registrable_domain)

    asyncio.run(dns_email.analyze_dns_email("https://www.shop.nl"))

    assert ("_dmarc.shop.nl", "TXT") in queried
    assert ("shop.nl", "MX") in queried
    assert not any(domain.startswith("www.") or ".www." in domain for domain, _ in queried)


def test_registrable_domain_falls_back_to_the_host_when_dns_fails(monkeypatch):
    import dns.resolver

    from app.domains import registrable_domain

    def boom(*args, **kwargs):
        raise dns.resolver.NoNameservers()

    monkeypatch.setattr(dns.resolver, "zone_for_name", boom)
    assert asyncio.run(registrable_domain("https://www.shop.nl/collections")) == "shop.nl"


# --- scraper ------------------------------------------------------------------------

def test_error_and_challenge_pages_are_blocked_but_normal_pages_are_not():
    from app.analysis.scraper import block_reason

    assert block_reason(403, "<html>Forbidden</html>") == "HTTP 403"
    assert block_reason(200, "<html><title>Just a moment...</title></html>") is not None
    # Cloudflare injects challenge-platform scripts into normal (large) pages too.
    normal = "<html>" + "x" * 80_000 + '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>cf-chl-</html>'
    assert block_reason(200, normal) is None


def test_every_set_cookie_header_is_seen():
    from app.analysis.scraper import set_cookie_text

    page = {"headers": {"Set-Cookie": "_fbp=last"}, "set_cookies": ["__kla_id=abc", "_fbp=fb.1.2"]}
    text = set_cookie_text(page)
    assert "__kla_id=abc" in text and "_fbp=fb.1.2" in text
    assert set_cookie_text({"headers": {"set-cookie": "a=1"}}) == "a=1"  # old page dicts


# --- tracking -----------------------------------------------------------------------

def test_shopify_web_pixels_count_as_installed_pixels():
    from app.full_audit.analyzers.tracking import detect_tracking

    html = (
        '<script src="https://cdn.shopify.com/s/files/x.js"></script><script>var webPixelsConfigList = ['
        '{"configuration":"{\\"config\\":\\"{\\\\\\"google_tag_ids\\\\\\":[\\\\\\"G-ABC123XYZ\\\\\\"]}\\"}"},'
        '{"configuration":"{\\"pixel_id\\":\\"1234567890123\\"}"}]</script>'
    )
    result = asyncio.run(detect_tracking([_page(html)]))
    assert result.pixels_health == "healthy"
    assert "Shopify Web Pixels" in (result.detection_evidence or "")


def test_a_pixel_that_may_live_in_gtm_is_unconfirmed_not_partial():
    from app.full_audit.analyzers.tracking import detect_tracking

    html = '<script src="https://www.googletagmanager.com/gtag/js?id=G-ABC123XYZ"></script><script>(GTM-ABCD12)</script>'
    result = asyncio.run(detect_tracking([_page(html)]))
    assert result.pixels_health == "to-validate"


def test_consent_default_must_be_the_actual_gtag_call():
    from app.full_audit.analyzers.tracking import _detect_consent_mode_v2

    assert _detect_consent_mode_v2('<select><option value="default"></option></select>', False) == "none"
    assert _detect_consent_mode_v2("gtag('consent','update',{'ad_storage':'granted'}); var x='default';", False) == "v2-incorrect"
    assert _detect_consent_mode_v2(
        "gtag('consent','default',{'ad_storage':'denied','ad_user_data':'denied','ad_personalization':'denied'})", False,
    ) == "v2-correct"


# --- owned channels ---------------------------------------------------------------

def test_klaviyo_email_alone_is_not_sms():
    from app.full_audit.analyzers.owned_channels import _detect_sms

    assert not _detect_sms('<script src="https://static.klaviyo.com/onsite/js/klaviyo.js"></script>')


def test_login_and_contact_forms_are_not_newsletter_signups():
    from app.full_audit.analyzers.owned_channels import _detect_newsletter_capture

    login = '<form action="/account/login"><input type="email" name="customer[email]"><input type="password"></form>'
    contact = '<form action="/contact#contact_form"><input type="email" name="contact[email]"><textarea></textarea></form>'
    assert _detect_newsletter_capture(login + contact)[0] is False

    shopify_newsletter = (
        '<form action="/contact#newsletter"><input type="hidden" name="form_type" value="customer">'
        '<input type="hidden" name="contact[tags]" value="newsletter"><input type="email" name="contact[email]"></form>'
    )
    assert _detect_newsletter_capture(shopify_newsletter)[0] is True


# --- structured data ---------------------------------------------------------------

_PRODUCT_GROUP = """<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
{"@type":["ProductGroup"],"name":"Tee","brand":{"@type":"Brand","name":"X"},"mpn":"T1",
 "hasVariant":[{"@type":"Product","sku":"T1-S","gtin13":"8712345678906",
   "offers":{"@type":"Offer","price":"20"}}],
 "aggregateRating":{"ratingValue":"4.6","reviewCount":"31"}}]}</script>"""


def test_product_group_with_gtin13_on_the_variant_is_complete():
    from app.full_audit.analyzers.product_feeds import analyze_product_feeds

    async def run():
        # feed endpoint probing is network I/O; only the JSON-LD part matters here
        import app.full_audit.analyzers.product_feeds as pf
        return await pf.analyze_product_feeds("https://127.0.0.1:1", [_page(_PRODUCT_GROUP) | {"url": "https://store.nl/products/tee"}])

    result = asyncio.run(run())
    assert result.jsonld_product_complete is True, result.missing_fields


def test_rich_results_see_nested_types_and_ratings():
    from app.full_audit.analyzers.rich_results import _parse_schemas

    types = _parse_schemas(_PRODUCT_GROUP)
    assert {"Product", "ProductGroup", "AggregateRating"} <= types


# --- social proof -----------------------------------------------------------------

def test_review_app_rendered_through_a_shopify_app_block_counts():
    from app.full_audit.analyzers.cro import _detect_social_proof

    html = '<div class="jdgm-widget jdgm-preview-badge" data-id="1"></div>'
    assert _detect_social_proof(html)[0] is True
    assert _detect_social_proof("<p>Mooie producten</p>")[0] is False


# --- express checkout ----------------------------------------------------------------

def test_accelerated_checkout_container_counts_as_express_checkout():
    from app.full_audit.analyzers.checkout import _detect_express_checkout

    assert _detect_express_checkout('<div class="additional-checkout-buttons"><shopify-accelerated-checkout-cart>') != []
    assert _detect_express_checkout('<button>Afrekenen</button>') == []


@pytest.mark.parametrize("html, platform", [
    ('<div class="trustpilot-widget" data-template-id="x"></div>', "Trustpilot"),
    ('<script src="https://widget.trustpilot.com/bootstrap/v5/tp.widget.bootstrap.min.js"></script>', "Trustpilot"),
    ('<script src="https://integrations.etrusted.com/applications/widget.js/v2"></script>', "Trusted Shops"),
    ('<span class="etrusted-review-badge__proof">Zufriedene Kundinnen</span>', "Trusted Shops"),
    ('<etrusted-widget data-etrusted-widget-id="wdg-1"></etrusted-widget>', "Trusted Shops"),
    ('<script src="//widgets.trustedshops.com/js/X1.js"></script>', "Trusted Shops"),
    ('<iframe src="https://www.kiyoh.com/retrieve-widget.html?locationId=1"></iframe>', "Kiyoh"),
    ('<link rel="stylesheet" href="https://www.feedbackcompany.com/widget.css">', "Feedback Company"),
    ('<script>(function(){var s=document.createElement("script");s.src="https://dashboard.webwinkelkeur.nl/webshops/sidebar.js";})()</script>', "WebwinkelKeur"),
    ('<div class="jdgm-widget jdgm-preview-badge" data-id="1"></div>', "Judge.me"),
    ('<div class="klaviyo-star-rating-widget"></div>', "Klaviyo Reviews"),
])
def test_every_review_platform_counts_as_social_proof(html, platform):
    from app.full_audit.analyzers.cro import _detect_social_proof

    assert _detect_social_proof(html) == (True, f"{platform} widget gedetecteerd")


def test_an_installed_review_app_that_renders_nothing_is_not_social_proof():
    from app.full_audit.analyzers.cro import _detect_social_proof

    # Plumelle /nl: the Trusted Shops app is installed, its sections render empty.
    html = (
        "<!-- BEGIN app block: shopify://apps/trusted-shops-reviews-and-more/blocks/trstd-login/1 -->"
        '<section id="shopify-section-template--1__etrusted_review_badge" class="shopify-section"> </section>'
        '<div class="footer__etrusted-badge"></div>'
        '<script type="application/ld+json">{"@type": "Organization", "sameAs": ["https://www.trustpilot.com/review/x.nl"]}</script>'
    )
    assert _detect_social_proof(html) == (False, None)
    assert _detect_social_proof("<p>Mooie producten</p>")[0] is False


def test_german_rating_text_counts():
    from app.full_audit.analyzers.cro import _detect_social_proof

    assert _detect_social_proof("<p>4,8 Sterne aus 1.234 Bewertungen</p>")[0] is True


# --- storefront locale ----------------------------------------------------------------

def test_accept_language_follows_the_storefront_locale_in_the_url():
    from app.analysis.scraper import accept_language_for, url_locale

    assert accept_language_for("https://plumelle.com/de") == "de,en;q=0.8"
    assert accept_language_for("https://shop.com/en-gb/products/x") == "en-GB,en;q=0.9"
    assert accept_language_for("https://shop.com/nl-be/") == "nl-BE,nl;q=0.9,en;q=0.8"
    assert accept_language_for("https://shop.nl/") == "nl-NL,nl;q=0.9,en;q=0.8"
    assert url_locale("https://shop.nl/collections/x") is None
    assert url_locale("https://shop.nl/p/123") is None


def test_a_locale_redirect_is_recorded_and_pages_keep_their_final_url(monkeypatch):
    from app.analysis import scraper

    html = "<html>" + "x" * 60_000 + "</html>"

    async def fake_fetch(session, url):
        assert session.headers["Accept-Language"] == "de,en;q=0.8"
        return html, {}, 200, [], "https://plumelle.com/nl"

    monkeypatch.setattr(scraper, "fetch_page", fake_fetch)
    result = asyncio.run(scraper.scrape_store("https://plumelle.com/de"))
    assert result["locale_redirect"] == "/de → /nl"
    assert result["pages"][0]["url"] == "https://plumelle.com/nl"


def test_review_app_variable_names_in_theme_code_are_not_a_widget():
    from app.full_audit.analyzers.cro import _detect_social_proof

    # Shopify theme code on Plumelle /nl references apps that aren't installed.
    html = "<script>var MetafieldYotpoRating = null; var okendoProduct = null;</script>"
    assert _detect_social_proof(html) == (False, None)

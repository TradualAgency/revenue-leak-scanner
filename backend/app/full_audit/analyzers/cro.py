import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from app.full_audit.analyzers.jsonld import jsonld_nodes, node_types
from app.full_audit.analyzers.performance import lcp_source_caveat, worst_mobile_lcp
from app.full_audit.page_sampling import PAGE_LABELS as _PAGE_LABELS
from app.full_audit.page_sampling import sample_pages_by_type as _sample_pages_by_type
from app.full_audit.schemas import CheckoutFlow, CroObservation, Performance, RichResultsHealth


@dataclass(frozen=True)
class ReviewPlatform:
    # Matched in src/href of script/iframe/a/img/link tags and inside inline <script> text
    # (widgets bootstrapped by a loader snippet).
    domains: tuple[str, ...] = ()
    # Matched in the raw HTML: widget class names and custom elements, i.e. markup that only
    # exists when the widget renders. Never an app slug or a bare section id: an installed
    # app whose block renders nothing (Plumelle's empty `__etrusted_review_badge` sections
    # on /nl) is not social proof.
    markers: tuple[str, ...] = ()


_REVIEW_PLATFORMS: dict[str, ReviewPlatform] = {
    # Third-party review and trust widgets
    "Trustpilot": ReviewPlatform(("trustpilot.com",), ("trustpilot-widget",)),
    "Trusted Shops": ReviewPlatform(
        ("trustedshops", "etrusted.com"), ("<etrusted-widget", "etrusted-review-badge__"),
    ),
    "Kiyoh": ReviewPlatform(("kiyoh.com",)),
    "Klantenvertellen": ReviewPlatform(("klantenvertellen.nl",)),
    "Feedback Company": ReviewPlatform(("feedbackcompany.com",), ("__fbcw__",)),
    "WebwinkelKeur": ReviewPlatform(("webwinkelkeur.nl",)),
    "Reviewmeester": ReviewPlatform(("reviewmeester.nl",)),
    "Reviews.io": ReviewPlatform(("reviews.io", "reviews.co.uk")),
    "Feefo": ReviewPlatform(("feefo.com",)),
    "eKomi": ReviewPlatform(("ekomi.de", "ekomi.com", "ekomiapps")),
    "Google Customer Reviews": ReviewPlatform(markers=("ratingbadge",)),
    "Bazaarvoice": ReviewPlatform(("bazaarvoice.com",), ("data-bv-show",)),
    "PowerReviews": ReviewPlatform(("powerreviews.com",)),
    "Lipscore": ReviewPlatform(("lipscore.com",), ("lipscore-rating", "lipscore-review")),
    "Shopper Approved": ReviewPlatform(("shopperapproved.com",)),
    "Verified Reviews": ReviewPlatform(("verified-reviews.com", "avis-verifies.com", "netreviews")),
    # Shopify review apps. Their widgets often render through theme app blocks with no
    # third-party src at all (assets from cdn.shopify.com/extensions/...), so the markup
    # is what gives them away.
    "Judge.me": ReviewPlatform(("judge.me",), ("jdgm-", "judgeme")),
    "Loox": ReviewPlatform(("loox.io",), ("loox-rating", "loox-reviews")),
    "Okendo": ReviewPlatform(("okendo",), ("okeReviews", "oke-reviews")),
    "Yotpo": ReviewPlatform(("yotpo.com",), ("yotpo-widget", "yotpo-main-widget")),
    "Stamped": ReviewPlatform(("stamped.io",), ("stamped-product-reviews", "stamped-main-widget")),
    "Junip": ReviewPlatform(("junip.co",), ("junip-",)),
    "Shopify Product Reviews": ReviewPlatform(("shopify.com/product-reviews",), ("spr-badge", "shopify-product-reviews")),
    "Klaviyo Reviews": ReviewPlatform(markers=("klaviyo-star-rating-widget", "klaviyo-reviews-")),
    "Fera": ReviewPlatform(("fera.ai",)),
    "Ali Reviews": ReviewPlatform(("alireviews",)),
    "Rivyo": ReviewPlatform(("rivyo",)),
    "Opinew": ReviewPlatform(("opinew.com",)),
    "Ryviu": ReviewPlatform(("ryviu",)),
}

_URL_IN_SCRIPT = re.compile(r"""(?:https?:)?//[\w.-]+\.[a-z]{2,}[^\s"'<>)]*""", re.IGNORECASE)

_RATING_PATTERN = re.compile(
    r"""(\d[.,]?\d?)\s*(sterren|stars|sterne|étoiles|stelle|estrellas|\/5|\/10)|   # 4.8 sterren, 4,8 Sterne, 4/5
        \b(\d{2,})\s+(reviews?|beoordelingen|ervaringen|klanten|bewertungen|rezensionen|avis|recensioni|reseñas|opiniones)\b""",
    re.VERBOSE | re.IGNORECASE,
)

_SP_EST_IMPACT = {
    "pdp": (
        "High — winkels met zichtbare reviews zien 15-20% hogere add-to-cart rates. "
        "Social proof op PDP is de directe vertrouwensdrempel voor een aankoop."
    ),
    "collection": (
        "Medium — review badges op collection-tiles verhogen click-through naar PDP "
        "en reduceren bounce op categoriepagina's."
    ),
    "homepage": (
        "High — trust signals op de homepage reduceren bounce rate voor nieuwe bezoekers aantoonbaar. "
        "Ontbrekend sociaal bewijs verhoogt de drempel voor een eerste aankoop."
    ),
}


def _detect_social_proof(html: str, has_aggregate_rating: bool = False) -> tuple[bool, str | None]:
    """Return (detected, evidence). Three cascading signals:
    1. Known review platform (_REVIEW_PLATFORMS): widget domain or rendered markup
    2. AggregateRating JSON-LD (passed in from rich_results)
    3. Rating-number + label pattern in text (strict regex, not loose keywords)
    """
    # Signal 1: a review platform's widget script/iframe/link, or its rendered markup
    soup = BeautifulSoup(html, "lxml")
    sources: list[str] = []
    for tag in soup.find_all(["script", "iframe", "a", "img", "link"]):
        sources.append((str(tag.get("src", "")) + str(tag.get("href", "")) + str(tag.get("data-src", ""))).lower())
        # URLs in inline loader snippets count, bare words don't: themes ship code like
        # `var okendoProduct = null` for apps that aren't installed. JSON-LD doesn't
        # either (a `sameAs` profile link isn't a widget).
        if tag.name == "script" and not tag.get("src") and "json" not in str(tag.get("type", "")):
            sources.extend(u.lower() for u in _URL_IN_SCRIPT.findall(tag.get_text()))
    for name, platform in _REVIEW_PLATFORMS.items():
        if any(domain in src for domain in platform.domains for src in sources):
            return True, f"{name} widget gedetecteerd"
        if any(marker in html for marker in platform.markers):
            return True, f"{name} widget gedetecteerd"

    # Signal 2: structured data — site-wide flag, or a rating nested in this page's JSON-LD
    if has_aggregate_rating or any(
        "AggregateRating" in node_types(n) or isinstance(n.get("aggregateRating"), dict)
        for n in jsonld_nodes(html)
    ):
        return True, "AggregateRating schema aanwezig"

    # Signal 3: rating number + label strict pattern
    text = soup.get_text(separator=" ")
    if _RATING_PATTERN.search(text):
        return True, "rating-cijfer patroon gevonden in paginatekst"

    return False, None


def make_cro_observations(
    pages: list[dict],
    performance: Performance | None,
    checkout: CheckoutFlow | None,
    rich_results: RichResultsHealth | None = None,
) -> list[CroObservation]:
    observations: list[CroObservation] = []

    # 1. LCP check — the same worst-of-field-and-money-page figure the revenue model
    # and the headline use, so the three can't quote different load times.
    if performance:
        lcp, lcp_source = worst_mobile_lcp(performance)
        caveat = lcp_source_caveat(performance, lcp_source)
        if lcp and lcp > 4000:
            observations.append(CroObservation(
                page="Homepage (mobile)",
                observation=f"Mobile LCP is {lcp / 1000:.1f}s{caveat} — well above Google's 'poor' threshold of 4s.",
                severity="high",
                est_impact="High — slow LCP directly causes visitor drop-off before first interaction.",
            ))
        elif lcp and lcp > 2500:
            observations.append(CroObservation(
                page="Homepage (mobile)",
                observation=f"Mobile LCP is {lcp / 1000:.1f}s{caveat} — above Google's 2.5s 'good' threshold.",
                severity="medium",
                est_impact="Medium — every 100ms above 2.5s correlates with ~1% conversion loss.",
            ))

    # 2. Checkout friction
    if checkout and checkout.fields_in_address_form is not None:
        if checkout.fields_in_address_form > 12:
            observations.append(CroObservation(
                page="Checkout",
                observation=f"Address form has {checkout.fields_in_address_form} input fields.",
                severity="high",
                est_impact="High — optimal checkout forms have 8-10 fields; excess fields increase abandonment.",
            ))

    # 3. Social proof — check each relevant page type separately
    has_agg_rating = bool(rich_results and rich_results.has_aggregate_rating)
    if pages:
        sampled = _sample_pages_by_type(pages)
        for ptype in ("pdp", "homepage", "collection"):
            if ptype not in sampled:
                continue
            page = sampled[ptype]
            sp_found, _ = _detect_social_proof(page["html"], has_agg_rating)
            if not sp_found:
                label = _PAGE_LABELS[ptype]
                observations.append(CroObservation(
                    page=label,
                    observation=(
                        f"Geen reviews, sterren of vertrouwenssignalen gedetecteerd op de {label.lower()}. "
                        "Geen review-platform widget (Trustpilot, Kiyoh, etc.), geen AggregateRating schema, "
                        "en geen rating-patroon in paginatekst."
                    ),
                    severity="high",
                    est_impact=_SP_EST_IMPACT.get(ptype, "High — ontbrekend sociaal bewijs verhoogt de aankoopdrempel."),
                ))

    return observations

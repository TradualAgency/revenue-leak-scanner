import re

from bs4 import BeautifulSoup

from app.full_audit.analyzers.jsonld import jsonld_nodes, node_types
from app.full_audit.analyzers.performance import lcp_source_caveat, worst_mobile_lcp
from app.full_audit.page_sampling import PAGE_LABELS as _PAGE_LABELS
from app.full_audit.page_sampling import sample_pages_by_type as _sample_pages_by_type
from app.full_audit.schemas import CheckoutFlow, CroObservation, Performance, RichResultsHealth

_REVIEW_PLATFORM_DOMAINS = [
    "trustpilot.com", "kiyoh.com", "feedbackcompany.com", "trustedshops",
    "judge.me", "loox.io", "yotpo.com", "reviews.io", "okendo", "stamped.io",
    "reviewmeester.nl", "webwinkelkeur.nl", "klantenvertellen.nl",
    "verified-reviews.com", "shopify.com/product-reviews",
]

# Review apps that render through Shopify theme app blocks / app extensions. Their
# widgets often have no third-party src at all (assets come from cdn.shopify.com/
# extensions/...), so the domain check above misses them; their markup and asset
# names don't.
_REVIEW_APP_MARKERS = [
    "jdgm-", "judgeme",                 # Judge.me
    "loox-rating", "loox-reviews",      # Loox
    "okeReviews", "oke-reviews",        # Okendo
    "yotpo-widget", "yotpo-main-widget",
    "stamped-product-reviews", "stamped-main-widget",
    "junip-",                           # Junip
    "spr-badge", "shopify-product-reviews",
]

_RATING_PATTERN = re.compile(
    r"""(\d[.,]?\d?)\s*(sterren|stars|\/5|\/10)|   # 4.8 sterren, 4/5
        \b(\d{2,})\s+(reviews?|beoordelingen|ervaringen|klanten)\b""",
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
    1. Known review-platform domain in src/href attributes
    2. AggregateRating JSON-LD (passed in from rich_results)
    3. Rating-number + label pattern in text (strict regex, not loose keywords)
    """
    # Signal 1: review platform script/iframe
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "iframe", "a", "img"]):
        src = str(tag.get("src", "")) + str(tag.get("href", "")) + str(tag.get("data-src", ""))
        for domain in _REVIEW_PLATFORM_DOMAINS:
            if domain in src.lower():
                return True, f"{domain} widget gedetecteerd"

    # Signal 1b: review app rendered through a Shopify app block / extension
    for marker in _REVIEW_APP_MARKERS:
        if marker in html:
            return True, f"review-app gedetecteerd ({marker})"

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

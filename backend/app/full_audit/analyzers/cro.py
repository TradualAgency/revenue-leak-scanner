from bs4 import BeautifulSoup

from app.full_audit.schemas import CheckoutFlow, CroObservation, Performance


def _has_social_proof_on_page(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ").lower()
    indicators = [
        "review", "rating", "stars", "testimonial", "verified",
        "ster", "beoordeling", "klanten", "ervaringen",
    ]
    return any(indicator in text for indicator in indicators)


def make_cro_observations(
    pages: list[dict],
    performance: Performance | None,
    checkout: CheckoutFlow | None,
) -> list[CroObservation]:
    observations: list[CroObservation] = []

    # 1. LCP check
    if performance and performance.mobile:
        lcp = performance.mobile.lcp_ms
        if lcp and lcp > 4000:
            observations.append(CroObservation(
                page="Homepage (mobile)",
                observation=f"Mobile LCP is {lcp / 1000:.1f}s — well above Google's 'poor' threshold of 4s.",
                severity="high",
                est_impact="High — slow LCP directly causes visitor drop-off before first interaction.",
            ))
        elif lcp and lcp > 2500:
            observations.append(CroObservation(
                page="Homepage (mobile)",
                observation=f"Mobile LCP is {lcp / 1000:.1f}s — above Google's 2.5s 'good' threshold.",
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

    # 3. Social proof on PDP
    pdp_pages = [p for p in pages if "/product" in p.get("url", "")]
    if pdp_pages:
        pdp_has_sp = _has_social_proof_on_page(pdp_pages[0]["html"])
        if not pdp_has_sp:
            observations.append(CroObservation(
                page="Product page (PDP)",
                observation="No social proof signals (reviews, ratings, testimonials) detected on product page.",
                severity="medium",
                est_impact="Medium — stores with visible reviews typically see 15-20% higher add-to-cart rates.",
            ))
    elif pages:
        # Fallback: check homepage
        if not _has_social_proof_on_page(pages[0]["html"]):
            observations.append(CroObservation(
                page="Homepage",
                observation="No social proof signals detected on homepage.",
                severity="low",
                est_impact="Low — trust signals on homepage reduce bounce rate for new visitors.",
            ))

    return observations

import re

from bs4 import BeautifulSoup

from app.full_audit.page_sampling import sample_pages_by_type
from app.full_audit.schemas import EuComplianceHealth

_STRIKETHROUGH_TAGS = ("s", "del", "strike")
_STRIKETHROUGH_CLASS_HINTS = ("compare-at-price", "was-price", "price--compare", "original-price", "price-was")

_LOWEST_PRICE_PATTERNS = [
    # Dutch
    "laagste prijs van de afgelopen 30 dagen", "laagste prijs in de afgelopen 30 dagen",
    "laagste prijs van de voorgaande 30 dagen",
    # English
    "lowest price in the last 30 days", "lowest price of the last 30 days",
    "lowest price over the past 30 days",
    # German (common on multilingual NL/BE/DE stores)
    "niedrigster preis der letzten 30 tage",
]

_GPSR_PATTERNS = [
    "verantwoordelijke marktdeelnemer", "responsible person", "responsible economic operator",
    "verantwortliche person", "producent contactgegevens", "manufacturer contact",
    "importeur:", "importer:", "fabrikant:", "manufacturer:",
]


def _price_looking_text(text: str) -> bool:
    return bool(re.search(r"[€$£]\s?\d|\d[.,]\d{2}\s?(eur|usd|€)", text, re.IGNORECASE))


def _detect_strikethrough_price(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    for tag_name in _STRIKETHROUGH_TAGS:
        for tag in soup.find_all(tag_name):
            if _price_looking_text(tag.get_text()):
                return True
    for tag in soup.find_all(True):
        classes = " ".join(tag.get("class", [])).lower()
        if any(hint in classes for hint in _STRIKETHROUGH_CLASS_HINTS) and _price_looking_text(tag.get_text()):
            return True
    return False


def _detect_lowest_price_disclosure(html: str) -> bool:
    text = BeautifulSoup(html, "lxml").get_text(separator=" ").lower()
    return any(pattern in text for pattern in _LOWEST_PRICE_PATTERNS)


def _detect_gpsr_mention(all_html: str) -> bool:
    text = BeautifulSoup(all_html, "lxml").get_text(separator=" ").lower()
    return any(pattern in text for pattern in _GPSR_PATTERNS)


async def analyze_eu_compliance(pages: list[dict]) -> EuComplianceHealth | None:
    if not pages:
        return None

    sampled = sample_pages_by_type(pages)
    pdp = sampled.get("pdp")
    if not pdp:
        return EuComplianceHealth(
            notes="Geen productpagina gevonden in de gescrapete set — Omnibus-signaal niet te bepalen.",
        )

    pdp_html = pdp.get("html", "")
    has_strikethrough = _detect_strikethrough_price(pdp_html)
    has_disclosure = _detect_lowest_price_disclosure(pdp_html) if has_strikethrough else None
    omnibus_risk = (has_strikethrough and not has_disclosure) if has_strikethrough else None

    all_html = "\n".join(p.get("html", "") for p in pages)
    gpsr_mentioned = _detect_gpsr_mention(all_html)

    evidence_parts = []
    if has_strikethrough:
        evidence_parts.append(
            "Afgeprijsde prijs gevonden op PDP" + (
                " zonder 'laagste prijs 30 dagen'-vermelding in de buurt" if omnibus_risk else
                " mét 'laagste prijs 30 dagen'-vermelding"
            )
        )
    if gpsr_mentioned:
        evidence_parts.append("Vermelding van verantwoordelijke partij/fabrikant gevonden")

    return EuComplianceHealth(
        pdp_sampled_url=pdp.get("url"),
        has_strikethrough_price=has_strikethrough,
        has_lowest_price_disclosure=has_disclosure,
        omnibus_risk_signal=omnibus_risk,
        gpsr_responsible_person_mentioned=gpsr_mentioned if gpsr_mentioned else None,
        evidence="; ".join(evidence_parts) if evidence_parts else None,
        notes=(
            "Heuristische signalen, geen juridisch oordeel. Afwezigheid van een gevonden "
            "vermelding betekent 'niet gezien in de gescrapete pagina's', niet 'ontbreekt' — "
            "GPSR-informatie staat vaak op een footer- of legal-pagina die mogelijk niet is "
            "meegescraped. Laat een jurist de daadwerkelijke naleving beoordelen."
        ),
    )

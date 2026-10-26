"""Deterministic action list: what to do about each finding, how much work it is, and
when to measure again.

Effort and ownership come from this table, never from an LLM, so the ranking a client
sees ("most euros per day of work first") is reproducible. Several findings can share
one action — a faster mobile page fixes both the organic LCP finding and the paid-click
bounce finding — so the table maps finding_id -> action key, and the list groups by it.
Their euros add up without double counting: those findings already split their
exposure (organic vs. paid) inside the registry.

Every finding_id registered anywhere must appear in FINDING_ACTIONS;
tests/test_actions.py fails the build when a new finding ships without one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.full_audit.schemas import ActionItem, FindingOut

Effort = Literal["S", "M", "L"]


@dataclass(frozen=True)
class ActionSpec:
    title_nl: str
    what_to_do_nl: str
    effort: Effort  # S: ≤2 werkdagen, M: 2-10, L: >10
    effort_days_low: float
    effort_days_high: float
    owner: str
    remeasure_metric: str
    remeasure_after_days: int


ACTIONS: dict[str, ActionSpec] = {
    "speed.lcp": ActionSpec(
        title_nl="Laadtijd op mobiel onder 2,5 seconden brengen",
        what_to_do_nl=(
            "Zorg dat de hoofdafbeelding en producten direct zichtbaar zijn: zware "
            "afbeeldingen verkleinen en voorladen, scripts die het laden blokkeren "
            "uitstellen of verwijderen, en apps die niemand gebruikt uitzetten."
        ),
        effort="M", effort_days_low=5, effort_days_high=15, owner="developer",
        # CrUX field data is a rolling 28-day window: re-measuring sooner mixes old visits in.
        remeasure_metric="Laadtijd mobiel (LCP, echte bezoekers via PageSpeed)",
        remeasure_after_days=28,
    ),
    "speed.inp": ActionSpec(
        title_nl="Pagina direct laten reageren op klikken",
        what_to_do_nl=(
            "Zware scripts (chat, pop-ups, tracking) pas laden na de eerste interactie "
            "of verwijderen, zodat knoppen en menu's meteen reageren."
        ),
        effort="M", effort_days_low=3, effort_days_high=8, owner="developer",
        remeasure_metric="Reactietijd (INP, en TBT in de labmeting)",
        remeasure_after_days=28,
    ),
    "layout.cls": ActionSpec(
        title_nl="Verspringende elementen vastzetten",
        what_to_do_nl=(
            "Geef afbeeldingen, banners en widgets vaste afmetingen, zodat de pagina niet "
            "verschuift terwijl bezoekers willen klikken."
        ),
        effort="S", effort_days_low=1, effort_days_high=2, owner="developer",
        remeasure_metric="Layoutverschuiving (CLS)",
        remeasure_after_days=28,
    ),
    "checkout.guest": ActionSpec(
        title_nl="Bestellen zonder account mogelijk maken",
        what_to_do_nl=(
            "Zet gastbestellingen aan in de checkout-instellingen; bied het aanmaken van "
            "een account pas ná de bestelling aan."
        ),
        effort="S", effort_days_low=0.5, effort_days_high=1, owner="Shopify-beheer",
        remeasure_metric="Checkout-conversie (bezoekers checkout → bestelling)",
        remeasure_after_days=30,
    ),
    "checkout.fields": ActionSpec(
        title_nl="Adresformulier inkorten",
        what_to_do_nl=(
            "Schrap of maak optionele velden die niet nodig zijn voor levering, en zet "
            "adres-aanvulling op postcode en huisnummer aan."
        ),
        effort="S", effort_days_low=1, effort_days_high=2, owner="developer",
        remeasure_metric="Aantal velden in het adresformulier en checkout-conversie",
        remeasure_after_days=30,
    ),
    "checkout.express": ActionSpec(
        title_nl="Snelle betaalknoppen controleren",
        what_to_do_nl=(
            "Controleer op een telefoon of Shop Pay, Apple Pay en Google Pay in de "
            "winkelmand en checkout verschijnen; zet ze aan in de betaalinstellingen als ze ontbreken."
        ),
        effort="S", effort_days_low=0.5, effort_days_high=1, owner="Shopify-beheer",
        remeasure_metric="Express-betaalknoppen zichtbaar in winkelmand en checkout",
        remeasure_after_days=7,
    ),
    "cro.social_proof": ActionSpec(
        title_nl="Reviews en sterren zichtbaar maken",
        what_to_do_nl=(
            "Toon reviews en een gemiddelde score op product- en collectiepagina's, en "
            "geef die score door aan Google zodat de sterren ook in zoekresultaten staan."
        ),
        effort="M", effort_days_low=2, effort_days_high=5, owner="marketeer",
        remeasure_metric="Conversie op productpagina's en reviewsterren in Google",
        remeasure_after_days=30,
    ),
    "tracking.attribution": ActionSpec(
        title_nl="Meting laten valideren",
        what_to_do_nl=(
            "Laat pixels, toestemmingsinstellingen (consent mode v2) en server-side meting "
            "controleren, zodat advertentieplatformen zien welke klikken omzet opleveren."
        ),
        effort="M", effort_days_low=3, effort_days_high=6, owner="marketeer",
        remeasure_metric="Aandeel bestellingen dat in de advertentieplatformen terugkomt",
        remeasure_after_days=30,
    ),
    "shipping.clarity": ActionSpec(
        title_nl="Verzendkosten op de productpagina tonen",
        what_to_do_nl=(
            "Zet de verzendkosten en de grens voor gratis verzending bij de koopknop en in "
            "de aankondigingsbalk, zodat ze in de checkout geen verrassing meer zijn."
        ),
        effort="S", effort_days_low=0.5, effort_days_high=1, owner="Shopify-beheer",
        remeasure_metric="Afhakers tussen winkelmand en checkout",
        remeasure_after_days=30,
    ),
    "cart.free_shipping_bar": ActionSpec(
        title_nl="Voortgangsbalk naar gratis verzending in de winkelmand",
        what_to_do_nl="Laat in de winkelmand zien hoeveel er nog bij moet voor gratis verzending.",
        effort="S", effort_days_low=0.5, effort_days_high=1, owner="Shopify-beheer",
        remeasure_metric="Gemiddelde bestelwaarde",
        remeasure_after_days=30,
    ),
    "cart.cross_sell": ActionSpec(
        title_nl="Aanvullende producten in de winkelmand aanbieden",
        what_to_do_nl="Toon één tot drie passende, goedkopere aanvullingen in de winkelmand.",
        effort="S", effort_days_low=1, effort_days_high=2, owner="marketeer",
        remeasure_metric="Gemiddelde bestelwaarde en producten per bestelling",
        remeasure_after_days=30,
    ),
    "catalog.stock": ActionSpec(
        title_nl="Uitverkochte producten afhandelen",
        what_to_do_nl=(
            "Verberg uitverkochte producten uit collecties of zet ze onderaan, en bied een "
            "'mail me bij voorraad'-optie of alternatieven aan."
        ),
        effort="S", effort_days_low=1, effort_days_high=2, owner="Shopify-beheer",
        remeasure_metric="Aandeel uitverkochte producten in collecties",
        remeasure_after_days=14,
    ),
    "catalog.content": ActionSpec(
        title_nl="Productpagina's compleet maken",
        what_to_do_nl="Vul ontbrekende productfoto's en beschrijvingen aan, te beginnen bij de best verkopende producten.",
        effort="M", effort_days_low=2, effort_days_high=6, owner="marketeer",
        remeasure_metric="Producten zonder foto of beschrijving",
        remeasure_after_days=30,
    ),
    "owned.email_capture": ActionSpec(
        title_nl="Een eigen klantenlijst opbouwen",
        what_to_do_nl=(
            "Zet een nieuwsbriefaanmelding (met een reden om je aan te melden) in de footer "
            "en als pop-up, gekoppeld aan een welkomst- en verlaten-winkelmandflow."
        ),
        effort="M", effort_days_low=2, effort_days_high=5, owner="marketeer",
        remeasure_metric="Nieuwe aanmeldingen per maand",
        remeasure_after_days=30,
    ),
    "mobile.conversion": ActionSpec(
        title_nl="Mobiele conversie apart onderzoeken",
        what_to_do_nl=(
            "Loop de aankoop op een telefoon zelf door en vergelijk het in analytics per stap "
            "met desktop; de laadtijd-actie hierboven is meestal de eerste stap."
        ),
        effort="S", effort_days_low=1, effort_days_high=2, owner="marketeer",
        remeasure_metric="Conversieratio mobiel t.o.v. desktop",
        remeasure_after_days=30,
    ),
    "seo.structured_data": ActionSpec(
        title_nl="Prijs, voorraad en sterren doorgeven aan Google",
        what_to_do_nl="Voeg productgegevens en reviewscores toe als gestructureerde gegevens op productpagina's.",
        effort="S", effort_days_low=1, effort_days_high=2, owner="developer",
        remeasure_metric="Rich results in Google Search Console",
        remeasure_after_days=30,
    ),
    "feed.merchant": ActionSpec(
        title_nl="Productgegevens klaarmaken voor Google Shopping",
        what_to_do_nl="Vul GTIN, merk en SKU aan voor alle producten en koppel de catalogus aan Google Merchant Center.",
        effort="M", effort_days_low=2, effort_days_high=5, owner="marketeer",
        remeasure_metric="Goedgekeurde producten in Merchant Center",
        remeasure_after_days=14,
    ),
}

FINDING_ACTIONS: dict[str, str] = {
    "perf.lcp_mobile": "speed.lcp",
    "adtraffic.post_click_bounce": "speed.lcp",
    "gap.lcp_mobile": "speed.lcp",
    "perf.inp_mobile": "speed.inp",
    "gap.inp_mobile": "speed.inp",
    "perf.cls_mobile": "layout.cls",
    "checkout.no_guest": "checkout.guest",
    "checkout.address_fields": "checkout.fields",
    "gap.checkout_address_fields": "checkout.fields",
    "checkout.no_express_pay": "checkout.express",
    "gap.checkout_express": "checkout.express",
    "cro.social_proof": "cro.social_proof",
    "gap.schema_aggregate_rating": "cro.social_proof",
    "gap.tracking_attribution": "tracking.attribution",
    "shipping.cost_clarity": "shipping.clarity",
    "cart.no_free_shipping_bar": "cart.free_shipping_bar",
    "cart.no_cross_sell": "cart.cross_sell",
    "catalog.out_of_stock": "catalog.stock",
    "catalog.missing_content": "catalog.content",
    "owned.no_email_capture": "owned.email_capture",
    "perf.mobile_gap": "mobile.conversion",
    "seo.rich_results": "seo.structured_data",
    "feed.merchant_ready": "feed.merchant",
}

_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _round_100(value: float) -> float:
    """Shown next to layer totals that are rounded to €100 — match them."""
    return float(round(value / 100) * 100)


def build_action_list(findings: list[FindingOut]) -> list[ActionItem]:
    """Group findings into actions and rank them: priced actions by euros per day of
    effort (high bound over high bound — the conservative ratio), then unpriced ones by
    their most severe finding."""
    grouped: dict[str, list[FindingOut]] = {}
    for f in findings:
        if f.kind != "revenue" or f.status == "good":
            continue
        key = FINDING_ACTIONS.get(f.finding_id)
        if key is not None:
            grouped.setdefault(key, []).append(f)

    items: list[ActionItem] = []
    for key, group in grouped.items():
        spec = ACTIONS[key]
        priced = [f for f in group if f.priced]
        basis = priced or group
        items.append(ActionItem(
            action_key=key,
            title_nl=spec.title_nl,
            what_to_do_nl=spec.what_to_do_nl,
            effort=spec.effort,
            effort_days_low=spec.effort_days_low,
            effort_days_high=spec.effort_days_high,
            owner=spec.owner,
            remeasure_metric=spec.remeasure_metric,
            remeasure_after_days=spec.remeasure_after_days,
            finding_ids=[f.finding_id for f in group],
            monthly_low=_round_100(sum(f.monthly_low or 0 for f in priced)) if priced else None,
            monthly_high=_round_100(sum(f.monthly_high or 0 for f in priced)) if priced else None,
            priced=bool(priced),
            confidence=min((f.confidence for f in basis), key=_CONFIDENCE_ORDER.__getitem__),
            verify_manually=all(f.verify_manually for f in group),
            priority=min((f.priority for f in group), key=_PRIORITY_ORDER.__getitem__),
        ))

    def rank(item: ActionItem) -> tuple:
        if item.priced:
            return (0, -(item.monthly_high or 0) / item.effort_days_high)
        return (1, _PRIORITY_ORDER[item.priority])

    return sorted(items, key=rank)

"""Shared revenue-model constants.

`revenue_leak.py` and `ad_traffic.py` both derive euro figures from the same
handful of assumptions (default revenue, AOV bucket, benchmark conversion
rate). They used to define these independently and had drifted apart — most
notably two different "benchmark CVR" values (2% vs 3%) feeding the same
report. Centralising them here means the report can no longer disagree with
itself about what "average" means.
"""

from __future__ import annotations

from dataclasses import dataclass

# Used whenever the operator hasn't supplied a real annual revenue figure.
DEFAULT_ANNUAL_REVENUE_EUR = 108_000.0  # = €9k/mnd legacy benchmark

# Assumed ad spend as a share of monthly revenue, used to size "wasted ad
# spend" euro figures when the operator hasn't supplied real spend.
AD_SPEND_SHARE_OF_REVENUE = 0.15

# NOTE: the single flat "benchmark CVR" that used to live here (BENCHMARK_CR) has
# been replaced by FUNNEL_CHAIN_CR below, which is derived from the funnel stage
# rates instead of being its own independent guess — see funnel.py. Both
# revenue_leak.py and ad_traffic.py build the same FunnelModel from the same
# inputs now, which is the thing that actually prevents them from disagreeing.


def aov_for_monthly_revenue(monthly_revenue_eur: float) -> float:
    """Bucketed AOV guess used only when no real AOV is supplied."""
    if monthly_revenue_eur < 50_000:
        return 75.0
    if monthly_revenue_eur < 250_000:
        return 95.0
    return 120.0


# ---------------------------------------------------------------------------
# Funnel model constants (analyzers/funnel.py, revenue_leak_rules.py)
#
# The revenue-leak model used to price findings as `count * arbitrary_eur *
# (monthly_revenue / 9_000)` — a fixed price per finding calibrated for a
# €108k/yr store, linearly rescaled. Nothing about the finding itself, or
# about which part of the funnel it affects, entered the calculation. The
# funnel model below replaces that: every euro figure is
# `funnel.monthly_revenue_eur * exposure_share * relative_uplift`, where
# `exposure_share` is the fraction of a funnel stage's traffic the finding
# actually touches, and `relative_uplift` is a cited, bounded estimate of how
# much that finding depresses conversion at that stage.
# ---------------------------------------------------------------------------

# session -> product_view -> add_to_cart -> reach_checkout -> purchase
# Placeholder benchmark exit rates for a "typical" Shopify DTC store. These are
# NOT independently verified against the cited sources yet — see CITATIONS
# below. They only set the *shape* of the funnel; `_calibrate_funnel_stages`
# in funnel.py rescales them so the chain always multiplies out to the real
# (operator-supplied or derived) conversion rate. Getting these wrong changes
# which stage a fixed uplift is attributed to, not the store's headline
# revenue number.
FUNNEL_STAGE_RATES: dict[str, float] = {
    "session_to_product_view": 0.45,     # LITTLEDATA_SHOPIFY_BENCHMARKS — VERIFY
    "product_view_to_cart": 0.16,        # LITTLEDATA_SHOPIFY_BENCHMARKS — VERIFY
    "cart_to_checkout": 0.45,            # BAYMARD_CART_ABANDONMENT — VERIFY
    "checkout_to_purchase": 0.55,        # BAYMARD_CHECKOUT_ABANDONMENT — VERIFY
}

FUNNEL_CHAIN_CR = (
    FUNNEL_STAGE_RATES["session_to_product_view"]
    * FUNNEL_STAGE_RATES["product_view_to_cart"]
    * FUNNEL_STAGE_RATES["cart_to_checkout"]
    * FUNNEL_STAGE_RATES["checkout_to_purchase"]
)

# "~70% of DTC traffic is mobile" is widely repeated but has no single citable
# source — treat as a rough default, not a benchmark. Prefer an operator
# input when one becomes available.
MOBILE_SHARE_DEFAULT = 0.70

# Share of sessions assumed to arrive via paid channels when SE Ranking has no
# paid/organic split. Used to avoid double-charging the same sessions in both
# the ad-traffic bounce model and the generic performance findings.
PAID_SHARE_DEFAULT = 0.30

# Fraction of PDP/collection sessions a page-level CRO finding (e.g. missing
# social proof) is assumed to reach. No independent source — internal
# estimate, kept deliberately conservative.
PDP_TRAFFIC_SHARE_DEFAULT = 0.35

# Per-stage ceilings on the SUM of relative uplifts attributed to a single
# funnel stage. These are sanity guards, not price caps: if the sum of a
# stage's findings would exceed the ceiling, every finding in that stage is
# scaled down proportionally (not clamped to a constant) and a ModelWarning
# is raised — binding is treated as a sign the rule table is over-claiming,
# never as a silent substitute value.
STAGE_UPLIFT_CEILINGS: dict[str, float] = {
    "session": 0.30,
    "product_view": 0.25,
    "add_to_cart": 0.25,
    "reach_checkout": 0.35,  # BAYMARD: a full checkout redesign can gain ~35% — the
                             # ceiling for the whole stage, never a single finding
}

# Report-wide backstop: total claimed uplift (high bound) must never exceed
# this share of modelled monthly revenue, regardless of how many findings
# stack up.
GLOBAL_UPLIFT_CEILING = 0.50


# ---------------------------------------------------------------------------
# Uplift curves shared by the absolute model (revenue_leak.py) and the
# gap-to-market model (competitor_benchmark/gap_pricing.py). They used to be
# written out inline in both places and had drifted: the gap model priced
# TBT linearly per 100ms while the absolute model used a step function. One
# definition means "how much does X seconds/ms of slowness cost" has one
# answer; only the reference point (Google's threshold vs. the market) differs.
# ---------------------------------------------------------------------------

# LCP: extrapolated from DELOITTE_MS_MILLIONS (see its our_interpretation) —
# 2-5% per second over the reference, capped at 10% / 25%.
LCP_UPLIFT_PER_S = (0.02, 0.05)
LCP_UPLIFT_CAP = (0.10, 0.25)

# INP, measured via its lab proxy TBT: INTERNAL_ESTIMATE, a two-step curve.
# Google's "good" TBT threshold is 200ms; >300ms over it (i.e. >500ms absolute)
# is the severe step.
INP_GOOD_TBT_MS = 200.0
INP_SEVERE_OVER_MS = 300.0
INP_UPLIFT_MILD = (0.01, 0.03)
INP_UPLIFT_SEVERE = (0.03, 0.06)


def lcp_uplift(seconds_over_reference: float) -> tuple[float, float] | None:
    """(low, high) relative conversion uplift for an LCP this many seconds over the
    reference, or None when it isn't over."""
    if seconds_over_reference <= 0:
        return None
    return (
        min(LCP_UPLIFT_CAP[0], seconds_over_reference * LCP_UPLIFT_PER_S[0]),
        min(LCP_UPLIFT_CAP[1], seconds_over_reference * LCP_UPLIFT_PER_S[1]),
    )


def inp_uplift(ms_over_reference: float) -> tuple[float, float] | None:
    """(low, high) relative conversion uplift for a TBT this many ms over the
    reference, or None when it isn't over."""
    if ms_over_reference <= 0:
        return None
    return INP_UPLIFT_SEVERE if ms_over_reference > INP_SEVERE_OVER_MS else INP_UPLIFT_MILD


@dataclass(frozen=True)
class Citation:
    """A source backing a benchmark number, plus how far we trust it.

    `verified` is False for every citation shipped in this module — the
    figures are our best-effort placeholders, written down explicitly so
    they can be checked against the source material before this model is
    used to make a real claim to a customer. Treat `verified=False` as
    "needs a human to open the source and confirm the number", not as
    "wrong". See revenue_leak.py module docstring / the project plan for
    the verification task.
    """

    source: str
    figure: str
    applies_to: str
    our_interpretation: str
    verified: bool = False
    url: str | None = None
    # What the client report shows (Dutch, plain language). The English fields above
    # are the working notes for whoever verifies the source.
    figure_nl: str = ""
    note_nl: str = ""
    source_nl: str = ""  # only where `source` is prose rather than a publication title


CITATIONS: dict[str, Citation] = {
    "DELOITTE_MS_MILLIONS": Citation(
        source="Google/Deloitte, \"Milliseconds Make Millions\" (2020)",
        figure="0.1s mobile page-speed improvement correlates with +8.4% retail "
               "conversion and +9.2% AOV",
        applies_to="perf.lcp_mobile uplift range",
        our_interpretation=(
            "The study measures a 0.1s improvement, not the multi-second LCP gaps this "
            "tool detects. Our uplift range is our own extrapolation from that base rate, "
            "clamped well below a linear scale-up — it is not a number from the study."
        ),
        figure_nl="0,1 seconde sneller op mobiel hing samen met +8,4% conversie in retail.",
        note_nl=(
            "Het onderzoek meet een verbetering van 0,1 seconde, niet de meerdere seconden die wij zien. Onze bandbreedte is een eigen, voorzichtige doortrekking van dat cijfer — geen getal uit het onderzoek zelf."
        ),
    ),
    "BAYMARD_CART_ABANDONMENT": Citation(
        source="Baymard Institute, cart abandonment rate meta-study",
        figure="~70% average cart abandonment across ~49 studies",
        applies_to="FUNNEL_STAGE_RATES['cart_to_checkout']",
        our_interpretation="Baymard updates this figure periodically; pin the exact "
                            "value and retrieval date before shipping.",
        figure_nl="Gemiddeld ~70% van de winkelmandjes wordt verlaten (meta-onderzoek over ~49 studies).",
        note_nl=(
            "Gebruikt om de vorm van de funnel te schatten, niet om een bedrag uit te rekenen."
        ),
    ),
    "BAYMARD_CHECKOUT_ABANDONMENT": Citation(
        source="Baymard Institute, checkout usability research",
        figure="~24-26% of checkout abandonment attributed to forced account creation; "
               "a full checkout redesign can recover ~35% of checkout conversion",
        applies_to="checkout.no_guest uplift range; reach_checkout stage ceiling",
        our_interpretation="Two related but distinct figures from Baymard's research — "
                            "verify both independently before use.",
        figure_nl="Verplicht een account aanmaken is een van de grootste redenen om de checkout te verlaten; een volledig herontwerp van de checkout kan tot ~35% conversie terugwinnen.",
        note_nl=(
            "Wij rekenen met een voorzichtige fractie daarvan, afhankelijk van wat we in jullie checkout zagen."
        ),
    ),
    "SPIEGEL_REVIEWS": Citation(
        source="Spiegel Research Center, Northwestern University (2017)",
        figure="Purchase likelihood +270% comparing 5 reviews to 0 reviews "
               "(up to +380% for higher-priced items)",
        applies_to="cro.social_proof uplift (priced only when a product page was sampled and "
                   "showed no review signal of any kind)",
        our_interpretation=(
            "This compares zero reviews to five, not 'our scraper found no review "
            "widget'. We price only the case where a sampled product page shows no "
            "review platform, no review-app markup, no rating schema and no rating text "
            "— and then at 2-5%, a small fraction of the study's effect. Anywhere the "
            "detection is weaker (no PDP sampled), the finding stays low and unpriced."
        ),
        figure_nl="Producten met 5 reviews worden tot 270% vaker gekocht dan producten zonder reviews.",
        note_nl=(
            "We rekenen alleen als een productpagina helemaal geen reviews of sterren toonde, "
            "en dan met 2–5% — een klein deel van het effect uit het onderzoek."
        ),
    ),
    "BAYMARD_EXTRA_COSTS": Citation(
        source="Baymard Institute, reasons for checkout abandonment",
        figure="~48% of shoppers who abandoned a checkout cite extra costs (shipping, "
               "taxes, fees) being too high as a reason — the most-cited reason",
        applies_to="shipping.cost_clarity uplift",
        our_interpretation=(
            "The study measures costs that are too high, not costs that are shown late. "
            "We price only a small 1-3% effect of shipping costs first appearing at "
            "checkout instead of on the product page."
        ),
        figure_nl="~48% van de afhakers in de checkout noemt extra kosten (verzending, belasting) als reden — de meest genoemde reden.",
        note_nl=(
            "Het onderzoek gaat over te hoge kosten, niet over onduidelijke. We rekenen daarom "
            "alleen een klein effect (1–3%) van verzendkosten die pas in de checkout zichtbaar worden."
        ),
    ),
    "LITTLEDATA_SHOPIFY_BENCHMARKS": Citation(
        source="Littledata, Shopify ecommerce benchmarks (published quarterly)",
        figure="Session -> product-view and product-view -> add-to-cart rates",
        applies_to="FUNNEL_STAGE_RATES['session_to_product_view'], "
                   "['product_view_to_cart']",
        our_interpretation="Republished on a rolling basis; pin the specific "
                            "edition/quarter used before shipping.",
        figure_nl="Gemiddelde doorstroom van bezoek naar productpagina en van productpagina naar winkelmand bij Shopify-winkels.",
        note_nl=(
            "Gebruikt om de vorm van de funnel te schatten, niet om een bedrag uit te rekenen."
        ),
    ),
    "MARKET_MEDIAN_BENCHMARK": Citation(
        source="Tradual competitor benchmark — live measurement of the audited store's "
               "own discovered competitor set",
        figure="Store's own metric value vs. the measured median/best of its competitor set",
        applies_to="the REFERENCE POINT of competitor_benchmark gap.* findings",
        our_interpretation=(
            "Verified only as a reference value: it is literally what the store's own "
            "market was observed to achieve (priced only when at least 3 competitors "
            "were measured). The euro elasticity applied to the gap is NOT covered by "
            "this citation — gap findings carry the elasticity's own citation "
            "(e.g. DELOITTE_MS_MILLIONS, unverified) alongside this one."
        ),
        verified=True,
        source_nl="Tradual marktvergelijking — gemeten bij jullie eigen concurrenten",
        figure_nl="Wat jullie eigen concurrenten gemeten halen (mediaan en beste).",
        note_nl=(
            "Het vergelijkingspunt is echt gemeten; de omrekening naar euro's gebruikt dezelfde aannames als de rest van dit rapport."
        ),
    ),
    "TRADUAL_FUNNEL_WALK": Citation(
        source="Tradual funnel walk — observed in a mobile browser session",
        figure="n/a — the blocker itself is observed; the conversion effect is our estimate",
        applies_to="FUNNEL_WALK_RULES (walk.* findings)",
        our_interpretation=(
            "What's verified is that the blocker exists: an agent hit it in a real mobile "
            "session, with a screenshot. The uplift range is an internal estimate, kept small "
            "and applied to mobile sessions only, since one walk can't tell how many "
            "visitors hit it."
        ),
        verified=True,  # honestly labelled: observed problem, internal effect estimate
        source_nl="Tradual funnel-test — gezien in een echte mobiele browsersessie",
        figure_nl="Het probleem is met eigen ogen gezien en vastgelegd met een screenshot.",
        note_nl=(
            "Het effect op conversie is een eigen, voorzichtige schatting, alleen gerekend over mobiele bezoekers."
        ),
    ),
    "INTERNAL_ESTIMATE": Citation(
        source="No external source",
        figure="n/a",
        applies_to="INP/TBT, CLS, and other findings with no published elasticity to "
                   "conversion",
        our_interpretation="Kept deliberately small and capped at confidence=medium; "
                            "never drives more than a minor share of a stage's ceiling.",
        verified=True,  # honestly labelled as internal — nothing to verify externally
        source_nl="Eigen schatting Tradual",
        figure_nl="Geen gepubliceerde bron.",
        note_nl=(
            "Voor deze punten bestaat geen betrouwbaar onderzoek naar het effect op conversie. We houden de schatting bewust klein."
        ),
    ),
}


@dataclass(frozen=True)
class FunnelWalkRule:
    stage: str
    exposure: str  # "mobile": funnel.mobile_share (the walk is mobile) | "all": 1.0
    uplift_low: float
    uplift_high: float
    priority: str
    citation: str = "TRADUAL_FUNNEL_WALK"


# Funnel-agent issue keys that carry a euro figure — and only when the browser layer
# recorded the matching fact (agents/funnel/service.PRICED_EVIDENCE). Every other key
# is shown without one; `shipping_cost_late` maps onto the analyzers' own
# shipping.cost_clarity finding.
FUNNEL_WALK_RULES: dict[str, FunnelWalkRule] = {
    "atc_blocked_by_overlay": FunnelWalkRule("add_to_cart", "mobile", 0.02, 0.06, "high"),
    "atc_no_feedback": FunnelWalkRule("add_to_cart", "mobile", 0.01, 0.03, "medium"),
    "checkout_unreachable": FunnelWalkRule("reach_checkout", "mobile", 0.03, 0.10, "critical"),
}

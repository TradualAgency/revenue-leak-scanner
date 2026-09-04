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
    ),
    "BAYMARD_CART_ABANDONMENT": Citation(
        source="Baymard Institute, cart abandonment rate meta-study",
        figure="~70% average cart abandonment across ~49 studies",
        applies_to="FUNNEL_STAGE_RATES['cart_to_checkout']",
        our_interpretation="Baymard updates this figure periodically; pin the exact "
                            "value and retrieval date before shipping.",
    ),
    "BAYMARD_CHECKOUT_ABANDONMENT": Citation(
        source="Baymard Institute, checkout usability research",
        figure="~24-26% of checkout abandonment attributed to forced account creation; "
               "a full checkout redesign can recover ~35% of checkout conversion",
        applies_to="checkout.no_guest uplift range; reach_checkout stage ceiling",
        our_interpretation="Two related but distinct figures from Baymard's research — "
                            "verify both independently before use.",
    ),
    "SPIEGEL_REVIEWS": Citation(
        source="Spiegel Research Center, Northwestern University (2017)",
        figure="Purchase likelihood +270% comparing 5 reviews to 0 reviews "
               "(up to +380% for higher-priced items)",
        applies_to="cro.social_proof (informational only — not priced)",
        our_interpretation=(
            "This compares zero reviews to five, not 'our scraper could not find a "
            "review widget in server-rendered HTML'. Since our own detection has a "
            "known false-negative rate against client-side-rendered review apps, this "
            "finding stays confidence=low and unpriced rather than borrowing this "
            "multiplier directly."
        ),
    ),
    "LITTLEDATA_SHOPIFY_BENCHMARKS": Citation(
        source="Littledata, Shopify ecommerce benchmarks (published quarterly)",
        figure="Session -> product-view and product-view -> add-to-cart rates",
        applies_to="FUNNEL_STAGE_RATES['session_to_product_view'], "
                   "['product_view_to_cart']",
        our_interpretation="Republished on a rolling basis; pin the specific "
                            "edition/quarter used before shipping.",
    ),
    "MARKET_MEDIAN_BENCHMARK": Citation(
        source="Tradual competitor benchmark — live measurement of the audited store's "
               "own discovered competitor set",
        figure="Store's own metric value vs. the measured median/best of its competitor set",
        applies_to="competitor_benchmark gap.* findings (gap-to-market euro figures)",
        our_interpretation=(
            "This is a first-party measurement, not an extrapolation from a published "
            "study — the cited 'benchmark' is literally what the store's own market was "
            "observed to achieve. Still subject to the same funnel exposure/uplift model "
            "as every other finding, and only priced when at least 3 competitors were "
            "successfully measured on the metric in question."
        ),
        verified=True,
    ),
    "INTERNAL_ESTIMATE": Citation(
        source="No external source",
        figure="n/a",
        applies_to="INP/TBT, CLS, and other findings with no published elasticity to "
                   "conversion",
        our_interpretation="Kept deliberately small and capped at confidence=medium; "
                            "never drives more than a minor share of a stage's ceiling.",
        verified=True,  # honestly labelled as internal — nothing to verify externally
    ),
}

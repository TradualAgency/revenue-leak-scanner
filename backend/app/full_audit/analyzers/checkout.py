import logging
import re
import time

import aiohttp
from bs4 import BeautifulSoup

from app.full_audit.schemas import CheckoutFlow, ObservedFriction

logger = logging.getLogger(__name__)

# A real mobile UA — checkout copy, express-checkout buttons, and field layout can all
# differ from desktop, and mobile is where most DTC traffic actually converts (or doesn't).
MOBILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
    )
}

_PAYMENT_ICONS = [
    "visa", "mastercard", "amex", "american express", "paypal", "ideal",
    "klarna", "afterpay", "apple pay", "google pay", "shop pay", "bancontact",
    "giropay", "sofort", "sepa",
]

# Word-boundary patterns — plain substring matching false-positives on common English
# words: "ideal" matches "our ideal solution", "sepa" matches "separate".
_PAYMENT_PATTERNS = {
    method: re.compile(r"\b" + re.escape(method) + r"\b", re.IGNORECASE)
    for method in _PAYMENT_ICONS
    if method != "ideal"
}
# "ideal" needs its own case-sensitive pattern: the payment method is styled "iDEAL" or
# "IDEAL" everywhere in the wild, while plain lowercase "ideal" is virtually always the
# English word — word boundaries alone don't disambiguate "our ideal solution".
_PAYMENT_PATTERNS["ideal"] = re.compile(r"\b(?:iDEAL|IDEAL)\b")

_EXPRESS_CHECKOUT_MARKERS = {
    "Shop Pay": ["shop-pay-button", "shopify-payment-button", "buy with shop"],
    "Apple Pay": ["apple-pay-button", "buy with apple pay", "applepay"],
    "Google Pay": ["google-pay-button", "buy with g pay", "googlepay"],
    "PayPal Express": ["paypal-express", "buy with paypal", "paypal-button"],
}


def _count_address_fields(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    address_keywords = {"address", "street", "city", "zip", "postal", "state", "province", "country", "phone", "name", "first", "last", "email"}
    count = 0
    for inp in soup.find_all(["input", "select"]):
        inp_type = str(inp.get("type", "text")).lower()
        if inp_type in ("hidden", "submit", "button", "checkbox", "radio"):
            continue
        identifier = " ".join([
            str(inp.get("name", "")),
            str(inp.get("id", "")),
            str(inp.get("placeholder", "")),
            str(inp.get("autocomplete", "")),
        ]).lower()
        if any(kw in identifier for kw in address_keywords):
            count += 1
    return count


_GUEST_POSITIVE = [
    # English
    "continue as guest", "guest checkout", "checkout as guest", "check out as guest",
    "order as guest", "buy as guest", "no account needed", "without an account",
    # Dutch
    "als gast", "doorgaan als gast", "bestellen als gast", "afrekenen als gast",
    "bestellen zonder account", "afrekenen zonder account", "betalen zonder account",
    "doorgaan zonder account", "zonder account bestellen", "zonder account afrekenen",
    "zonder registratie", "geen account nodig", "verder zonder account",
    # German (some NL stores have multilingual checkouts)
    "als gast bestellen", "ohne konto bestellen",
]

_GUEST_NEGATIVE = [
    # English
    "must create an account", "account required to checkout", "login required to checkout",
    "sign in to continue", "log in to continue", "registration required",
    # Dutch
    "account verplicht", "registratie verplicht", "inloggen verplicht",
    "account aanmaken om af te rekenen", "inloggen om af te rekenen",
    "u moet ingelogd zijn", "je moet ingelogd zijn",
]


def _detect_guest_checkout(html: str) -> bool | None:
    """Return True if guest checkout is detected, False if explicitly blocked,
    None if undetermined. Most Shopify stores default to guest unless customer
    accounts are set to required — so absence of phrases ≠ no guest checkout."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ").lower()

    # Explicit negative signals win — if we see account-required copy, no guest
    for phrase in _GUEST_NEGATIVE:
        if phrase in text:
            return False

    # Positive signals — explicit guest copy
    for phrase in _GUEST_POSITIVE:
        if phrase in text:
            return True

    # Heuristic: if there's a checkout email field and no required password field, guest is likely allowed
    email_field = soup.find("input", attrs={"type": "email"}) or soup.find("input", attrs={"name": lambda v: v and "email" in v.lower()})
    password_required = False
    for pw in soup.find_all("input", attrs={"type": "password"}):
        if pw.get("required") is not None or pw.get("aria-required") == "true":
            password_required = True
            break
    if email_field and not password_required:
        return True
    if password_required and not email_field:
        return False

    return None


def _detect_payment_methods(html: str) -> list[str]:
    found = []
    for method, pattern in _PAYMENT_PATTERNS.items():
        if pattern.search(html):
            found.append(method.title())
    return found


def _detect_express_checkout(html: str) -> list[str]:
    lower = html.lower()
    return [name for name, markers in _EXPRESS_CHECKOUT_MARKERS.items() if any(m in lower for m in markers)]


async def _get_first_available_variant(session: aiohttp.ClientSession, base: str) -> int | None:
    """Fetch /products.json (Shopify's public storefront product feed) and return the
    id of the first in-stock variant found. Returns None on non-Shopify stores, empty
    catalogs, or fully out-of-stock catalogs — probe_checkout treats that as unreachable
    rather than falling back to a guess."""
    try:
        async with session.get(f"{base}/products.json?limit=20") as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
    except Exception:
        return None

    products = data.get("products", []) if isinstance(data, dict) else []
    for product in products:
        for variant in product.get("variants", []):
            if variant.get("available"):
                variant_id = variant.get("id")
                if isinstance(variant_id, int):
                    return variant_id
    return None


async def probe_checkout(store_url: str) -> CheckoutFlow:
    base = store_url.rstrip("/")

    friction: list[ObservedFriction] = []
    errors: list[str] = []
    fields_count: int | None = None
    guest_available: bool | None = None
    payment_methods: list[str] = []
    express_checkout: list[str] = []
    redirects: int = 0
    checkout_time_s: float | None = None
    added_to_cart = False

    try:
        connector = aiohttp.TCPConnector(limit=2)
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(headers=MOBILE_HEADERS, connector=connector, timeout=timeout) as session:
            start = time.monotonic()

            variant_id = await _get_first_available_variant(session, base)
            if variant_id is None:
                errors.append("Kon geen bestelbaar product vinden via /products.json — geen (herkenbare) Shopify store of leeg assortiment")
            else:
                # Real add-to-cart via Shopify's public cart API — mirrors what a
                # visitor's browser does on "Add to cart". No order is placed; this only
                # populates the anonymous cart session (cookie), same as browsing does.
                async with session.post(
                    f"{base}/cart/add.js",
                    json={"id": variant_id, "quantity": 1},
                    headers={"Accept": "application/json"},
                ) as add_resp:
                    if add_resp.status >= 400:
                        body = await add_resp.text(errors="replace")
                        errors.append(f"/cart/add.js gaf HTTP {add_resp.status}: {body[:200]}")
                    else:
                        added_to_cart = True

            if added_to_cart:
                # Cart page — express-checkout buttons (Shop Pay/Apple Pay/...) usually live here
                async with session.get(f"{base}/cart", allow_redirects=True) as resp:
                    cart_html = await resp.text(errors="replace")
                    cart_redirects = len(resp.history)
                    express_checkout = _detect_express_checkout(cart_html)
                    cart_payment = _detect_payment_methods(cart_html)
                    if cart_payment:
                        payment_methods = cart_payment

                # With an item in the cart, /checkout should now reach a real checkout —
                # not the "empty cart" redirect the old probe was stuck on.
                async with session.get(f"{base}/checkout", allow_redirects=True) as resp:
                    checkout_html = await resp.text(errors="replace")
                    redirects = cart_redirects + len(resp.history)
                    checkout_time_s = round(time.monotonic() - start, 1)

                    if resp.status == 404:
                        errors.append("Checkout gaf 404, ondanks item in winkelmand")
                    elif resp.status >= 400:
                        errors.append(f"Checkout gaf HTTP {resp.status}")
                    else:
                        checkout_fields = _count_address_fields(checkout_html)
                        if checkout_fields > 0:
                            fields_count = checkout_fields
                        guest_available = _detect_guest_checkout(checkout_html)
                        if not payment_methods:
                            payment_methods = _detect_payment_methods(checkout_html)
                        if not express_checkout:
                            express_checkout = _detect_express_checkout(checkout_html)

    except Exception as exc:
        logger.warning("Checkout probe failed: %s", exc)
        errors.append(f"Checkout probe error: {type(exc).__name__}")

    probe_status: str = "ok" if (added_to_cart and not errors) else "unreachable"

    # Friction rules only mean something once we've actually reached a real checkout —
    # on an unreachable probe there's no reliable signal to rate.
    if probe_status == "ok":
        if fields_count is not None and fields_count > 12:
            friction.append(ObservedFriction(
                step="Address form",
                issue=f"Address form has {fields_count} fields — above optimal 8-10.",
                est_impact="Medium — adds friction and drop-off in mobile checkout.",
            ))
        if guest_available is False:
            friction.append(ObservedFriction(
                step="Login gate",
                issue="No guest checkout option detected.",
                est_impact="High — forced account creation increases abandonment by ~35%.",
            ))
        if redirects > 2:
            friction.append(ObservedFriction(
                step="Navigation",
                issue=f"{redirects} redirects before reaching checkout.",
                est_impact="Low — adds latency and potential drop-off.",
            ))
        if not express_checkout:
            friction.append(ObservedFriction(
                step="Express checkout",
                issue="Geen Shop Pay / Apple Pay / Google Pay knop gedetecteerd op winkelmand of betaalpagina.",
                est_impact="Medium — express checkout verkort de betaalstap en verhoogt conversie op mobiel.",
            ))

    return CheckoutFlow(
        probe_status=probe_status,  # type: ignore[arg-type]
        tested_as_mobile=True,
        fields_in_address_form=fields_count,
        guest_checkout_available=guest_available,
        payment_methods_order=payment_methods[:8],
        express_checkout_methods=express_checkout,
        redirects_before_payment=redirects,
        errors_encountered=errors,
        total_checkout_time_seconds=checkout_time_s,
        observed_friction=friction,
        post_purchase_observations=None,
        notes=(
            "Outside-only checkout probe: product daadwerkelijk in de winkelmand gelegd via "
            "de Shopify cart-API (mobiele user-agent) en doorgestroomd naar checkout. "
            "Geen bestelling geplaatst."
            if probe_status == "ok" else
            "Checkout niet bereikbaar voor outside-only meting — geen bestelbaar product "
            "gevonden, of add-to-cart/checkout is mislukt."
        ),
    )

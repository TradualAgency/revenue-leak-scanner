import logging
import time

import aiohttp
from bs4 import BeautifulSoup

from app.full_audit.schemas import CheckoutFlow, ObservedFriction

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TradualAuditBot/1.0)"}

_PAYMENT_ICONS = [
    "visa", "mastercard", "amex", "american express", "paypal", "ideal",
    "klarna", "afterpay", "apple pay", "google pay", "shop pay", "bancontact",
    "giropay", "sofort", "sepa",
]


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


def _detect_guest_checkout(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ").lower()
    return any(phrase in text for phrase in ["continue as guest", "guest checkout", "checkout as guest", "als gast"])


def _detect_payment_methods(html: str) -> list[str]:
    text = html.lower()
    found = []
    for method in _PAYMENT_ICONS:
        if method in text:
            found.append(method.title())
    return found


async def probe_checkout(store_url: str) -> CheckoutFlow:
    base = store_url.rstrip("/")
    urls_to_probe = [
        f"{base}/cart",
        f"{base}/checkout",
    ]

    friction: list[ObservedFriction] = []
    errors: list[str] = []
    fields_count: int | None = None
    guest_available: bool | None = None
    payment_methods: list[str] = []
    redirects: int = 0
    checkout_time_s: float | None = None

    try:
        connector = aiohttp.TCPConnector(limit=2)
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(headers=HEADERS, connector=connector, timeout=timeout) as session:
            # Probe /cart first for payment icons (Shopify often shows them in cart)
            start = time.monotonic()
            async with session.get(f"{base}/cart", allow_redirects=True) as resp:
                cart_html = await resp.text(errors="replace")
                cart_redirects = len(resp.history)
                cart_payment = _detect_payment_methods(cart_html)
                if cart_payment:
                    payment_methods = cart_payment

            # Probe /checkout
            async with session.get(f"{base}/checkout", allow_redirects=True) as resp:
                checkout_html = await resp.text(errors="replace")
                redirects = cart_redirects + len(resp.history)
                checkout_time_s = round(time.monotonic() - start, 1)

                if resp.status == 404:
                    errors.append("Checkout page returned 404 — may require items in cart")
                elif resp.status >= 400:
                    errors.append(f"Checkout responded with HTTP {resp.status}")

                checkout_fields = _count_address_fields(checkout_html)
                if checkout_fields > 0:
                    fields_count = checkout_fields

                guest_available = _detect_guest_checkout(checkout_html)
                if not payment_methods:
                    payment_methods = _detect_payment_methods(checkout_html)

    except Exception as exc:
        logger.warning("Checkout probe failed: %s", exc)
        errors.append(f"Checkout probe error: {type(exc).__name__}")

    # Rules-based friction
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

    return CheckoutFlow(
        tested_as_mobile=False,
        fields_in_address_form=fields_count,
        guest_checkout_available=guest_available,
        payment_methods_order=payment_methods[:8],
        redirects_before_payment=redirects,
        errors_encountered=errors,
        total_checkout_time_seconds=checkout_time_s,
        observed_friction=friction,
        post_purchase_observations=None,
        notes="Automated outside-only checkout probe. No actual order placed.",
    )

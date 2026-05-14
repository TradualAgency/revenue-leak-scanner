import logging
import re
import ssl
import socket
from datetime import datetime, UTC
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.full_audit.schemas import PciStatus, SecurityCompliance, SslStatus

logger = logging.getLogger(__name__)

_BANNER_SELECTORS = [
    "#cookieyes", ".cookieyes", "[id*='cookieyes']",
    "#onetrust-banner-sdk", ".optanon-alert-box-wrapper",
    "#cookiebanner", ".cookie-banner", "[class*='cookie-banner']",
    ".osano-cm-window", "[class*='osano']",
    "#CybotCookiebotDialog", "[id*='cookiebot']",
    ".iubenda-cs-container", "[class*='iubenda']",
    "[id*='cookie-consent']", "[class*='cookie-consent']",
    "[id*='gdpr']", "[class*='gdpr']",
]

_KNOWN_PSP_REDIRECT_INDICATORS = [
    "pay.google.com", "paypal.com", "checkout.stripe.com",
    "checkout.shopify.com", "buckaroo.nl", "multisafepay",
    "mollie.com", "adyen.com", "worldline",
]


def _check_ssl(hostname: str) -> tuple[SslStatus, str | None]:
    try:
        ctx = ssl.create_default_context()
        conn = ctx.wrap_socket(socket.socket(), server_hostname=hostname)
        conn.settimeout(10)
        conn.connect((hostname, 443))
        cert = conn.getpeercert()
        conn.close()

        if not cert or not isinstance(cert, dict):
            return "valid", "SSL certificate present"

        not_after = cert.get("notAfter")
        if isinstance(not_after, str) and not_after:
            try:
                expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
                days_left = (expires - datetime.now(UTC)).days
                if days_left < 14:
                    return "issues", f"SSL certificate expires in {days_left} days"
                return "valid", f"Valid SSL, expires {not_after} ({days_left} days)"
            except ValueError:
                pass
        return "valid", "SSL certificate present"
    except ssl.SSLError as exc:
        return "issues", f"SSL error: {exc}"
    except Exception as exc:
        logger.debug("SSL check failed for %s: %s", hostname, exc)
        return "issues", f"Could not verify SSL: {type(exc).__name__}"


def _detect_cookie_banner(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for selector in _BANNER_SELECTORS:
        # Simple class/id matching without full CSS selector support
        if selector.startswith("#"):
            if soup.find(id=selector[1:]):
                return f"Banner detected ({selector})"
        elif selector.startswith("."):
            if soup.find(class_=selector[1:]):
                return f"Banner detected ({selector})"
        elif "[" in selector:
            attr_match = re.search(r'\[([^=\]]+)[*=]*["\']?([^"\'=\]]*)["\']?\]', selector)
            if attr_match:
                attr_name, attr_val = attr_match.group(1), attr_match.group(2)
                results = soup.find_all(lambda tag: tag.has_attr(attr_name))  # type: ignore[arg-type]
                for el in results:
                    el_val = str(el.get(attr_name, ""))
                    if not attr_val or attr_val in el_val:
                        return f"Banner detected ({selector})"
    return None


def _gdpr_concerns(html: str, has_banner: bool) -> list[str]:
    concerns = []
    # Check if tracking present without consent banner
    has_tracking = any(p in html for p in [
        "connect.facebook.net", "google-analytics.com", "analytics.tiktok.com"
    ])
    if has_tracking and not has_banner:
        concerns.append("Tracking scripts detected without visible consent management")

    # Check for third-party cookies being set immediately (heuristic)
    if "_fbp" in html or "_ga" in html:
        if not has_banner:
            concerns.append("Analytics/ad cookies may load before user consent")

    return concerns


async def check_security(store_url: str, pages: list[dict]) -> SecurityCompliance:
    parsed = urlparse(store_url)
    hostname = parsed.hostname or ""

    ssl_status, ssl_details = _check_ssl(hostname) if hostname else ("missing", "No hostname")

    homepage_html = pages[0].get("html", "") if pages else ""
    banner_behavior = _detect_cookie_banner(homepage_html)
    gdpr = _gdpr_concerns(homepage_html, banner_behavior is not None)

    # PCI heuristic: if checkout is handled by known PSP, likely compliant
    all_html = " ".join(p.get("html", "") for p in pages)
    pci: PciStatus = "likely"
    for psp in _KNOWN_PSP_REDIRECT_INDICATORS:
        if psp in all_html:
            pci = "likely"
            break
    else:
        pci = "concerns"

    return SecurityCompliance(
        ssl_status=ssl_status,
        ssl_details=ssl_details,
        cookie_banner_behavior=banner_behavior or "No standard cookie banner detected",
        gdpr_concerns=gdpr,
        pci_compliance=pci,
        notes="PCI assessment is heuristic — verify actual payment flow for compliance.",
    )

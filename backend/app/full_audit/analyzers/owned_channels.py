import re

from bs4 import BeautifulSoup

from app.full_audit.schemas import OwnedChannels

_ESP_COOKIE_PATTERNS = {
    "Klaviyo": ["__kla_id"],
    "Omnisend": ["_omappvp", "omnisend"],
    "Mailchimp": ["_mailchimp"],
    "Attentive": ["__attentive_id"],
    "Drip": [],
}

_ESP_SCRIPT_PATTERNS = {
    "Klaviyo": ["static.klaviyo.com", "_learnq"],
    "Omnisend": ["omnywidget.omnisend.com"],
    "Mailchimp": ["chimpstatic.com"],
    "Attentive": ["cdn.attn.tv"],
    "Drip": ["tag.getdrip.com"],
    "ActiveCampaign": ["trackcmp.net"],
}

_SMS_PATTERNS = [
    "cdn.attn.tv",      # Attentive
    "cdn.recart.com",   # Recart
    "static.klaviyo.com",  # Klaviyo SMS
    "postscript.io",    # Postscript
    "smsbump.com",
]


def _detect_esp_from_headers(pages: list[dict]) -> tuple[str | None, str | None]:
    for page in pages:
        headers = {k.lower(): v for k, v in page.get("headers", {}).items()}
        set_cookie = headers.get("set-cookie", "")
        for esp, cookies in _ESP_COOKIE_PATTERNS.items():
            for cookie in cookies:
                if cookie in set_cookie:
                    return esp, f"Set-Cookie header contains: {cookie}"
    return None, None


def _detect_esp_from_html(html: str) -> tuple[str | None, str | None]:
    for esp, patterns in _ESP_SCRIPT_PATTERNS.items():
        for pattern in patterns:
            if pattern in html:
                return esp, f"Script or inline reference: {pattern}"
    return None, None


def _has_newsletter_form(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    for form in soup.find_all("form"):
        for inp in form.find_all("input"):
            inp_type = str(inp.get("type", "")).lower()
            inp_name = str(inp.get("name", "")).lower()
            if inp_type == "email" or "email" in inp_name:
                return True
    return False


def _detect_sms(html: str) -> bool:
    return any(pattern in html for pattern in _SMS_PATTERNS)


async def detect_owned_channels(store_url: str, pages: list[dict]) -> OwnedChannels:
    if not pages:
        return OwnedChannels()

    all_html = " ".join(p.get("html", "") for p in pages)
    homepage_html = pages[0].get("html", "")

    # ESP detection: try cookies first, then HTML
    esp, ev = _detect_esp_from_headers(pages)
    if not esp:
        esp, ev = _detect_esp_from_html(all_html)

    newsletter_signup = _has_newsletter_form(homepage_html)
    sms_active = _detect_sms(all_html)

    # Flow heuristics — outside-only can't confirm these, mark as unknown
    return OwnedChannels(
        esp_detected=esp,
        esp_detection_evidence=ev,
        newsletter_signup_tested=newsletter_signup,
        welcome_flow_observed=None,
        abandoned_cart_flow_observed=None,
        post_purchase_flow_observed=None,
        win_back_flow_observed=None,
        est_email_revenue_percent=None,
        benchmark_email_revenue_percent=30.0,
        sms_active=sms_active if sms_active else None,
        notes="Email flows (welcome, abandoned cart, etc.) require inbox access — not verifiable from outside.",
    )

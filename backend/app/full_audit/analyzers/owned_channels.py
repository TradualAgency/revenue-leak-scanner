import json
import logging
import re

from bs4 import BeautifulSoup

from app.full_audit.schemas import OwnedChannels

logger = logging.getLogger(__name__)

_ESP_COOKIE_PATTERNS = {
    "Klaviyo": ["__kla_id"],
    "Omnisend": ["_omappvp", "omnisend"],
    "Mailchimp": ["_mailchimp"],
    "Attentive": ["__attentive_id"],
    "Drip": [],
}

_ESP_SCRIPT_PATTERNS = {
    "Klaviyo": ["static.klaviyo.com", "klaviyo.com/onsite", "_learnq", "klaviyo.js"],
    "Omnisend": ["omnywidget.omnisend.com", "omnisend.js"],
    "Mailchimp": ["chimpstatic.com"],
    "Attentive": ["cdn.attn.tv"],
    "Drip": ["tag.getdrip.com"],
    "ActiveCampaign": ["trackcmp.net"],
}

_NEWSLETTER_ESP_PATTERNS = [
    # Klaviyo — all CDN/API variants + form containers
    "static.klaviyo.com", "a.klaviyo.com", "klaviyo.com/onsite", "klaviyo.com/api/v3",
    "klaviyo.js", "_learnq", "klaviyo-form-", "klaviyoforms", "data-klaviyo",
    # Omnisend
    "omnisend.com", "omnisrc.com", "omnywidget", "omnisend.js", "omnisend/inshop",
    # Mailchimp / Mailmunch
    "chimpstatic.com", "list-manage.com", "mc-embedded-subscribe", "mc4wp",
    "mailmunch.co",
    # MailerLite
    "mailerlite.com", "ml-form-", "mailerlite.com/universal",
    # Privy / Sumo / OptinMonster / PopupSmart
    "privy.com", "privy-widget", "sumo.com", "optinmonster", "popupsmart",
    # Attentive / Drip / ActiveCampaign
    "cdn.attn.tv", "tag.getdrip.com", "trackcmp.net",
    # Shopify native newsletter sections
    'data-section-type="newsletter"', "shopify-section-newsletter",
    # Other common markers
    "_ko_init", "kla_email",
]

_NEWSLETTER_KEYWORDS = [
    "nieuwsbrief", "newsletter", "subscribe", "abonneer",
    "blijf op de hoogte", "stay updated", "sign up", "aanmelden",
    "email updates", "weekly updates", "updates ontvangen",
    "schrijf je in", "schrijf je op", "meld je aan",
]

_SMS_PATTERNS = [
    "cdn.attn.tv",      # Attentive
    "cdn.recart.com",   # Recart
    "static.klaviyo.com",  # Klaviyo SMS
    "postscript.io",    # Postscript
    "smsbump.com",
]

_NEWSLETTER_AI_SYSTEM = """\
Je analyseert een extract van een webshop-pagina (raw HTML, scripts, footer). \
Bepaal of de webshop een nieuwsbrief-aanmeldformulier of e-mailcapture-mechanisme heeft.

Positief bewijs (één hiervan is genoeg):
- Script-tag naar Klaviyo, Omnisend, Mailchimp, Privy of vergelijkbare e-mailmarketingtool
- Een element met class of id die "klaviyo-form", "newsletter", "subscribe" of vergelijkbaar bevat
- Een <input type="email"> in de footer of popup-container
- Tekst als "nieuwsbrief", "inschrijven", "subscribe" nabij een invoerveld

Reageer ALLEEN met geldige JSON (geen markdown, geen uitleg erbuiten):
{"detected": true, "mechanism": "<kort label>", "evidence": "<kort bewijs>"}
of
{"detected": false, "mechanism": null, "evidence": null}\
"""

_NEWSLETTER_AI_ELEMENT_PATTERN = re.compile(
    r"newsletter|subscribe|popup|optin|signup|klaviyo|omnisend|mailchimp|privy",
    re.I,
)


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


def _detect_newsletter_capture(html: str) -> tuple[bool, str | None]:
    """Return (has_capture, evidence_string). Three cascading paths:
    A) ESP popup/form script or known container detected in raw HTML
    B) Any <input type="email"> with nearby newsletter-intent keyword
    C) Any <form> containing an email input (broad fallback)
    """
    lower_html = html.lower()

    # Path A: ESP popup script or form container marker
    for pattern in _NEWSLETTER_ESP_PATTERNS:
        if pattern.lower() in lower_html:
            return True, f"{pattern} popup/form script aanwezig"

    # Path B: standalone email input + newsletter intent in attributes
    soup = BeautifulSoup(html, "lxml")
    for inp in soup.find_all("input"):
        inp_type = str(inp.get("type", "")).lower()
        if inp_type != "email":
            continue
        nearby = " ".join([
            str(inp.get("placeholder", "")),
            str(inp.get("aria-label", "")),
            str(inp.get("name", "")),
            str(inp.get("id", "")),
        ]).lower()
        if any(kw in nearby for kw in _NEWSLETTER_KEYWORDS):
            return True, f"email input met attribuut: '{nearby[:50].strip()}'"

    # Path C: any form with email input (fallback)
    for form in soup.find_all("form"):
        for inp in form.find_all("input"):
            inp_type = str(inp.get("type", "")).lower()
            inp_name = str(inp.get("name", "")).lower()
            if inp_type == "email" or "email" in inp_name:
                return True, "form met email-input"

    return False, None


def _detect_sms(html: str) -> bool:
    return any(pattern in html for pattern in _SMS_PATTERNS)


def _build_newsletter_extract(pages: list[dict]) -> str:
    """Build a slim multi-page HTML extract for AI newsletter detection (~9k chars max)."""
    parts: list[str] = []

    for page in pages[:2]:
        html = page.get("html", "")
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")

        head = soup.find("head")
        if head:
            parts.append(f"HEAD:\n{str(head)[:2000]}")

        script_srcs = [tag.get("src", "") for tag in soup.find_all("script", src=True) if tag.get("src")]
        if script_srcs:
            parts.append("SCRIPTS:\n" + "\n".join(script_srcs[:40]))

        for form in soup.find_all("form"):
            parts.append(f"FORM:\n{str(form)[:600]}")

        for tag in soup.find_all(True):
            classes = " ".join(tag.get("class", []))
            tag_id = tag.get("id", "")
            if _NEWSLETTER_AI_ELEMENT_PATTERN.search(classes) or _NEWSLETTER_AI_ELEMENT_PATTERN.search(tag_id):
                parts.append(f"ELEMENT [{tag.name}]:\n{str(tag)[:400]}")

        footer = soup.find("footer")
        if footer:
            parts.append(f"FOOTER:\n{str(footer)[:2000]}")

    return "\n\n".join(parts)[:9000]


async def _ai_detect_newsletter(pages: list[dict]) -> tuple[bool | None, str | None]:
    """Claude Haiku fallback. Returns (True, evidence) if detected, (None, None) otherwise."""
    try:
        import anthropic
        from app.config import settings

        if not settings.ANTHROPIC_API_KEY:
            return None, None

        extract = _build_newsletter_extract(pages)
        if not extract.strip():
            return None, None

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            system=_NEWSLETTER_AI_SYSTEM,
            messages=[{"role": "user", "content": extract}],
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()

        data = json.loads(raw)
        detected = data.get("detected")
        if not isinstance(detected, bool):
            return None, None
        if not detected:
            # Can't confirm absence via raw HTML — treat as unknown
            return None, None
        evidence = data.get("evidence") or data.get("mechanism")
        return True, evidence
    except Exception as exc:
        logger.warning("AI newsletter detection failed: %s", exc)
        return None, None


async def detect_owned_channels(store_url: str, pages: list[dict]) -> OwnedChannels:
    if not pages:
        return OwnedChannels()

    all_html = " ".join(p.get("html", "") for p in pages)

    # ESP detection: try cookies first, then HTML
    esp, ev = _detect_esp_from_headers(pages)
    if not esp:
        esp, ev = _detect_esp_from_html(all_html)

    # Newsletter detection: scan each page individually, then AI fallback
    newsletter_signup: bool | None = None
    newsletter_evidence: str | None = None

    for page in pages:
        found, evidence = _detect_newsletter_capture(page.get("html", ""))
        if found:
            newsletter_signup = True
            newsletter_evidence = evidence
            break

    if not newsletter_signup:
        newsletter_signup, newsletter_evidence = await _ai_detect_newsletter(pages)

    sms_active = _detect_sms(all_html)

    notes_parts = ["Email flows (welcome, abandoned cart, etc.) require inbox access — not verifiable from outside."]
    if newsletter_evidence:
        notes_parts.append(f"Email capture gevonden: {newsletter_evidence}")

    return OwnedChannels(
        esp_detected=esp,
        esp_detection_evidence=ev,
        newsletter_signup_tested=newsletter_signup,
        sms_active=sms_active if sms_active else None,
        notes=" ".join(notes_parts),
    )

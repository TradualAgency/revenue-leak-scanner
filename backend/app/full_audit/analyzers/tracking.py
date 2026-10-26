import functools
import json
import re
from pathlib import Path

from app.full_audit.schemas import (
    ConsentModeStatus,
    HealthStatus,
    ServerSideTagging,
    TrackingDataQuality,
)

_SIGS_PATH = Path(__file__).parent.parent / "data" / "tracker_signatures.json"


@functools.lru_cache(maxsize=1)
def _load_signatures() -> dict:
    with open(_SIGS_PATH) as f:
        return json.load(f)


def _match_tool(html: str, sig: dict) -> bool:
    for pattern in sig.get("script_patterns", []):
        if pattern in html:
            return True
    for pattern in sig.get("inline_patterns", []):
        if pattern in html:
            return True
    return False


_CONSENT_CALL_RE = re.compile(r"""gtag\(\s*['"]consent['"]\s*,\s*['"](default|update)['"]\s*,\s*\{([^}]*)\}""")
# The two parameters Consent Mode v2 added; a default call without them is v1.
_CONSENT_V2_PARAMS = ("ad_user_data", "ad_personalization")


def _detect_consent_mode_v2(html: str, cmp_or_gtm_present: bool) -> ConsentModeStatus:
    """Judged on the actual gtag('consent', ...) calls. The old check accepted any
    "default" string anywhere in the page — which nearly every page contains."""
    calls = _CONSENT_CALL_RE.findall(html)
    if calls:
        defaults = [body for kind, body in calls if kind == "default"]
        if any(all(param in body for param in _CONSENT_V2_PARAMS) for body in defaults):
            return "v2-correct"
        return "v2-incorrect"
    # No inline gtag('consent'...) call in the raw HTML. If a CMP or GTM container is
    # present, consent config plausibly lives inside GTM/the CMP backend, invisible to a
    # static HTML scrape — that's "unknown", not "no consent management at all".
    if cmp_or_gtm_present:
        return "to-validate"
    return "none"


def _detect_sgtm(pages: list[dict]) -> ServerSideTagging:
    """Detect server-side GTM via non-google custom container domains."""
    for page in pages:
        html = page.get("html", "")
        # sGTM: GTM loaded from a custom subdomain (not googletagmanager.com)
        matches = re.findall(r'src=["\'](https?://[^"\']+gtm\.js[^"\']*)["\']', html)
        for m in matches:
            if "googletagmanager.com" not in m:
                return "yes"
    return "no"


_WEB_PIXELS_MARKER = "webPixelsConfigList"
_GA4_ID_RE = re.compile(r"\bG-[A-Z0-9]{6,12}\b")
_GOOGLE_ADS_ID_RE = re.compile(r"\bAW-\d{6,12}\b")
_META_PIXEL_ID_RE = re.compile(r"pixel_?[iI]d\\*\"\s*:\s*\\*\"?(\d{10,20})")


def _web_pixels(html: str) -> dict[str, str]:
    """Pixels configured through Shopify's Web Pixels Manager. They load in a sandbox a
    static scrape can't execute, but their configuration is inlined in the page as
    (escaped) JSON — enough to see which tags are installed. Returns tool -> evidence."""
    start = html.find(_WEB_PIXELS_MARKER)
    if start < 0:
        return {}
    segment = html[start:start + 60_000]
    found: dict[str, str] = {}
    if m := _GA4_ID_RE.search(segment):
        found["Google Analytics 4"] = f"Shopify Web Pixels: {m.group(0)}"
    if m := _GOOGLE_ADS_ID_RE.search(segment):
        found["Google Ads"] = f"Shopify Web Pixels: {m.group(0)}"
    if m := _META_PIXEL_ID_RE.search(segment):
        found["Meta Pixel"] = f"Shopify Web Pixels: pixel {m.group(1)}"
    return found


def _estimate_attribution_loss(
    pixels: HealthStatus | None,
    consent: ConsentModeStatus | None,
    duplicate: bool,
) -> float:
    # CAPI status is always "to-validate" outside-only (server-side calls aren't visible
    # in scraped HTML), so it never contributes here — a fixed +10 for an unmeasurable
    # signal isn't a measurement, it's a guess dressed up as one.
    loss = 0.0
    if consent in ("none", "v2-incorrect"):
        loss += 20.0
    if pixels in ("partial", "missing"):
        loss += 15.0
    if duplicate:
        loss += 5.0
    return min(loss, 70.0)


async def detect_tracking(pages: list[dict]) -> TrackingDataQuality:
    if not pages:
        return TrackingDataQuality()

    sigs = _load_signatures()
    all_html = " ".join(p.get("html", "") for p in pages)

    # Detect analytics tools
    found_analytics: list[str] = []
    evidence_parts: list[str] = []
    for sig in sigs.get("analytics", []):
        if _match_tool(all_html, sig):
            found_analytics.append(sig["name"])
            patterns_hit = [p for p in sig.get("script_patterns", []) + sig.get("inline_patterns", []) if p in all_html]
            if patterns_hit:
                evidence_parts.append(f"{sig['name']}: {patterns_hit[0]}")

    # Detect CMP
    found_cmp: list[str] = []
    for sig in sigs.get("cmp", []):
        if _match_tool(all_html, sig):
            found_cmp.append(sig["name"])

    # Detect ESP
    found_esp: list[str] = []
    for sig in sigs.get("esp", []):
        if _match_tool(all_html, sig):
            found_esp.append(sig["name"])

    for tool, evidence in _web_pixels(all_html).items():
        if tool not in found_analytics:
            found_analytics.append(tool)
            evidence_parts.append(evidence)

    analytics_stack = ", ".join(found_analytics + found_esp) if (found_analytics or found_esp) else None

    # Duplicate GTM detection (also used below to inform consent-mode confidence)
    gtm_ids = set(re.findall(r"GTM-[A-Z0-9]+", all_html))
    duplicate = len(gtm_ids) > 1

    # Pixel health: if Meta Pixel or GA4 detected → healthy, else missing/unknown.
    # On Shopify, pixels are commonly loaded through the Web Pixels Manager — a sandboxed
    # iframe/worker that a static HTML scrape structurally cannot see into. Absence of a
    # script-tag match there means "can't confirm", not "not installed".
    is_shopify = any(
        marker in all_html for marker in ("cdn.shopify.com", "Shopify.shop", "window.Shopify")
    )
    has_ga4 = any("Google Analytics 4" in a for a in found_analytics)
    has_meta = any("Meta Pixel" in a for a in found_analytics)
    # A GTM container or Shopify's pixel sandbox can hold the pixel we didn't see, so
    # "one of two found" there is unconfirmed, not "partial" — "partial" and "missing"
    # add attribution loss, and a pixel we simply can't see must not.
    hidden_pixels_possible = is_shopify or bool(gtm_ids)
    if has_ga4 and has_meta:
        pixels_health: HealthStatus = "healthy"
    elif hidden_pixels_possible:
        pixels_health = "to-validate"
    elif has_ga4 or has_meta:
        pixels_health = "partial"
    else:
        pixels_health = "missing"

    # CAPI: heuristic — we can't detect server-side from outside
    capi_status: HealthStatus = "to-validate"

    consent_mode = _detect_consent_mode_v2(all_html, cmp_or_gtm_present=bool(found_cmp or gtm_ids))
    cmp_provider = found_cmp[0] if found_cmp else None

    sgtm = _detect_sgtm(pages)

    attribution_loss = _estimate_attribution_loss(pixels_health, consent_mode, duplicate)

    return TrackingDataQuality(
        analytics_stack=analytics_stack,
        detection_evidence="; ".join(evidence_parts) if evidence_parts else None,
        pixels_health=pixels_health,
        capi_status=capi_status,
        consent_mode_status=consent_mode,
        cmp_provider=cmp_provider,
        est_attribution_loss_percent=round(attribution_loss, 1),
        server_side_tagging=sgtm,
        duplicate_tracking_detected=duplicate,
        notes="CAPI status requires manual verification — not detectable from outside.",
    )

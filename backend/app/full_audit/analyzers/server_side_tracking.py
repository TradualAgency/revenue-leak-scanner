import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.full_audit.schemas import ServerSideTracking

logger = logging.getLogger(__name__)

_SGTM_SUBDOMAIN_RE = re.compile(
    r"(gtm|tags|analytics|tracking|events|collect|pixel)\.",
    re.IGNORECASE,
)

_GEC_PATTERNS = [
    re.compile(r"gtag\s*\(\s*['\"]set['\"].*user_data", re.IGNORECASE | re.DOTALL),
    re.compile(r"enhanced_conversions", re.IGNORECASE),
    re.compile(r"google_tag_params.*email", re.IGNORECASE | re.DOTALL),
]

_TIKTOK_CAPI_PATTERNS = [
    re.compile(r"ttq\.identify", re.IGNORECASE),
    re.compile(r"tiktok.*events.*api", re.IGNORECASE),
]


async def analyze_server_side_tracking(store_url: str, pages: list[dict]) -> ServerSideTracking:
    try:
        parsed = urlparse(store_url)
        domain = parsed.hostname or ""
        apex = domain.removeprefix("www.") if domain else ""

        html_combined = "\n".join(p.get("html", "") for p in pages[:3])

        # sGTM — script src on a store-owned subdomain
        sgtm_detected = False
        sgtm_endpoint: str | None = None
        try:
            soup = BeautifulSoup(html_combined[:300_000], "lxml")
            for tag in soup.find_all("script", src=True):
                src = tag.get("src", "")
                if not src or "googletagmanager.com" in src:
                    continue
                src_host = (urlparse(str(src)).hostname or "").lower()
                if apex and src_host.endswith(f".{apex}") and src_host != f"www.{apex}":
                    if _SGTM_SUBDOMAIN_RE.search(src_host):
                        sgtm_detected = True
                        sgtm_endpoint = src_host
                        break
        except Exception:
            pass

        # Meta CAPI — server-set _fbc/_fbp cookies indicate CAPI
        all_headers: dict[str, str] = {}
        for page in pages:
            for k, v in (page.get("headers", {}) or {}).items():
                all_headers[k.lower()] = v

        set_cookie = all_headers.get("set-cookie", "")
        if "_fbc=" in set_cookie or "_fbp=" in set_cookie:
            meta_capi_status = "detected"
        elif "fbq(" in html_combined or "fbevents" in html_combined:
            meta_capi_status = "browser-only"
        else:
            meta_capi_status = "absent"

        # Google Enhanced Conversions
        gec_status = "not-detected"
        for pattern in _GEC_PATTERNS:
            if pattern.search(html_combined):
                gec_status = "detected"
                break

        # TikTok Events API
        tiktok_status = "not-detected"
        for pattern in _TIKTOK_CAPI_PATTERNS:
            if pattern.search(html_combined):
                tiktok_status = "detected"
                break

        # Attribution loss risk
        risk_factors = sum([
            not sgtm_detected,
            meta_capi_status in ("browser-only", "absent"),
            gec_status == "not-detected",
        ])
        risk = "high" if risk_factors >= 2 else "medium" if risk_factors == 1 else "low"

        return ServerSideTracking(
            sgtm_detected=sgtm_detected,
            sgtm_endpoint=sgtm_endpoint,
            meta_capi_status=meta_capi_status,  # type: ignore[arg-type]
            google_enhanced_conv_status=gec_status,
            tiktok_capi_status=tiktok_status,
            attribution_loss_risk=risk,  # type: ignore[arg-type]
        )
    except Exception as exc:
        logger.warning("server_side_tracking analyzer failed: %s", exc)
        return ServerSideTracking()

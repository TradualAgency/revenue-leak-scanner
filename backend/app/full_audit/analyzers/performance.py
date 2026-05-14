import logging

import aiohttp

from app.config import settings
from app.full_audit.schemas import LighthouseScores, MobileCWV, Performance, Rating

logger = logging.getLogger(__name__)

PAGESPEED_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

_CATEGORY_MAP = {"FAST": "good", "AVERAGE": "needs-improvement", "SLOW": "poor"}


def _cwv_rating(category: str) -> Rating:
    return _CATEGORY_MAP.get(category, "needs-improvement")  # type: ignore[return-value]


def _score_to_int(val: float | None) -> int | None:
    if val is None:
        return None
    return int(round(val * 100))


def _lcp_rating_from_ms(ms: float | None) -> Rating | None:
    if ms is None:
        return None
    if ms < 2500:
        return "good"
    if ms < 4000:
        return "needs-improvement"
    return "poor"


def _cls_rating_from_val(cls: float | None) -> Rating | None:
    if cls is None:
        return None
    if cls < 0.1:
        return "good"
    if cls < 0.25:
        return "needs-improvement"
    return "poor"


def _inp_rating_from_ms(ms: float | None) -> Rating | None:
    if ms is None:
        return None
    if ms < 200:
        return "good"
    if ms < 500:
        return "needs-improvement"
    return "poor"


async def _call_psi(url: str, strategy: str = "mobile") -> dict | None:
    if not settings.PAGESPEED_API_KEY:
        return None
    params = {
        "url": url,
        "strategy": strategy,
        "key": settings.PAGESPEED_API_KEY,
        "category": ["performance", "accessibility", "best-practices", "seo"],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                PAGESPEED_API_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                if resp.status != 200:
                    logger.warning("PSI API returned %s for %s (%s)", resp.status, url, strategy)
                    return None
                return await resp.json()
    except Exception as exc:
        logger.warning("PSI API error for %s: %s", url, exc)
        return None


def _cwv_from_field_data(data: dict) -> MobileCWV:
    """Extract CrUX field data (real-user measurements). May be sparse for low-traffic sites."""
    exp = data.get("loadingExperience", {}).get("metrics", {})

    def metric_val(key: str) -> float | None:
        m = exp.get(key, {})
        v = m.get("percentile")
        return float(v) if v is not None else None

    def metric_rating(key: str) -> Rating | None:
        cat = exp.get(key, {}).get("category")
        return _cwv_rating(cat) if cat else None

    cls_raw = metric_val("CUMULATIVE_LAYOUT_SHIFT_SCORE")
    cls_val = cls_raw / 100 if cls_raw is not None else None

    return MobileCWV(
        lcp_ms=metric_val("LARGEST_CONTENTFUL_PAINT_MS"),
        lcp_rating=metric_rating("LARGEST_CONTENTFUL_PAINT_MS"),
        inp_ms=metric_val("INTERACTION_TO_NEXT_PAINT"),
        inp_rating=metric_rating("INTERACTION_TO_NEXT_PAINT"),
        cls=cls_val,
        cls_rating=metric_rating("CUMULATIVE_LAYOUT_SHIFT_SCORE"),
        fcp_ms=metric_val("FIRST_CONTENTFUL_PAINT_MS"),
        ttfb_ms=metric_val("EXPERIMENTAL_TIME_TO_FIRST_BYTE"),
    )


def _cwv_from_lab(data: dict) -> MobileCWV:
    """Extract Lighthouse lab metrics. Always available when PSI succeeds."""
    audits = data.get("lighthouseResult", {}).get("audits", {})

    def audit_val(key: str) -> float | None:
        v = audits.get(key, {}).get("numericValue")
        return float(v) if v is not None else None

    lcp_ms = audit_val("largest-contentful-paint")
    cls_val = audit_val("cumulative-layout-shift")
    fcp_ms = audit_val("first-contentful-paint")
    ttfb_ms = audit_val("server-response-time")

    return MobileCWV(
        lcp_ms=lcp_ms,
        lcp_rating=_lcp_rating_from_ms(lcp_ms),
        inp_ms=audit_val("interactive"),
        inp_rating=_inp_rating_from_ms(audit_val("interactive")),
        cls=cls_val,
        cls_rating=_cls_rating_from_val(cls_val),
        fcp_ms=fcp_ms,
        ttfb_ms=ttfb_ms,
    )


def _merge_cwv(field: MobileCWV, lab: MobileCWV) -> MobileCWV:
    """Prefer field data (real users) per metric; fill nulls from lab."""
    def pick(f, l):
        return f if f is not None else l

    return MobileCWV(
        lcp_ms=pick(field.lcp_ms, lab.lcp_ms),
        lcp_rating=pick(field.lcp_rating, lab.lcp_rating),
        inp_ms=pick(field.inp_ms, lab.inp_ms),
        inp_rating=pick(field.inp_rating, lab.inp_rating),
        cls=pick(field.cls, lab.cls),
        cls_rating=pick(field.cls_rating, lab.cls_rating),
        fcp_ms=pick(field.fcp_ms, lab.fcp_ms),
        ttfb_ms=pick(field.ttfb_ms, lab.ttfb_ms),
    )


def _lighthouse_from_response(data: dict) -> LighthouseScores:
    cats = data.get("lighthouseResult", {}).get("categories", {})
    return LighthouseScores(
        performance=_score_to_int(cats.get("performance", {}).get("score")),
        accessibility=_score_to_int(cats.get("accessibility", {}).get("score")),
        best_practices=_score_to_int(cats.get("best-practices", {}).get("score")),
        seo=_score_to_int(cats.get("seo", {}).get("score")),
    )


def _render_blocking(data: dict) -> list[str]:
    audits = data.get("lighthouseResult", {}).get("audits", {})
    items = audits.get("render-blocking-resources", {}).get("details", {}).get("items", [])
    return [item.get("url", "") for item in items if item.get("url")]


def _large_images(data: dict) -> list[str]:
    audits = data.get("lighthouseResult", {}).get("audits", {})
    items = audits.get("uses-optimized-images", {}).get("details", {}).get("items", [])
    return [item.get("url", "") for item in items if item.get("url")]


def _unused_js_kb(data: dict) -> float | None:
    audits = data.get("lighthouseResult", {}).get("audits", {})
    val = audits.get("unused-javascript", {}).get("numericValue")
    return round(val / 1024, 1) if val else None


def _page_weight_kb(data: dict) -> float | None:
    audits = data.get("lighthouseResult", {}).get("audits", {})
    val = audits.get("total-byte-weight", {}).get("numericValue")
    return round(val / 1024, 1) if val else None


def _request_count(data: dict) -> int | None:
    audits = data.get("lighthouseResult", {}).get("audits", {})
    items = audits.get("network-requests", {}).get("details", {}).get("items", [])
    return len(items) if items else None


def _tbt_ms(data: dict) -> float | None:
    audits = data.get("lighthouseResult", {}).get("audits", {})
    val = audits.get("total-blocking-time", {}).get("numericValue")
    return float(val) if val is not None else None


def _speed_index_ms(data: dict) -> float | None:
    audits = data.get("lighthouseResult", {}).get("audits", {})
    val = audits.get("speed-index", {}).get("numericValue")
    return float(val) if val is not None else None


def _tti_ms(data: dict) -> float | None:
    audits = data.get("lighthouseResult", {}).get("audits", {})
    val = audits.get("interactive", {}).get("numericValue")
    return float(val) if val is not None else None


async def analyze_performance(store_url: str, pages: list[dict]) -> Performance:
    mobile_data = await _call_psi(store_url, strategy="mobile")
    desktop_data = await _call_psi(store_url, strategy="desktop")

    mobile_cwv: MobileCWV | None = None
    lighthouse: LighthouseScores | None = None
    render_blocking: list[str] = []
    large_images: list[str] = []
    unused_js: float | None = None
    page_weight: float | None = None
    req_count: int | None = None
    desktop_lcp: float | None = None
    tbt: float | None = None
    speed_index: float | None = None
    tti: float | None = None
    notes: str | None = None

    if mobile_data:
        field_cwv = _cwv_from_field_data(mobile_data)
        lab_cwv = _cwv_from_lab(mobile_data)
        mobile_cwv = _merge_cwv(field_cwv, lab_cwv)
        lighthouse = _lighthouse_from_response(mobile_data)
        render_blocking = _render_blocking(mobile_data)
        large_images = _large_images(mobile_data)
        unused_js = _unused_js_kb(mobile_data)
        page_weight = _page_weight_kb(mobile_data)
        req_count = _request_count(mobile_data)
        tbt = _tbt_ms(mobile_data)
        speed_index = _speed_index_ms(mobile_data)
        tti = _tti_ms(mobile_data)
    else:
        # Fallback from scraper load times
        load_times = [p["load_time_ms"] for p in pages if p.get("load_time_ms", 0) > 0]
        if load_times:
            avg_ms = sum(load_times) / len(load_times)
            estimated_lcp = avg_ms * 8
            lcp_rating: Rating = (
                "good" if estimated_lcp < 2500 else "needs-improvement" if estimated_lcp < 4000 else "poor"
            )
            mobile_cwv = MobileCWV(lcp_ms=estimated_lcp, lcp_rating=lcp_rating)
        notes = "PageSpeed Insights API key not configured — CWV estimated from TTFB only."

    if desktop_data:
        audits = desktop_data.get("lighthouseResult", {}).get("audits", {})
        lcp_val = audits.get("largest-contentful-paint", {}).get("numericValue")
        desktop_lcp = float(lcp_val) if lcp_val else None

    return Performance(
        mobile=mobile_cwv,
        desktop_lcp_ms=desktop_lcp,
        lighthouse=lighthouse,
        tbt_ms=tbt,
        speed_index_ms=speed_index,
        tti_ms=tti,
        render_blocking_resources=render_blocking,
        large_images_uncompressed=large_images,
        unused_javascript_kb=unused_js,
        total_page_weight_kb=page_weight,
        number_of_requests=req_count,
        notes=notes,
    )

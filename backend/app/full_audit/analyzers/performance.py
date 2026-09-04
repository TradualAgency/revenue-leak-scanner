import asyncio
import logging
from urllib.parse import urlparse

import aiohttp

from app.config import settings
from app.full_audit.page_sampling import sample_pages_by_type
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


async def _no_psi_call() -> None:
    """Placeholder awaitable for asyncio.gather when there's no money page to measure."""
    return None


_ALL_CATEGORIES = ["performance", "accessibility", "best-practices", "seo"]


async def _call_psi_once(url: str, strategy: str, categories: list[str], timeout_s: float) -> dict | None:
    params = {
        "url": url,
        "strategy": strategy,
        "key": settings.PAGESPEED_API_KEY,
        "category": categories,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                PAGESPEED_API_URL,
                params=params,
                # Each extra Lighthouse category roughly multiplies audit time; a slow
                # site can genuinely take well over a minute even for one category. A
                # tight timeout here silently turns "this site is slow" into "we
                # measured nothing", which is worse than waiting.
                timeout=aiohttp.ClientTimeout(total=timeout_s),
            ) as resp:
                if resp.status != 200:
                    logger.warning("PSI API returned %s for %s (%s)", resp.status, url, strategy)
                    return None
                return await resp.json()
    except Exception as exc:
        logger.warning("PSI API error for %s: %s (%s)", url, exc, type(exc).__name__)
        return None


async def _call_psi(
    url: str, strategy: str = "mobile", categories: list[str] | None = None, timeout_s: float = 90,
) -> dict | None:
    if not settings.PAGESPEED_API_KEY:
        return None
    cats = categories if categories is not None else _ALL_CATEGORIES

    result = await _call_psi_once(url, strategy, cats, timeout_s)
    if result is not None:
        return result

    # Slow sites are exactly where PSI is most likely to time out or 500 on a given
    # attempt — retrying once catches the transient cases without doubling latency for
    # sites that succeed on the first try.
    logger.info("Retrying PSI call for %s (%s)", url, strategy)
    return await _call_psi_once(url, strategy, cats, timeout_s)


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
        # INP has no lab-simulated equivalent — Lighthouse's "interactive" audit is Time
        # to Interactive, a page-load metric on a completely different scale (seconds,
        # not the 200/500ms INP thresholds). Mapping TTI onto inp_ms made every site read
        # as "INP critical". Leave null; INP is only trustworthy from real-user CrUX data.
        inp_ms=None,
        inp_rating=None,
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


def _third_party_summary_by_domain(data: dict) -> dict[str, dict]:
    """Lighthouse's own `third-party-summary` audit: real transfer size and blocking
    time per third-party entity, attributed from the actual page load it measured —
    not a guess. Used to replace the flat 50/15/20 KB constants that used to stand in
    for a measurement in `third_party.py`.

    Lighthouse groups by "entity" (a business, e.g. "Google"), not literal hostname, so
    the returned keys are best-effort domains/names for substring matching downstream,
    not exact hostnames.
    """
    audits = data.get("lighthouseResult", {}).get("audits", {})
    items = audits.get("third-party-summary", {}).get("details", {}).get("items", [])
    result: dict[str, dict] = {}
    for item in items:
        entity = item.get("entity")
        key: str | None = None
        if isinstance(entity, dict):
            url = entity.get("url")
            if url:
                key = urlparse(url).netloc.removeprefix("www.").lower()
            elif entity.get("text"):
                key = str(entity["text"]).lower()
        elif isinstance(entity, str):
            key = entity.lower()
        if not key:
            continue
        result[key] = {
            "transfer_size_kb": round((item.get("transferSize") or 0) / 1024, 1),
            "blocking_ms": round(float(item.get("blockingTime") or 0), 1),
            "main_thread_ms": round(float(item.get("mainThreadTime") or 0), 1),
        }
    return result


async def analyze_performance(
    store_url: str, pages: list[dict], include_desktop: bool = True,
) -> tuple[Performance, dict[str, dict]]:
    money_page = _pick_money_page(pages)

    # Three independent PSI calls (each a full Lighthouse run, now allowed up to 90s) —
    # run them concurrently rather than sequentially, or a single slow site could push
    # this analyzer's worst case to 3x the per-call timeout.
    calls = [
        _call_psi(store_url, strategy="mobile"),
        # Only `.performance` is ever read from the desktop and money-page results
        # (confirmed: no code reads their accessibility/best-practices/seo scores) —
        # requesting just that category keeps these two calls fast even on slow sites,
        # so they don't become the bottleneck next to the necessarily-full mobile call.
        # `include_desktop=False` (competitor benchmark) drops this call entirely — a
        # 33% PSI-call saving per domain, since nothing downstream reads desktop scores
        # in that comparison.
        _call_psi(store_url, strategy="desktop", categories=["performance"]) if include_desktop else _no_psi_call(),
        _call_psi(money_page[0], strategy="mobile", categories=["performance"]) if money_page else _no_psi_call(),
    ]
    mobile_data, desktop_data, money_page_data = await asyncio.gather(*calls)

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
        # No PSI data — the scraper's own fetch time is TTFB, not a browser page load.
        # Scaling it by a guessed multiplier presented a fabricated LCP as a measurement
        # (the same issue fixed in the free-scan's pagespeed.py). Leave CWV unmeasured.
        notes = "PageSpeed Insights API key niet geconfigureerd of API-aanroep mislukt — Core Web Vitals niet gemeten."

    desktop_lighthouse: LighthouseScores | None = None
    if desktop_data:
        audits = desktop_data.get("lighthouseResult", {}).get("audits", {})
        lcp_val = audits.get("largest-contentful-paint", {}).get("numericValue")
        desktop_lcp = float(lcp_val) if lcp_val else None
        desktop_lighthouse = _lighthouse_from_response(desktop_data)

    # Real per-entity weight/blocking-time from the mobile run's own third-party audit —
    # used downstream to replace the synthetic size/blocking constants in third_party.py.
    third_party_summary = _third_party_summary_by_domain(mobile_data) if mobile_data else {}

    money_page_url, money_page_type, money_page_lcp, money_page_lcp_source, money_page_lighthouse = _money_page_result(
        money_page[0] if money_page else None,
        money_page[1] if money_page else None,
        money_page_data,
    )

    performance = Performance(
        mobile=mobile_cwv,
        desktop_lcp_ms=desktop_lcp,
        lighthouse=lighthouse,
        desktop_lighthouse=desktop_lighthouse,
        tbt_ms=tbt,
        speed_index_ms=speed_index,
        tti_ms=tti,
        render_blocking_resources=render_blocking,
        large_images_uncompressed=large_images,
        unused_javascript_kb=unused_js,
        total_page_weight_kb=page_weight,
        number_of_requests=req_count,
        money_page_url=money_page_url,
        money_page_type=money_page_type,  # type: ignore[arg-type]
        money_page_lcp_ms=money_page_lcp,
        money_page_lcp_source=money_page_lcp_source,  # type: ignore[arg-type]
        money_page_lighthouse=money_page_lighthouse,
        notes=notes,
    )
    return performance, third_party_summary


def _pick_money_page(pages: list[dict]) -> tuple[str, str] | None:
    """Pick an actual revenue page to measure — a PDP if one was scraped, else a
    collection page. Everything else in this module measures the homepage, which is
    commercially the least relevant page on the site."""
    sampled = sample_pages_by_type(pages)
    page = sampled.get("pdp")
    page_type = "pdp"
    if page is None:
        page = sampled.get("collection")
        page_type = "collection"
    if page is None:
        return None
    url = page.get("url")
    if not url:
        return None
    return url, page_type


def _money_page_result(
    url: str | None, page_type: str | None, data: dict | None,
) -> tuple[str | None, str | None, float | None, str | None, LighthouseScores | None]:
    if not data:
        return url, page_type, None, None, None

    lighthouse = _lighthouse_from_response(data)

    # PSI returns CrUX field data per the exact URL queried (`loadingExperience`), not
    # just per-origin — the same response already fetched for the lab LCP below can
    # carry a real-user figure for this specific page. It's absent when CrUX doesn't
    # have enough real-user traffic for this URL (common on lower-traffic PDP/collection
    # pages), in which case we fall back to the simulated Lighthouse run.
    field_lcp = _cwv_from_field_data(data).lcp_ms
    if field_lcp is not None:
        return url, page_type, field_lcp, "field", lighthouse

    audits = data.get("lighthouseResult", {}).get("audits", {})
    lcp_val = audits.get("largest-contentful-paint", {}).get("numericValue")
    lcp_ms = float(lcp_val) if lcp_val else None
    return url, page_type, lcp_ms, "lab" if lcp_ms is not None else None, lighthouse


def worst_mobile_lcp(performance: Performance | None) -> tuple[float | None, str | None]:
    """Best available mobile LCP signal for the store, preferring real-user data over
    simulated data wherever it exists.

    `performance.mobile.lcp_ms` is CrUX field data (real users) for the homepage.
    `performance.money_page_lcp_ms` is the money page's own PSI result, which is
    field data too whenever CrUX has enough real-user traffic for that specific URL
    (`money_page_lcp_source == "field"`) — that's the single best signal available
    (real users, on the actual revenue page) and is returned directly, no need to
    compare it against a different page's number.

    Only when the money page falls back to a simulated Lighthouse run
    (`money_page_lcp_source == "lab"`) do we not know which of the two figures better
    reflects reality, so we take the worse of the two as the conservative estimate —
    callers MUST surface the returned source in any text they generate, since a lab
    number should never be presented as if it were a real-user measurement. Falls
    back to `desktop_lcp_ms` only when no mobile figure is available at all.

    Returns `(lcp_ms, source)` with source in
    {"money_page_field", "field", "money_page_lab", "desktop", None}.
    """
    if performance is None:
        return None, None

    field_lcp = performance.mobile.lcp_ms if performance.mobile else None
    money_lcp = performance.money_page_lcp_ms

    if money_lcp is not None and performance.money_page_lcp_source == "field":
        return money_lcp, "money_page_field"

    if field_lcp is not None and money_lcp is not None:
        return (money_lcp, "money_page_lab") if money_lcp >= field_lcp else (field_lcp, "field")
    if field_lcp is not None:
        return field_lcp, "field"
    if money_lcp is not None:
        return money_lcp, "money_page_lab"
    if performance.desktop_lcp_ms is not None:
        return performance.desktop_lcp_ms, "desktop"
    return None, None


def lcp_source_caveat(performance: Performance | None, source: str | None) -> str:
    """Parenthetical caveat for any sentence built around `worst_mobile_lcp`'s result —
    empty for the homepage's own real-user data (the implicit baseline), otherwise
    states which page/measurement type produced the number. "money_page_field" is
    still real-user data (just for a specific page, not the origin default) so it
    gets an attribution note rather than the lab disclaimer."""
    if source == "desktop":
        return " (desktop-meting — mobiel niet gemeten, mobiel is meestal trager)"
    if source == "money_page_field":
        page_label = "productpagina" if performance and performance.money_page_type == "pdp" else "collectiepagina"
        url_suffix = f" ({performance.money_page_url})" if performance and performance.money_page_url else ""
        return f" (echte bezoekersdata van je {page_label}{url_suffix})"
    if source == "money_page_lab":
        page_label = "productpagina" if performance and performance.money_page_type == "pdp" else "collectiepagina"
        url_suffix = f" ({performance.money_page_url})" if performance and performance.money_page_url else ""
        return f" (labmeting op je {page_label}{url_suffix} — geen real-user meting)"
    return ""

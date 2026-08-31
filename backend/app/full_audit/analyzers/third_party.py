import functools
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.full_audit.schemas import DetectedScript, Necessity, ThirdPartyScripts

_CATALOG_PATH = Path(__file__).parent.parent / "data" / "third_party_catalog.json"


@functools.lru_cache(maxsize=1)
def _load_catalog() -> list[dict]:
    with open(_CATALOG_PATH) as f:
        return json.load(f)


def _catalog_by_domain() -> dict[str, dict]:
    return {entry["domain"]: entry for entry in _load_catalog()}


def _extract_external_domains(html: str, base_domain: str) -> dict[str, list[str]]:
    """Return {domain: [src_urls...]} for third-party resources.

    Deliberately excludes <img> — this feed drives "N apps/scripts running on your
    store" language and per-domain weight/blocking-time figures. Image hosts (font
    CDNs, payment-method badges, YouTube thumbnails, generic image CDNs) inflate the
    domain count without being an app or a script; they're not part of that story.
    """
    soup = BeautifulSoup(html, "lxml")
    domains: dict[str, list[str]] = {}

    selectors = [
        ("script", "src"),
        ("link", "href"),
        ("iframe", "src"),
    ]
    for tag_name, attr in selectors:
        for tag in soup.find_all(tag_name, **{attr: True}):
            url = str(tag.get(attr, "")).strip()
            if not url or url.startswith(("data:", "#", "javascript:")):
                continue
            try:
                parsed = urlparse(url)
                domain = parsed.netloc
                if not domain or domain == base_domain:
                    continue
                # Strip www. for grouping
                clean_domain = domain.removeprefix("www.")
                domains.setdefault(clean_domain, []).append(url)
            except Exception:
                continue
    return domains


def _dangerous_patterns(pages: list[dict], detected: list[DetectedScript]) -> list[str]:
    patterns = []
    for page in pages:
        html = page.get("html", "")
        # Check if tracking scripts load before consent banner
        has_tracker = any(
            s.name in ("Google Analytics 4", "Meta Pixel", "TikTok Pixel")
            for s in detected
            if s.necessity in ("useful", "critical")
        )
        has_cmp = any(
            s.name in ("Cookiebot", "OneTrust", "CookieYes", "Iubenda", "Osano")
            for s in detected
        )
        if has_tracker and not has_cmp:
            patterns.append("Tracking scripts loaded without detected consent management platform")
            break
    # Check for duplicate GTM containers
    all_html = " ".join(p.get("html", "") for p in pages)
    gtm_ids = set(re.findall(r"GTM-[A-Z0-9]+", all_html))
    if len(gtm_ids) > 1:
        patterns.append(f"Multiple GTM containers detected: {', '.join(sorted(gtm_ids))}")
    return patterns


async def scan_third_party(pages: list[dict]) -> ThirdPartyScripts:
    if not pages:
        return ThirdPartyScripts()

    catalog = _catalog_by_domain()
    homepage = pages[0]
    base_url = homepage.get("url", "")
    base_domain = urlparse(base_url).netloc.removeprefix("www.")

    all_domains: dict[str, list[str]] = {}
    for page in pages:
        html = page.get("html", "")
        page_domains = _extract_external_domains(html, base_domain)
        for domain, urls in page_domains.items():
            existing = all_domains.setdefault(domain, [])
            for u in urls:
                if u not in existing:
                    existing.append(u)

    detected_scripts: list[DetectedScript] = []

    for domain in all_domains:
        # Match against catalog (substring match on domain)
        entry = None
        for cat_domain, cat_entry in catalog.items():
            if cat_domain in domain or domain in cat_domain:
                entry = cat_entry
                break

        if entry:
            necessity: Necessity = entry["default_necessity"]
            monthly_cost = float(entry["est_monthly_cost_eur"])
            purpose = entry["purpose"]
            name = entry["name"]
            replaceable_by = entry.get("replaceable_by")
            recommendation = f"Consider replacing with: {replaceable_by}" if replaceable_by else None
        else:
            necessity = "useful"
            monthly_cost = 0.0
            purpose = "Unknown third-party resource"
            name = domain
            recommendation = None

        # Weight and blocking time are NOT set here — they used to be flat constants
        # (50/15/20 KB, blocking = size * 0.8) standing in for a measurement. They're
        # filled in by `apply_psi_third_party_measurements()` from PageSpeed Insights'
        # own third-party-summary audit, which actually measured the page load. A
        # domain PSI didn't observe stays unmeasured (None) rather than guessed.
        detected_scripts.append(DetectedScript(
            name=name,
            domain=domain,
            purpose=purpose,
            size_kb=None,
            blocking_time_ms=None,
            necessity=necessity,
            monthly_cost_eur=monthly_cost if monthly_cost > 0 else None,
            recommendation=recommendation,
        ))

    # No weight/blocking measurement yet to sort by — order by cost (the one real
    # number available at this stage) so paid tools surface first, then name.
    detected_scripts.sort(key=lambda s: (-(s.monthly_cost_eur or 0), s.name.lower()))

    dangerous = _dangerous_patterns(pages, detected_scripts)

    return ThirdPartyScripts(
        total_third_party_domains=len(all_domains),
        total_third_party_kb=None,
        total_third_party_blocking_ms=None,
        detected_scripts=detected_scripts,
        dangerous_patterns=dangerous,
    )


def apply_psi_third_party_measurements(
    third_party: ThirdPartyScripts | None,
    psi_summary: dict[str, dict],
) -> ThirdPartyScripts | None:
    """Overlay PageSpeed Insights' third-party-summary measurements (real transfer size
    + blocking time, attributed by Lighthouse's own entity classification) onto the
    HTML-detected script list from `scan_third_party`.

    PSI groups by "entity" (a business, e.g. "Google"), not literal hostname, so matching
    is substring-based in both directions — the same approach already used for the local
    third-party catalog. Domains PSI didn't observe on the page it measured stay
    unmeasured (None); we no longer fabricate a number to fill the gap.
    """
    if third_party is None:
        return None
    if not psi_summary:
        # No PSI data at all (no API key, or the call failed) — nothing to overlay.
        return third_party

    updated_scripts: list[DetectedScript] = []
    total_kb = 0.0
    total_blocking_ms = 0.0
    any_matched = False

    for script in third_party.detected_scripts:
        domain = (script.domain or "").lower()
        match = None
        for psi_key, data in psi_summary.items():
            if psi_key and (psi_key in domain or domain in psi_key):
                match = data
                break
        if match:
            any_matched = True
            size_kb = match["transfer_size_kb"]
            blocking_ms = match["blocking_ms"]
            total_kb += size_kb
            total_blocking_ms += blocking_ms
            updated_scripts.append(script.model_copy(update={
                "size_kb": size_kb,
                "blocking_time_ms": blocking_ms if blocking_ms > 0 else None,
            }))
        else:
            updated_scripts.append(script)

    if not any_matched:
        return third_party.model_copy(update={"detected_scripts": updated_scripts})

    # Now that real weight/blocking numbers exist, surface the heaviest offenders first.
    updated_scripts.sort(key=lambda s: (-(s.blocking_time_ms or 0), -(s.size_kb or 0)))

    return third_party.model_copy(update={
        "detected_scripts": updated_scripts,
        "total_third_party_kb": round(total_kb, 1),
        "total_third_party_blocking_ms": round(total_blocking_ms, 1),
    })

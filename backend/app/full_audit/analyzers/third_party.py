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
    """Return {domain: [src_urls...]} for third-party resources."""
    soup = BeautifulSoup(html, "lxml")
    domains: dict[str, list[str]] = {}

    selectors = [
        ("script", "src"),
        ("link", "href"),
        ("iframe", "src"),
        ("img", "src"),
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
                clean_domain = domain.lstrip("www.")
                domains.setdefault(clean_domain, []).append(url)
            except Exception:
                continue
    return domains


def _is_blocking(html: str, src_url: str) -> bool:
    """Heuristic: script is blocking if in <head> without async/defer."""
    soup = BeautifulSoup(html, "lxml")
    head = soup.find("head")
    if not head:
        return False
    for tag in head.find_all("script", src=True):
        tag_src = str(tag.get("src", ""))
        if src_url in tag_src:
            return not (tag.get("async") is not None or tag.get("defer") is not None)
    return False


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
    base_domain = urlparse(base_url).netloc.lstrip("www.")

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
    total_kb = 0.0
    total_blocking_ms = 0.0

    for domain, urls in all_domains.items():
        # Match against catalog (substring match on domain)
        entry = None
        for cat_domain, cat_entry in catalog.items():
            if cat_domain in domain or domain in cat_domain:
                entry = cat_entry
                break

        if entry:
            necessity: Necessity = entry["default_necessity"]
            monthly_cost = float(entry["est_monthly_cost_eur"])
            size_kb = 50.0 if monthly_cost > 0 else 15.0
            purpose = entry["purpose"]
            name = entry["name"]
            replaceable_by = entry.get("replaceable_by")
            recommendation = f"Consider replacing with: {replaceable_by}" if replaceable_by else None
        else:
            necessity = "useful"
            monthly_cost = 0.0
            size_kb = 20.0
            purpose = "Unknown third-party resource"
            name = domain
            recommendation = None

        # Blocking time heuristic
        blocking = False
        for page in pages:
            for src_url in urls:
                if _is_blocking(page.get("html", ""), src_url):
                    blocking = True
                    break
        blocking_ms = size_kb * 0.8 if blocking else 0.0

        total_kb += size_kb
        total_blocking_ms += blocking_ms

        detected_scripts.append(DetectedScript(
            name=name,
            domain=domain,
            purpose=purpose,
            size_kb=round(size_kb, 1),
            blocking_time_ms=round(blocking_ms, 1) if blocking_ms else None,
            necessity=necessity,
            monthly_cost_eur=monthly_cost if monthly_cost > 0 else None,
            recommendation=recommendation,
        ))

    # Sort: blocking first, then by size
    detected_scripts.sort(key=lambda s: (-(s.blocking_time_ms or 0), -(s.size_kb or 0)))

    dangerous = _dangerous_patterns(pages, detected_scripts)

    return ThirdPartyScripts(
        total_third_party_domains=len(all_domains),
        total_third_party_kb=round(total_kb, 1),
        total_third_party_blocking_ms=round(total_blocking_ms, 1),
        detected_scripts=detected_scripts,
        dangerous_patterns=dangerous,
    )

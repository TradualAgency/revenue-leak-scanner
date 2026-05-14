import functools
import json
import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

from app.full_audit.schemas import SiteSearchHealth, VendorDetection

logger = logging.getLogger(__name__)


@functools.lru_cache
def _load_sigs() -> list[dict]:
    path = Path(__file__).parent.parent / "data" / "site_search_signatures.json"
    return json.loads(path.read_text())


async def detect_site_search(pages: list[dict]) -> SiteSearchHealth:
    try:
        html_combined = "\n".join(p.get("html", "") for p in pages)
        found: list[VendorDetection] = []

        for sig in _load_sigs():
            hits: list[str] = []
            for pattern in sig.get("script_patterns", []):
                if re.search(re.escape(pattern), html_combined, re.IGNORECASE):
                    hits.append(f"script:{pattern}")
            for pattern in sig.get("dom_patterns", []):
                if re.search(re.escape(pattern), html_combined, re.IGNORECASE):
                    hits.append(f"dom:{pattern}")
            if hits:
                found.append(VendorDetection(
                    name=sig["name"],
                    confidence="confirmed",
                    evidence="; ".join(hits[:2]),
                ))

        native = False
        for page in pages:
            try:
                soup = BeautifulSoup(page.get("html", ""), "lxml")
                for form in soup.find_all("form"):
                    if "search" in str(form.get("action", "")).lower():
                        native = True
                        break
                if not native and soup.find("input", type="search"):
                    native = True
            except Exception:
                pass
            if native:
                break

        provider = found[0].name if found else ("Native" if native else None)
        evidence = "; ".join(f"{v.name}: {v.evidence}" for v in found[:3]) if found else None

        return SiteSearchHealth(
            provider_detected=provider,
            detected_vendors=found,
            native_search_present=native,
            evidence=evidence,
        )
    except Exception as exc:
        logger.warning("site_search analyzer failed: %s", exc)
        return SiteSearchHealth()

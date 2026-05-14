import functools
import json
import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

from app.full_audit.schemas import ReturnsHealth, VendorDetection

logger = logging.getLogger(__name__)


@functools.lru_cache
def _load_sigs() -> list[dict]:
    path = Path(__file__).parent.parent / "data" / "returns_signatures.json"
    return json.loads(path.read_text())


async def detect_returns(pages: list[dict]) -> ReturnsHealth:
    try:
        html_combined = "\n".join(p.get("html", "") for p in pages)
        found: list[VendorDetection] = []
        portal_url: str | None = None

        for sig in _load_sigs():
            hits: list[str] = []
            for pattern in sig.get("script_patterns", []):
                if re.search(re.escape(pattern), html_combined, re.IGNORECASE):
                    hits.append(f"script:{pattern}")
            for pattern in sig.get("link_patterns", []):
                if re.search(re.escape(pattern), html_combined, re.IGNORECASE):
                    hits.append(f"link:{pattern}")
            if hits:
                found.append(VendorDetection(
                    name=sig["name"],
                    confidence="confirmed",
                    evidence="; ".join(hits[:2]),
                ))

        # Try to find an explicit returns portal href
        for page in pages:
            try:
                soup = BeautifulSoup(page.get("html", ""), "lxml")
                for a in soup.find_all("a", href=True):
                    href = str(a.get("href", ""))
                    if any(kw in href.lower() for kw in ("return", "retour", "ruilen")):
                        portal_url = href
                        break
            except Exception:
                pass
            if portal_url:
                break

        providers = [v.name for v in found]
        evidence = "; ".join(f"{v.name}: {v.evidence}" for v in found[:3]) if found else None

        return ReturnsHealth(
            providers_detected=providers,
            detected_vendors=found,
            returns_portal_url=portal_url,
            evidence=evidence,
        )
    except Exception as exc:
        logger.warning("returns analyzer failed: %s", exc)
        return ReturnsHealth()

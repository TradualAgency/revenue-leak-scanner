import functools
import json
import logging
import re
from pathlib import Path

from app.full_audit.schemas import MarketplacePresence

logger = logging.getLogger(__name__)


@functools.lru_cache
def _load_sigs() -> list[dict]:
    path = Path(__file__).parent.parent / "data" / "marketplace_signatures.json"
    return json.loads(path.read_text())

_REVIEW_PLATFORMS = {"Trustpilot", "Kiyoh", "Google Reviews", "Bazaarvoice", "Yotpo"}


async def detect_marketplaces(pages: list[dict]) -> MarketplacePresence:
    try:
        html_combined = "\n".join(p.get("html", "") for p in pages)
        marketplaces: list[str] = []
        review_platforms: list[str] = []
        evidence_hits: list[str] = []

        for sig in _load_sigs():
            hits: list[str] = []
            for pattern in sig.get("script_patterns", []):
                if re.search(re.escape(pattern), html_combined, re.IGNORECASE):
                    hits.append(f"script:{pattern}")
            for pattern in sig.get("link_patterns", []):
                if re.search(re.escape(pattern), html_combined, re.IGNORECASE):
                    hits.append(f"link:{pattern}")
            if hits:
                name = sig["name"]
                if name in _REVIEW_PLATFORMS:
                    review_platforms.append(name)
                else:
                    marketplaces.append(name)
                evidence_hits.append(f"{name}: {hits[0]}")

        return MarketplacePresence(
            platforms_detected=marketplaces,
            review_platforms_detected=review_platforms,
            evidence="; ".join(evidence_hits[:6]) if evidence_hits else None,
        )
    except Exception as exc:
        logger.warning("marketplaces analyzer failed: %s", exc)
        return MarketplacePresence()

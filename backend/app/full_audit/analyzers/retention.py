import functools
import json
import logging
import re
from pathlib import Path

from app.full_audit.schemas import RetentionHealth, VendorDetection

logger = logging.getLogger(__name__)


@functools.lru_cache
def _load_sigs() -> list[dict]:
    path = Path(__file__).parent.parent / "data" / "retention_signatures.json"
    return json.loads(path.read_text())


async def detect_retention(pages: list[dict]) -> RetentionHealth:
    try:
        html_combined = "\n".join(p.get("html", "") for p in pages)
        by_category: dict[str, list[VendorDetection]] = {"subscription": [], "loyalty": [], "bundling": []}

        for sig in _load_sigs():
            hits: list[str] = []
            for pattern in sig.get("script_patterns", []):
                if re.search(re.escape(pattern), html_combined, re.IGNORECASE):
                    hits.append(f"script:{pattern}")
            for pattern in sig.get("dom_patterns", []):
                if re.search(re.escape(pattern), html_combined, re.IGNORECASE):
                    hits.append(f"dom:{pattern}")
            if hits:
                category = sig.get("category", "")
                if category in by_category:
                    by_category[category].append(VendorDetection(
                        name=sig["name"],
                        confidence="confirmed",
                        evidence="; ".join(hits[:2]),
                    ))

        all_found = by_category["subscription"] + by_category["loyalty"] + by_category["bundling"]
        evidence = "; ".join(f"{v.name}: {v.evidence}" for v in all_found[:6]) if all_found else None

        return RetentionHealth(
            subscription_detected=by_category["subscription"],
            loyalty_detected=by_category["loyalty"],
            bundling_detected=by_category["bundling"],
            evidence=evidence,
        )
    except Exception as exc:
        logger.warning("retention analyzer failed: %s", exc)
        return RetentionHealth()

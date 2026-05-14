import functools
import json
import logging
import re
from pathlib import Path

from app.full_audit.schemas import ShippingHealth, VendorDetection

logger = logging.getLogger(__name__)


@functools.lru_cache
def _load_sigs() -> list[dict]:
    path = Path(__file__).parent.parent / "data" / "shipping_signatures.json"
    return json.loads(path.read_text())


async def detect_shipping(pages: list[dict]) -> ShippingHealth:
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

        providers = [v.name for v in found]
        evidence = "; ".join(f"{v.name}: {v.evidence}" for v in found[:4]) if found else None

        return ShippingHealth(
            providers_detected=providers,
            detected_vendors=found,
            evidence=evidence,
        )
    except Exception as exc:
        logger.warning("shipping analyzer failed: %s", exc)
        return ShippingHealth()

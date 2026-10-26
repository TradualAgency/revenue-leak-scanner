import functools
import json
import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

from app.full_audit.page_sampling import sample_pages_by_type
from app.full_audit.schemas import ShippingHealth, VendorDetection

logger = logging.getLogger(__name__)


@functools.lru_cache
def _load_sigs() -> list[dict]:
    path = Path(__file__).parent.parent / "data" / "shipping_signatures.json"
    return json.loads(path.read_text())


_SHIPPING_WORDS = r"(?:verzend(?:ing|kosten)?|bezorg(?:ing|kosten)?|levering|shipping|delivery|versand(?:kosten)?|livraison)"
_FREE_WORDS = r"(?:gratis|free|kostenlos(?:er|e)?|gratuite?)"
_AMOUNT = r"€\s?(\d{1,4}(?:[.,]\d{2})?)|(\d{1,4}(?:[.,]\d{2})?)\s?(?:€|euro|eur)\b"
_THRESHOLD_RE = re.compile(
    _FREE_WORDS + r"\s+" + _SHIPPING_WORDS + r"[^.€\d]{0,40}?(?:vanaf|boven|over|from|ab|dès|à partir de)\s*(?:" + _AMOUNT + ")",
    re.IGNORECASE,
)
_COST_RE = re.compile(
    _SHIPPING_WORDS + r"[^.]{0,60}?(?:" + _AMOUNT + "|" + _FREE_WORDS + ")"
    + "|" + _FREE_WORDS + r"\s+" + _SHIPPING_WORDS,
    re.IGNORECASE,
)


def _amount(match: re.Match) -> float | None:
    raw = next((g for g in match.groups() if g), None)
    try:
        return float(raw.replace(",", ".")) if raw else None
    except ValueError:
        return None


def shipping_cost_info(pages: list[dict]) -> tuple[bool | None, float | None, str | None]:
    """(cost info on the product page?, free-shipping threshold, evidence). Judged on the
    visible text of one sampled product page — announcement bars and USP lists are part
    of that page, so a site-wide "gratis verzending vanaf €50" counts."""
    pdp = sample_pages_by_type(pages).get("pdp")
    if pdp is None:
        return None, None, None
    text = " ".join(BeautifulSoup(pdp.get("html", ""), "lxml").get_text(" ").split())
    if m := _THRESHOLD_RE.search(text):
        return True, _amount(m), m.group(0)[:120]
    if m := _COST_RE.search(text):
        return True, None, m.group(0)[:120]
    return False, None, None


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

        cost_info, threshold, cost_evidence = shipping_cost_info(pages)
        return ShippingHealth(
            providers_detected=providers,
            detected_vendors=found,
            evidence=evidence,
            cost_info_on_pdp=cost_info,
            free_shipping_threshold_eur=threshold,
            cost_info_evidence=cost_evidence,
        )
    except Exception as exc:
        logger.warning("shipping analyzer failed: %s", exc)
        return ShippingHealth()

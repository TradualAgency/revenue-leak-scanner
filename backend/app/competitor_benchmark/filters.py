"""Pure filter pipeline that decides which DataForSEO candidates are plausible
competitors. This is the fix for the amazon.com/ebay.com/etsy.com regression: the old
implementation (analyzers/competitor_benchmark.py) took the first 3 domains DataForSEO
ranked by keyword overlap and only filtered social networks + same-brand matches —
nothing compared a candidate's size against the store's own, so the biggest domains in
the market always won (olafhussein.com, 89 keywords, got amazon.com at 39,044,800 — a
438,706x ratio).

The size band in `_check_size_band` is the structural fix; the blocklist is a safety
net, not the primary mechanism, because a blocklist can never be complete.

Deliberately pure and dict-in/dict-out at the boundary: no I/O, no pydantic
validation of the input, so recorded DataForSEO JSON fixtures can be replayed through
this module in tests without spending API credits on the layer where all the value is.
"""

from __future__ import annotations

import functools
import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from app.competitor_benchmark.market import TLDS_BY_LANGUAGE, brand_label, is_same_brand
from app.competitor_benchmark.schemas import CandidateDomain, RejectedCandidate
from app.domains import extract_domain

_BLOCKLIST_PATH = Path(__file__).parent / "data" / "non_competitor_domains.json"

# Absolute floor/ceiling on the acceptable keyword-count band. A pure ratio band around
# a small store (e.g. 89 keywords) gives [~9, ~1068] — too tight in absolute terms for
# the realistic small-niche-DTC universe, where a genuine peer might sit at 40 or 1500
# keywords regardless of the exact ratio to the audited store.
MIN_KEYWORDS_FLOOR = 50
MAX_KEYWORDS_CEILING = 2_000
KEYWORDS_LOWER_RATIO = 0.10
KEYWORDS_UPPER_RATIO = 12.0
ETV_LOWER_RATIO = 0.05
ETV_UPPER_RATIO = 20.0
# Safety net when the store itself has no DataForSEO footprint (own domain_rank_overview
# call failed/empty): reject anything more than 25x the candidate set's own median —
# amazon.com at ~39M against a niche candidate-set median of a few thousand is tens of
# thousands of times over, so this still catches the mega-marketplace case with zero
# store metrics to compare against.
MEDIAN_FALLBACK_RATIO = 25.0
MIN_INTERSECTIONS_FLOOR = 5
MIN_INTERSECTIONS_STORE_RATIO = 0.03
MIN_SERP_KEYWORD_HITS = 3

_GTLD_ALLOWLIST = {"com", "shop", "store", "eu", "io"}


@functools.lru_cache(maxsize=1)
def _load_blocklist() -> list[dict]:
    with open(_BLOCKLIST_PATH) as f:
        return json.load(f)["entries"]


def _tld(domain: str) -> str:
    return domain.rsplit(".", 1)[-1].lower()


def blocklist_match(domain: str) -> dict | None:
    reg = extract_domain(domain)
    label = brand_label(domain)
    for entry in _load_blocklist():
        pattern = entry["pattern"].lower()
        if entry["match"] == "registrable":
            if reg == pattern or reg.endswith(f".{pattern}"):
                return entry
        elif entry["match"] == "brand_any_tld":
            if label == pattern:
                return entry
    return None


@dataclass(frozen=True)
class StoreMetrics:
    domain: str
    organic_keywords_count: int | None = None
    est_organic_traffic_value_usd: float | None = None


def _size_ratio(candidate_k: int | None, store_k: int | None) -> float | None:
    if candidate_k is None or not store_k:
        return None
    return candidate_k / store_k


def _check_size_band(candidate: dict, store: StoreMetrics, candidate_median_k: float | None) -> str | None:
    """Returns a rejection reason string, or None if the candidate passes."""
    k_c = candidate.get("organic_keywords_count")
    etv_c = candidate.get("est_organic_traffic_value_usd")

    if store.organic_keywords_count:
        k_store = store.organic_keywords_count
        if k_c is None and etv_c is None:
            return "size_band"  # no data to prove this candidate isn't a mega-site
        if k_c is not None:
            lower = max(KEYWORDS_LOWER_RATIO * k_store, MIN_KEYWORDS_FLOOR)
            upper = max(KEYWORDS_UPPER_RATIO * k_store, MAX_KEYWORDS_CEILING)
            if not (lower <= k_c <= upper):
                return "size_band"
        if store.est_organic_traffic_value_usd and etv_c is not None:
            etv_store = store.est_organic_traffic_value_usd
            lower_etv = ETV_LOWER_RATIO * etv_store
            upper_etv = ETV_UPPER_RATIO * etv_store
            if not (lower_etv <= etv_c <= upper_etv):
                return "size_band"
        return None

    # Fallback: no store keyword count available (domain_rank_overview failed/empty).
    if candidate_median_k and k_c is not None:
        if k_c > MEDIAN_FALLBACK_RATIO * candidate_median_k:
            return "size_band"
    return None


def _check_min_intersections(candidate: dict, store: StoreMetrics) -> bool:
    source = candidate.get("discovery_source")
    if source == "serp_competitors":
        return (candidate.get("serp_keyword_hits") or 0) >= MIN_SERP_KEYWORD_HITS
    intersections = candidate.get("intersections")
    if intersections is None:
        return False
    floor = MIN_INTERSECTIONS_FLOOR
    if store.organic_keywords_count:
        floor = max(MIN_INTERSECTIONS_FLOOR, MIN_INTERSECTIONS_STORE_RATIO * store.organic_keywords_count)
    return intersections >= floor


def _check_market_coherence(domain: str, store_domain: str, market_language_code: str | None) -> bool:
    tld = _tld(domain)
    if tld in _GTLD_ALLOWLIST:
        return True
    if tld == _tld(store_domain):
        return True
    if market_language_code and tld in TLDS_BY_LANGUAGE.get(market_language_code, set()):
        return True
    return False


_REASON_NL = {
    "self": "dit is de gescande store zelf",
    "same_brand": "zelfde merk (andere regio/subdomein)",
    "blocklist": "bekend als {category}, geen directe concurrent",
    "size_band": "grootte wijkt te sterk af van je eigen store — waarschijnlijk geen vergelijkbare concurrent",
    "min_intersections": "te weinig gedeelde zoekwoorden om overlap aan te tonen",
    "market_coherence": "domein hoort niet bij de gedetecteerde markt",
}


def apply_filters(
    candidates: list[dict],
    store: StoreMetrics,
    market_language_code: str | None = None,
) -> tuple[list[CandidateDomain], list[RejectedCandidate]]:
    """`candidates` is a list of normalized dicts (see discovery.py for how raw
    DataForSEO responses are shaped into this form):
    {domain, discovery_source, organic_keywords_count, est_organic_traffic_value_usd,
     avg_keyword_position, intersections, serp_keyword_hits}
    """
    kept: list[CandidateDomain] = []
    rejected: list[RejectedCandidate] = []

    k_values = [c["organic_keywords_count"] for c in candidates if c.get("organic_keywords_count")]
    candidate_median_k = statistics.median(k_values) if k_values else None

    store_reg = extract_domain(store.domain)

    for candidate in candidates:
        domain = candidate.get("domain") or ""
        if not domain:
            continue
        reg = extract_domain(domain)

        if reg == store_reg:
            rejected.append(RejectedCandidate(domain=domain, reason_code="self", reason_nl=_REASON_NL["self"]))
            continue

        if is_same_brand(domain, store.domain):
            rejected.append(RejectedCandidate(domain=domain, reason_code="same_brand", reason_nl=_REASON_NL["same_brand"]))
            continue

        block = blocklist_match(domain)
        if block is not None:
            rejected.append(RejectedCandidate(
                domain=domain, reason_code="blocklist",
                reason_nl=_REASON_NL["blocklist"].format(category=block["category"]),
                category=block["category"],
            ))
            continue

        size_reject = _check_size_band(candidate, store, candidate_median_k)
        if size_reject is not None:
            rejected.append(RejectedCandidate(domain=domain, reason_code="size_band", reason_nl=_REASON_NL["size_band"]))
            continue

        if not _check_min_intersections(candidate, store):
            rejected.append(RejectedCandidate(
                domain=domain, reason_code="min_intersections", reason_nl=_REASON_NL["min_intersections"],
            ))
            continue

        if not _check_market_coherence(domain, store.domain, market_language_code):
            rejected.append(RejectedCandidate(
                domain=domain, reason_code="market_coherence", reason_nl=_REASON_NL["market_coherence"],
            ))
            continue

        kept.append(CandidateDomain(
            domain=domain,
            discovery_source=candidate.get("discovery_source", "competitors_domain"),
            organic_keywords_count=candidate.get("organic_keywords_count"),
            est_organic_traffic_value_usd=candidate.get("est_organic_traffic_value_usd"),
            avg_keyword_position=candidate.get("avg_keyword_position"),
            intersections=candidate.get("intersections"),
            serp_keyword_hits=candidate.get("serp_keyword_hits"),
            size_ratio_to_store=_size_ratio(candidate.get("organic_keywords_count"), store.organic_keywords_count),
        ))

    return kept, rejected

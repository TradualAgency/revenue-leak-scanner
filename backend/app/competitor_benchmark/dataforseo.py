from __future__ import annotations

import base64
import logging

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.dataforseo.com/v3"
_TIMEOUT = aiohttp.ClientTimeout(total=45.0)

# Over-fetched wide, then filtered hard by filters.py — the previous limit of 15 with a
# take-first-3 rule left almost no room for a size-band filter to work with. Verify
# against DataForSEO's pricing page before raising further; some Labs endpoints price
# per returned row.
COMPETITORS_FETCH_LIMIT = 100
RANKED_KEYWORDS_FETCH_LIMIT = 50
SERP_COMPETITORS_KEYWORD_SEED_LIMIT = 20


def credentials_configured() -> bool:
    return bool(settings.DATAFORSEO_LOGIN and settings.DATAFORSEO_PASSWORD)


def _auth_header() -> dict[str, str]:
    token = base64.b64encode(f"{settings.DATAFORSEO_LOGIN}:{settings.DATAFORSEO_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


async def _post(session: aiohttp.ClientSession, path: str, body: list[dict]) -> dict | None:
    try:
        async with session.post(f"{_API_BASE}{path}", json=body) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.warning("DataForSEO %s returned %s: %s", path, resp.status, text[:300])
                return None
            data = await resp.json()
    except Exception as exc:
        # Observed in practice: some large domains cause DataForSEO Labs to return a
        # task-level 500 or simply hang well past a reasonable timeout. Either way this
        # is "no data available for this call", not a reason to fail the whole run.
        logger.warning("DataForSEO request failed for %s: %s", path, exc)
        return None

    tasks = data.get("tasks") or []
    if not tasks or tasks[0].get("status_code") != 20000:
        logger.warning("DataForSEO task error for %s: %s", path, tasks[0].get("status_message") if tasks else "no tasks")
        return None
    return tasks[0]


def new_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(timeout=_TIMEOUT, headers=_auth_header())


async def fetch_domain_rank_overview(
    session: aiohttp.ClientSession, domain: str, location_code: int, language_code: str,
) -> dict | None:
    task = await _post(
        session,
        "/dataforseo_labs/google/domain_rank_overview/live",
        [{"target": domain, "location_code": location_code, "language_code": language_code}],
    )
    result = (task or {}).get("result") or []
    if result and result[0] and result[0].get("items"):
        organic = result[0]["items"][0].get("metrics", {}).get("organic", {})
        return {"organic_keywords_count": organic.get("count"), "est_organic_traffic_value_usd": organic.get("etv")}
    return None


async def fetch_competitors_domain(
    session: aiohttp.ClientSession, domain: str, location_code: int, language_code: str,
    limit: int = COMPETITORS_FETCH_LIMIT,
) -> list[dict]:
    task = await _post(
        session,
        "/dataforseo_labs/google/competitors_domain/live",
        [{"target": domain, "location_code": location_code, "language_code": language_code, "limit": limit}],
    )
    result = (task or {}).get("result") or []
    if result and result[0] and result[0].get("items"):
        return result[0]["items"]
    return []


async def fetch_ranked_keywords(
    session: aiohttp.ClientSession, domain: str, location_code: int, language_code: str,
    limit: int = RANKED_KEYWORDS_FETCH_LIMIT,
) -> list[dict]:
    """Store's own top organic keywords by ETV, used to seed serp_competitors."""
    task = await _post(
        session,
        "/dataforseo_labs/google/ranked_keywords/live",
        [{
            "target": domain, "location_code": location_code, "language_code": language_code,
            "limit": limit,
            "order_by": ["keyword_data.keyword_info.etv,desc"],
            "filters": [["keyword_data.keyword_info.search_volume", ">", 0]],
        }],
    )
    result = (task or {}).get("result") or []
    if result and result[0] and result[0].get("items"):
        return result[0]["items"]
    return []


async def fetch_serp_competitors(
    session: aiohttp.ClientSession, domain: str, keywords: list[str], location_code: int, language_code: str,
) -> list[dict]:
    """Who else ranks on the store's own money keywords — a structurally different
    signal from competitors_domain's whole-domain keyword overlap, which is exactly
    the metric that lets a mega-marketplace outrank a niche store's real peers."""
    if not keywords:
        return []
    task = await _post(
        session,
        "/dataforseo_labs/google/serp_competitors/live",
        [{
            "target": domain, "location_code": location_code, "language_code": language_code,
            "keywords": keywords[:SERP_COMPETITORS_KEYWORD_SEED_LIMIT],
        }],
    )
    result = (task or {}).get("result") or []
    if result and result[0] and result[0].get("items"):
        return result[0]["items"]
    return []

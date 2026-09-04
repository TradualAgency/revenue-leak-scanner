from __future__ import annotations

import logging

import aiohttp

from app.config import settings
from app.domains import extract_domain
from app.full_audit.schemas import SeRankingTraffic

logger = logging.getLogger(__name__)

_API_BASE = "https://api.seranking.com/v1"
_TIMEOUT = aiohttp.ClientTimeout(total=15.0)

__all__ = ["extract_domain", "fetch_traffic_estimates"]


async def fetch_traffic_estimates(store_url: str) -> SeRankingTraffic | None:
    if not settings.SERANKING_API_KEY:
        logger.debug("SERANKING_API_KEY not configured — skipping traffic lookup")
        return None

    domain = extract_domain(store_url)
    headers = {"Authorization": f"Token {settings.SERANKING_API_KEY}"}
    params = {"domain": domain, "with_subdomains": 1}

    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(
                f"{_API_BASE}/domain/overview/worldwide",
                headers=headers,
                params=params,
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.warning("SE Ranking API %s for %s: %s", resp.status, domain, body[:200])
                    return None
                data: dict = await resp.json()
    except Exception as exc:
        logger.warning("SE Ranking request failed for %s: %s", domain, exc)
        return None

    organic = data.get("organic") or []
    adv = data.get("adv") or []

    # Worldwide endpoint returns lists; first element is the global aggregate.
    org = organic[0] if organic else {}
    paid = adv[0] if adv else {}

    monthly_organic = int(org.get("traffic_sum") or 0)
    monthly_paid = int(paid.get("traffic_sum") or 0)

    if monthly_organic == 0 and monthly_paid == 0:
        logger.info("SE Ranking returned zero traffic for %s — falling back to heuristic", domain)
        return None

    return SeRankingTraffic(
        domain=domain,
        monthly_organic_sessions=monthly_organic,
        monthly_paid_sessions=monthly_paid,
        organic_keywords_count=int(org.get("keywords_count") or 0),
        paid_keywords_count=int(paid.get("keywords_count") or 0),
        # SE Ranking returns price_sum in USD cents
        est_organic_traffic_value_usd=float(org.get("price_sum") or 0.0) / 100,
        raw_response=data,
    )

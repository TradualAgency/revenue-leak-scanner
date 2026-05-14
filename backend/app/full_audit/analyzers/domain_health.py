import asyncio
import logging
import re
from urllib.parse import urlparse

import aiohttp

from app.full_audit.schemas import DomainHealth

logger = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=10)


async def _head(session: aiohttp.ClientSession, url: str, allow_redirects: bool = True):
    try:
        async with session.head(url, allow_redirects=allow_redirects, timeout=_TIMEOUT) as r:
            return r.status, dict(r.headers), str(r.url)
    except Exception:
        return None, {}, url


async def analyze_domain_health(store_url: str, pages: list[dict]) -> DomainHealth:
    try:
        parsed = urlparse(store_url)
        domain = parsed.hostname or ""
        if not domain:
            return DomainHealth()

        # HSTS from scraped homepage headers
        hp_headers = {k.lower(): v for k, v in (pages[0].get("headers", {}) if pages else {}).items()}
        hsts_header = hp_headers.get("strict-transport-security", "")
        hsts_enabled = bool(hsts_header)
        hsts_max_age_days: int | None = None
        if hsts_enabled:
            m = re.search(r"max-age=(\d+)", hsts_header, re.IGNORECASE)
            if m:
                hsts_max_age_days = int(int(m.group(1)) / 86400)

        async with aiohttp.ClientSession() as session:
            # HTTP → HTTPS redirect
            _, _, http_final = await _head(session, f"http://{domain}")
            http_to_https = http_final.startswith("https://") if http_final else None

            # www ↔ apex redirect
            is_www = domain.startswith("www.")
            apex = domain.removeprefix("www.")
            alt_host = f"www.{apex}" if not is_www else apex
            alt_status, _, alt_final = await _head(session, f"https://{alt_host}")

            if alt_status and alt_status < 400 and alt_final:
                if not is_www and alt_final.startswith(f"https://{domain}"):
                    www_redirect_status = "www-to-apex"
                elif is_www and alt_final.startswith(f"https://{domain}"):
                    www_redirect_status = "apex-to-www"
                else:
                    www_redirect_status = "inconsistent"
            else:
                www_redirect_status = "inconsistent"

            # Redirect chain depth
            chain_len = 0
            current = store_url
            visited: set[str] = set()
            for _ in range(10):
                if current in visited:
                    break
                visited.add(current)
                s, h, _ = await _head(session, current, allow_redirects=False)
                if s in (301, 302, 303, 307, 308):
                    chain_len += 1
                    loc = h.get("location", h.get("Location", ""))
                    if not loc:
                        break
                    if loc.startswith("/"):
                        p = urlparse(current)
                        loc = f"{p.scheme}://{p.netloc}{loc}"
                    current = loc
                else:
                    break

        # IPv6
        ipv6 = False
        try:
            import dns.resolver
            aaaa = await asyncio.to_thread(dns.resolver.resolve, domain, "AAAA", lifetime=5.0)
            ipv6 = len(list(aaaa)) > 0
        except Exception:
            pass

        evidence_parts = []
        if hsts_header:
            evidence_parts.append(f"HSTS: {hsts_header[:80]}")
        if chain_len > 0:
            evidence_parts.append(f"redirect chain: {chain_len}")
        if not http_to_https:
            evidence_parts.append("HTTP→HTTPS niet geforceerd")

        return DomainHealth(
            hsts_enabled=hsts_enabled,
            hsts_max_age_days=hsts_max_age_days,
            www_redirect_status=www_redirect_status,  # type: ignore[arg-type]
            http_to_https_forced=http_to_https,
            ipv6_enabled=ipv6,
            redirect_chain_length=chain_len,
            evidence="; ".join(evidence_parts) if evidence_parts else None,
        )
    except Exception as exc:
        logger.warning("domain_health analyzer failed: %s", exc)
        return DomainHealth()

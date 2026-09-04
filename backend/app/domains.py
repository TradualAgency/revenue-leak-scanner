"""Domain normalization shared by every analyzer that has to turn "whatever the user
or an API gave us" into a comparable host.

This used to live in `full_audit/analyzers/seranking.py`, which meant
`competitor_benchmark` imported its domain handling from an unrelated SEO-vendor
module — and, worse, that the operator's manual-competitor input path skipped it
entirely and pushed raw strings like `https://shop.nl` into the measurement pipeline
(which then built `https://https://shop.nl` and recorded the domain as unreachable).

One normalizer, used at every ingress point.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Platforms whose root domain carries traffic for all stores — subdomains are store-specific,
# so we must NOT roll up to the root.
_SHARED_PLATFORMS = {"myshopify.com", "squarespace.com", "wixsite.com", "webflow.io"}

# A hostname we are willing to treat as a store: at least two dot-separated labels, an
# alphabetic TLD (so bare IPv4 is rejected), 1-253 chars overall.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)


def extract_domain(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.hostname or url).lower().removeprefix("www.")
    for platform in _SHARED_PLATFORMS:
        if host.endswith(f".{platform}") or host == platform:
            return host
    return host


def normalize_competitor_input(raw: str) -> str | None:
    """Turn free-text operator input into a comparable domain, or None if it can't be one.

    Accepts `https://Shop.NL/collections/all?x=1`, `www.shop.nl`, `shop.nl` — all three
    become `shop.nl`. Returns None for empty input, IP literals, `localhost`, bare TLDs
    and anything else that isn't a routable hostname, so callers can report it as
    invalid instead of measuring it and reporting "unreachable" three minutes later.
    """
    if not raw:
        return None
    candidate = raw.strip()
    if not candidate or re.search(r"\s", candidate):
        return None

    host = extract_domain(candidate).rstrip(".")
    if not host:
        return None

    # IDN (e.g. `café.nl`) — compare and store the ASCII form, which is what DNS,
    # the scraper and the snapshot cache all key on.
    if not host.isascii():
        try:
            host = host.encode("idna").decode("ascii")
        except (UnicodeError, UnicodeDecodeError):
            return None

    return host if _HOSTNAME_RE.match(host) else None


def same_registrable(a: str, b: str) -> bool:
    """True when two inputs point at the same host once normalized."""
    return bool(a) and bool(b) and extract_domain(a).rstrip(".") == extract_domain(b).rstrip(".")

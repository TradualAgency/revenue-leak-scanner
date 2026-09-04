"""Decides which manually-supplied competitor domains are admitted to a run.

Deliberately pure and I/O-free, like `filters.py`: this is the layer where all the
value is, so it must be testable without a database, a network or API credits. Both
entry points (seeds at run creation, adds on an existing run) go through
`resolve_seeds`, which is what stops the two paths drifting apart again — the previous
implementation normalized the store's own domain but appended operator input verbatim,
so `https://shop.nl` reached the measurement pipeline as-is and always came back
unreachable.

Rejections vs. warnings is a deliberate split. Only two things are hard rejects: input
that cannot be a domain, and the audited store itself (which would otherwise land in
its own market median). Everything else the operator asked for is admitted with a
visible warning, because operator intent beats a heuristic — but silently is not an
option either.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.competitor_benchmark.filters import blocklist_match
from app.competitor_benchmark.market import is_same_brand
from app.domains import normalize_competitor_input, same_registrable

SeedStatus = Literal["accepted", "rejected", "warning"]
SeedCode = Literal[
    "accepted", "normalized", "duplicate", "invalid", "self",
    "same_brand", "blocklist", "over_limit",
]


class SeedOutcome(BaseModel):
    """What happened to one supplied domain. Reports a *decision*, never a measurement —
    the measurement runs afterwards in the background, so the copy must not imply the
    competitor was successfully measured."""
    input: str
    domain: str | None = None
    status: SeedStatus
    code: SeedCode
    message_nl: str


def resolve_seeds(
    raw: list[str],
    store_domain: str,
    existing: list[str],
    limit: int,
) -> tuple[list[str], list[SeedOutcome]]:
    """Returns (accepted domains in input order, one outcome per input).

    `existing` is the set already on the run; accepted domains are those that fit
    within `limit` *including* `existing`.
    """
    accepted: list[str] = []
    outcomes: list[SeedOutcome] = []
    seen = {normalize_competitor_input(d) or d.strip().lower() for d in existing}
    remaining = max(0, limit - len(existing))

    for item in raw:
        original = (item or "").strip()

        domain = normalize_competitor_input(original)
        if domain is None:
            outcomes.append(SeedOutcome(
                input=original, status="rejected", code="invalid",
                message_nl=f"'{original}' is geen geldig domein — niet toegevoegd.",
            ))
            continue

        # Hard reject: the store cannot be its own competitor. Anything else would put
        # the audited store into the median it is being compared against.
        if same_registrable(domain, store_domain):
            outcomes.append(SeedOutcome(
                input=original, domain=domain, status="rejected", code="self",
                message_nl=f"{domain} is de gescande store zelf — niet toegevoegd.",
            ))
            continue

        if domain in seen:
            outcomes.append(SeedOutcome(
                input=original, domain=domain, status="rejected", code="duplicate",
                message_nl=f"{domain} staat al in de lijst.",
            ))
            continue

        if len(accepted) >= remaining:
            outcomes.append(SeedOutcome(
                input=original, domain=domain, status="rejected", code="over_limit",
                message_nl=(
                    f"{domain} is niet toegevoegd — de limiet van {limit} concurrenten is bereikt. "
                    "Verwijder er eerst een."
                ),
            ))
            continue

        accepted.append(domain)
        seen.add(domain)

        # Admitted — but say why it might be a bad idea. Same-brand is a warning rather
        # than a reject because `is_same_brand` is substring containment on the brand
        # label and does produce false positives; blocking a legitimate competitor on a
        # fuzzy match is worse than flagging it.
        if is_same_brand(domain, store_domain):
            outcomes.append(SeedOutcome(
                input=original, domain=domain, status="warning", code="same_brand",
                message_nl=(
                    f"{domain} toegevoegd — meting gestart. Let op: lijkt hetzelfde merk "
                    "als de gescande store."
                ),
            ))
            continue

        block = blocklist_match(domain)
        if block is not None:
            outcomes.append(SeedOutcome(
                input=original, domain=domain, status="warning", code="blocklist",
                message_nl=(
                    f"{domain} toegevoegd — meting gestart. Let op: bekend als "
                    f"{block['category']}, dit vertekent de marktmediaan."
                ),
            ))
            continue

        if domain != original.lower():
            outcomes.append(SeedOutcome(
                input=original, domain=domain, status="accepted", code="normalized",
                message_nl=f"Opgeslagen als {domain} — meting gestart.",
            ))
            continue

        outcomes.append(SeedOutcome(
            input=original, domain=domain, status="accepted", code="accepted",
            message_nl=f"{domain} toegevoegd — meting gestart.",
        ))

    return accepted, outcomes

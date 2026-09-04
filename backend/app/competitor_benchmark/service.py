"""Orchestrates a competitor benchmark run: discovery -> per-domain measurement
(cache-aware) -> scoring -> euro gap pricing -> persistence. Mirrors the
queued/processing/ready status-machine pattern in full_audit/service.py, including
"never raise out of the background task" — every failure path writes a status and an
error_message rather than leaving the row stuck.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.scraper import scrape_store
from app.competitor_benchmark import snapshot_cache
from app.competitor_benchmark.comparison import build_comparisons, score_layers, store_snapshot_from_audit
from app.competitor_benchmark.discovery import discover_candidates
from app.competitor_benchmark.gap_pricing import price_gap_to_market
from app.competitor_benchmark.market import resolve_market
from app.competitor_benchmark.measure import measure_all
from app.competitor_benchmark.models import CompetitorBenchmarkRun
from app.competitor_benchmark.schemas import (
    CandidateDomain,
    CompetitorBenchmarkData,
    CompetitorRosterEntry,
    CompetitorSnapshot,
    DiscoveryResult,
    MarketInfo,
    RejectedCandidate,
    SeedOutcome,
)
from app.competitor_benchmark.seeds import resolve_seeds
from app.config import settings
from app.database import AsyncSessionLocal
from app.domains import extract_domain
from app.full_audit.models import FullAudit
from app.full_audit.schemas import FullAuditData

logger = logging.getLogger(__name__)

_MIN_MEASURED_FOR_READY = 3


async def _set_status(db: AsyncSession, run_id: uuid.UUID, status: str) -> None:
    result = await db.execute(select(CompetitorBenchmarkRun).where(CompetitorBenchmarkRun.id == run_id))
    row = result.scalar_one_or_none()
    if row:
        row.status = status
        await db.commit()


async def _fail(run_id: uuid.UUID, message: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(CompetitorBenchmarkRun).where(CompetitorBenchmarkRun.id == run_id))
            row = result.scalar_one_or_none()
            if row:
                row.status = "failed"
                row.error_message = message[:2000]
                await db.commit()
    except Exception:
        logger.exception("Failed to persist failure state for competitor benchmark run %s", run_id)


async def _resolve_snapshots(
    db: AsyncSession,
    domains: list[str],
    *,
    probe_checkout: bool,
    force: bool = False,
    force_domains: set[str] | None = None,
) -> list[CompetitorSnapshot]:
    """Cache-aware measurement: reuse a fresh snapshot when one exists, measure the
    rest. This is what makes an operator override cheap (only newly-added domains
    lack a cache hit) and what lets two prospects in the same niche share
    measurements of the same competitor.

    `force_domains` bypasses the cache for specific domains. Newly added competitors go
    in there, because failures are negative-cached for 2 days: without this, an operator
    who fixes a typo and re-adds the domain gets the cached failure back and no
    measurement at all, unless they happen to know the separate /remeasure endpoint
    exists.
    """
    forced = force_domains or set()
    cached: dict[str, CompetitorSnapshot] = {}
    to_measure: list[str] = []
    for domain in domains:
        snapshot = None if (force or domain in forced) else await snapshot_cache.get_fresh(db, domain)
        if snapshot is not None:
            # The cache is keyed on the registrable domain, so a lookup for `www.x.nl`
            # can return a snapshot whose own `.domain` is `x.nl`. Re-key it onto the
            # domain we asked for, or `_build_roster` looks it up under the requested
            # name, misses, and tells the prospect a measured competitor was
            # unreachable.
            if snapshot.domain != domain:
                snapshot = snapshot.model_copy(update={"domain": domain})
            cached[domain] = snapshot
        else:
            to_measure.append(domain)

    measured: list[CompetitorSnapshot] = []
    if to_measure:
        measured = await measure_all(to_measure, probe_checkout=probe_checkout)
        for snapshot in measured:
            await snapshot_cache.upsert(db, snapshot)

    by_domain = {**cached, **{s.domain: s for s in measured}}
    return [by_domain[d] for d in domains if d in by_domain]


def _dedup_normalized(domains: list[str]) -> list[str]:
    """Normalize and de-duplicate while preserving order. Guards the whole scoring path
    against legacy rows written before ingress normalization existed, where `www.x.nl`
    and `x.nl` could both sit in `selected_domains` and count twice in the median."""
    seen: set[str] = set()
    out: list[str] = []
    for domain in domains:
        normalized = extract_domain(domain)
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def _curation_note(seeded: list[str], added: list[str], removed: list[str]) -> str | None:
    """The disclosure sentence for a hand-touched competitor set.

    Added and removed genuinely warrant different wording: injecting a competitor and
    dropping one both move the median, but a prospect reading "wij hebben er twee
    weggehaald" is owed a different explanation than "wij hebben er twee toegevoegd".
    """
    manual = sorted(set(seeded) | set(added))
    n_manual, n_removed = len(manual), len(set(removed))

    if n_manual and n_removed:
        return (
            "Deze set is handmatig samengesteld door Tradual — dit is geen automatisch "
            "bepaald marktgemiddelde."
        )
    if n_removed:
        subject = "1 concurrent is" if n_removed == 1 else f"{n_removed} concurrenten zijn"
        return f"Uit de automatisch gevonden set {subject} handmatig verwijderd door Tradual."
    if n_manual:
        subject = "1 concurrent is" if n_manual == 1 else f"{n_manual} concurrenten zijn"
        return f"{subject} handmatig toegevoegd aan de automatisch gevonden set."
    return None


def _build_roster(
    selected_domains: list[str],
    candidate_meta: dict[str, CandidateDomain],
    snapshots: dict[str, CompetitorSnapshot],
) -> list[CompetitorRosterEntry]:
    from app.competitor_benchmark.metrics import is_shopify

    roster = []
    for domain in selected_domains:
        meta = candidate_meta.get(domain)
        snap = snapshots.get(domain)
        roster.append(CompetitorRosterEntry(
            domain=domain,
            classification=meta.classification if meta else None,
            reason_nl=meta.reason_nl if meta else None,
            measure_status=snap.measure_status if snap else "unreachable",
            measured_at=snap.measured_at if snap else None,
            is_shopify=is_shopify(snap) if snap else None,
            discovery_source=meta.discovery_source if meta else None,
        ))
    return roster


async def _score_and_persist(
    db: AsyncSession,
    run: CompetitorBenchmarkRun,
    audit_data: FullAuditData,
    store_domain: str,
    selected_domains: list[str],
    candidate_meta: dict[str, CandidateDomain],
    market: MarketInfo,
    include_checkout_probe: bool,
    force_domains: set[str] | None = None,
) -> None:
    selected_domains = _dedup_normalized(selected_domains)
    await _set_status(db, run.id, "measuring")
    snapshots = await _resolve_snapshots(
        db, selected_domains, probe_checkout=include_checkout_probe, force_domains=force_domains,
    )
    snapshots_by_domain = {s.domain: s for s in snapshots}

    await _set_status(db, run.id, "scoring")
    store_snapshot = store_snapshot_from_audit(audit_data, store_domain)
    comparisons = build_comparisons(store_snapshot, snapshots)
    layer_scores, overall_relative_score = score_layers(comparisons, store_snapshot)

    funnel = audit_data.revenue_leak.funnel if audit_data.revenue_leak else None
    if funnel is not None:
        gaps, gap_med_lo, gap_med_hi, gap_best_lo, gap_best_hi = price_gap_to_market(comparisons, funnel)
    else:
        gaps, gap_med_lo, gap_med_hi, gap_best_lo, gap_best_hi = [], None, None, None, None

    lcp_comparison = next((c for c in comparisons if c.key == "speed.lcp_mobile_ms"), None)
    market_is_also_below_benchmark = bool(
        lcp_comparison and lcp_comparison.median is not None and lcp_comparison.median > 2500
    )

    roster = _build_roster(selected_domains, candidate_meta, snapshots_by_domain)
    measured_count = sum(1 for s in snapshots if s.measure_status in ("ok", "partial"))

    data = CompetitorBenchmarkData(
        store_domain=store_domain,
        market=market,
        roster=roster,
        comparisons=comparisons,
        layer_scores=layer_scores,
        overall_relative_score=overall_relative_score,
        gaps=gaps,
        gap_to_median_monthly_eur_low=gap_med_lo,
        gap_to_median_monthly_eur_high=gap_med_hi,
        gap_to_best_monthly_eur_low=gap_best_lo,
        gap_to_best_monthly_eur_high=gap_best_hi,
        market_is_also_below_benchmark=market_is_also_below_benchmark,
        manually_curated=bool(run.operator_removed or run.operator_added or run.seed_domains),
        curation_note_nl=_curation_note(
            run.seed_domains or [], run.operator_added or [], run.operator_removed or [],
        ),
        checkout_probe_included=include_checkout_probe,
        methodology_note_nl=(
            "Marktvergelijking o.b.v. live meting van automatisch (of handmatig aangepast) "
            "geselecteerde concurrenten. Mediaan/beste-waarden alleen getoond bij minimaal "
            "3 succesvol gemeten concurrenten per metric."
        ),
        generated_at=datetime.now(UTC),
    )

    run.benchmark_data = data.model_dump(mode="json")
    run.selected_domains = selected_domains
    run.status = "ready" if measured_count >= _MIN_MEASURED_FOR_READY else "insufficient_data"
    run.completed_at = datetime.now(UTC)
    await db.commit()


def _candidate_meta_from_discovery(discovery: DiscoveryResult) -> dict[str, CandidateDomain]:
    # Keyed on the normalized domain so roster lookups can't miss on a `www.` mismatch.
    return {extract_domain(c.domain): c for c in discovery.kept}


async def run_competitor_benchmark(run_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(CompetitorBenchmarkRun).where(CompetitorBenchmarkRun.id == run_id))
            run = result.scalar_one()

            audit_result = await db.execute(select(FullAudit).where(FullAudit.id == run.full_audit_id))
            audit_row = audit_result.scalar_one_or_none()
            if audit_row is None or audit_row.status != "ready_for_review" or not audit_row.audit_data:
                raise RuntimeError("Bron-audit is niet beschikbaar of nog niet voltooid")

            audit_data = FullAuditData.model_validate(audit_row.audit_data)
            store_url = audit_row.store_url
            store_domain = extract_domain(store_url)

            # Persist before discovery: a discovery failure used to leave store_domain
            # empty, which then showed up as a blank store name on the report.
            run.store_domain = store_domain
            await db.commit()

            await _set_status(db, run.id, "discovering")

            # A light re-scrape purely to feed discovery's market resolution (hreflang/
            # html-lang/Shopify globals) and product/collection titles for the AI
            # ranking pass — the full audit's own analyzer outputs are reused for
            # everything else via `store_snapshot_from_audit`.
            try:
                scrape_result = await scrape_store(store_url, max_pages=settings.COMPETITOR_SCRAPER_MAX_PAGES)
            except Exception as exc:
                logger.warning("Store re-scrape for discovery failed for %s: %s", store_url, exc)
                scrape_result = {"pages": []}
            pages = scrape_result.get("pages") or []

            market_override = (run.location_code, run.language_code) if run.market_source == "operator" else None
            discovery = await discover_candidates(
                store_url, pages,
                company_name=audit_data.company_name, industry=audit_data.industry,
                market_override=market_override,
                use_ai_ranking=True,
                max_ranked=10,
            )
            # Everything the operator told us about, in priority order: seeds first,
            # then anything they added by hand on a previous pass. Re-applying
            # `operator_added` here is what makes a re-discovery (e.g. after a market
            # change) idempotent w.r.t. operator intent instead of silently wiping it.
            manual_domains = _dedup_normalized((run.seed_domains or []) + (run.operator_added or []))
            excluded = {extract_domain(d) for d in (run.operator_removed or [])}
            manual_domains = [d for d in manual_domains if d not in excluded]

            if discovery is None:
                if not manual_domains:
                    raise RuntimeError(
                        "DataForSEO is niet geconfigureerd en er zijn geen handmatige "
                        "concurrenten opgegeven — concurrent-discovery niet mogelijk"
                    )
                # Manual-only run. `resolve_market` is pure and needs no API key, and a
                # synthetic DiscoveryResult keeps `discovery_json` non-null so the
                # operator's /candidates panel stays reachable.
                resolution = resolve_market(store_domain, pages, override=market_override)
                discovery = DiscoveryResult(
                    market=MarketInfo(
                        location_code=resolution.location_code,
                        language_code=resolution.language_code,
                        source=resolution.source,
                        confidence=resolution.confidence,
                    ),
                    market_note_nl=(
                        "Automatische discovery niet beschikbaar — alleen handmatig "
                        "opgegeven concurrenten zijn gemeten."
                    ),
                )

            run.location_code = discovery.market.location_code
            run.language_code = discovery.market.language_code
            run.market_source = discovery.market.source

            candidate_meta = _candidate_meta_from_discovery(discovery)
            for domain in manual_domains:
                if domain not in candidate_meta:
                    entry = CandidateDomain(
                        domain=domain, discovery_source="operator", classification="operator",
                        reason_nl="Handmatig opgegeven door Tradual", enrichment_status="skipped",
                    )
                    candidate_meta[domain] = entry
                    discovery.kept.insert(0, entry)

            run.discovery_json = discovery.model_dump(mode="json")
            await db.commit()

            limit = run.measure_limit or settings.COMPETITOR_MEASURE_LIMIT
            auto = [
                c.domain for c in discovery.kept
                if extract_domain(c.domain) not in set(manual_domains) | excluded
            ]
            selected_domains = (manual_domains + auto)[:limit]

            await _score_and_persist(
                db, run, audit_data, store_domain, selected_domains, candidate_meta,
                discovery.market, run.include_checkout_probe,
            )
            logger.info("Competitor benchmark completed for run %s (%s)", run_id, store_domain)

        except Exception as exc:
            logger.exception("Competitor benchmark failed for run %s: %s", run_id, exc)
            await _fail(run_id, str(exc))


async def remeasure(run_id: uuid.UUID, force: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(CompetitorBenchmarkRun).where(CompetitorBenchmarkRun.id == run_id))
            run = result.scalar_one()

            audit_result = await db.execute(select(FullAudit).where(FullAudit.id == run.full_audit_id))
            audit_row = audit_result.scalar_one()
            audit_data = FullAuditData.model_validate(audit_row.audit_data)

            discovery = DiscoveryResult.model_validate(run.discovery_json) if run.discovery_json else None
            candidate_meta = _candidate_meta_from_discovery(discovery) if discovery else {}
            market = discovery.market if discovery else MarketInfo(
                location_code=run.location_code, language_code=run.language_code,
                source=run.market_source, confidence="high",
            )
            selected_domains = run.selected_domains or []

            if force:
                # Bypass the snapshot cache and re-measure + re-upsert every selected
                # domain; _score_and_persist below will then hit fresh cache entries.
                await _resolve_snapshots(db, selected_domains, probe_checkout=run.include_checkout_probe, force=True)

            await _score_and_persist(
                db, run, audit_data, run.store_domain, selected_domains, candidate_meta,
                market, run.include_checkout_probe,
            )
        except Exception as exc:
            logger.exception("Competitor benchmark remeasure failed for run %s: %s", run_id, exc)
            await _fail(run_id, str(exc))


@dataclass
class CompetitorSetPlan:
    """Outcome of deciding what an operator's add/remove request actually does.

    Deciding is separated from measuring on purpose: it is pure bookkeeping (one SELECT,
    one UPDATE, no network) and therefore runs inside the request, so the response can
    say which domains were accepted, what they were normalized to, and which were
    dropped. When this ran in the background task the endpoint could only ever return an
    opaque 200, and a typo'd domain failed three minutes later where nobody saw it.
    """
    outcomes: list[SeedOutcome]
    selected_domains: list[str]
    accepted: list[str]
    removed: list[str] = field(default_factory=list)
    needs_rediscovery: bool = False

    @property
    def changed(self) -> bool:
        """False when nothing was accepted and nothing was removed — e.g. the operator
        made a typo. The caller must not re-measure in that case: it would cost a full
        pass over every selected domain for no change at all."""
        return bool(self.accepted or self.removed) or self.needs_rediscovery


async def plan_competitor_set_update(
    db: AsyncSession,
    run: CompetitorBenchmarkRun,
    add: list[str],
    remove: list[str],
    market_override: tuple[int, str] | None = None,
) -> CompetitorSetPlan:
    # A market change re-derives the whole competitor universe — a different market is a
    # different set of plausible peers, not a tweak to this one. Operator curation is
    # re-applied by run_competitor_benchmark rather than discarded.
    if market_override is not None and market_override != (run.location_code, run.language_code):
        run.location_code, run.language_code = market_override
        run.market_source = "operator"
        run.status = "queued"
        await db.commit()
        return CompetitorSetPlan(outcomes=[], selected_domains=list(run.selected_domains or []),
                                 accepted=[], needs_rediscovery=True)

    current = _dedup_normalized(run.selected_domains or [])
    removed = [extract_domain(d) for d in remove if extract_domain(d)]
    remove_set = set(removed)
    kept_selection = [d for d in current if d not in remove_set]

    limit = run.measure_limit or settings.COMPETITOR_MEASURE_LIMIT
    accepted, outcomes = resolve_seeds(add, run.store_domain, kept_selection, limit)
    new_selected = kept_selection + accepted

    run.selected_domains = new_selected
    run.operator_added = sorted(set(run.operator_added or []) | set(accepted))
    run.operator_removed = sorted(set(run.operator_removed or []) | remove_set)

    discovery = DiscoveryResult.model_validate(run.discovery_json) if run.discovery_json else None
    if discovery is not None:
        # Prune `kept` on removal instead of leaving it untouched: the operator UI
        # renders the selection, and a removed competitor whose candidate entry survived
        # here used to reappear as a chip on the next refetch. The entry moves to
        # `rejected` so the audit trail still shows it was considered.
        surviving = []
        for candidate in discovery.kept:
            if extract_domain(candidate.domain) in remove_set:
                discovery.rejected.append(RejectedCandidate(
                    domain=candidate.domain, reason_code="operator_removed",
                    reason_nl="Handmatig verwijderd door Tradual",
                ))
            else:
                surviving.append(candidate)
        discovery.kept = surviving

        # Only domains that actually made the selection get a candidate entry — adding
        # one for every requested domain is how a chip could appear for a competitor the
        # cap had silently dropped.
        known = {extract_domain(c.domain) for c in discovery.kept}
        for domain in accepted:
            if domain not in known:
                discovery.kept.append(CandidateDomain(
                    domain=domain, discovery_source="operator", classification="operator",
                    reason_nl="Handmatig toegevoegd door Tradual", enrichment_status="skipped",
                ))
        run.discovery_json = discovery.model_dump(mode="json")

    if accepted or remove_set:
        run.status = "measuring"
    await db.commit()

    return CompetitorSetPlan(
        outcomes=outcomes, selected_domains=new_selected,
        accepted=accepted, removed=sorted(remove_set),
    )


async def measure_competitor_set(run_id: uuid.UUID, force_domains: list[str] | None = None) -> None:
    """Background half of an operator edit: measure and re-score the already-persisted
    selection. `force_domains` bypasses the snapshot cache for newly added domains."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(CompetitorBenchmarkRun).where(CompetitorBenchmarkRun.id == run_id))
            run = result.scalar_one()

            audit_result = await db.execute(select(FullAudit).where(FullAudit.id == run.full_audit_id))
            audit_row = audit_result.scalar_one()
            audit_data = FullAuditData.model_validate(audit_row.audit_data)

            discovery = DiscoveryResult.model_validate(run.discovery_json) if run.discovery_json else None
            candidate_meta = _candidate_meta_from_discovery(discovery) if discovery else {}
            market = discovery.market if discovery else MarketInfo(
                location_code=run.location_code, language_code=run.language_code,
                source=run.market_source, confidence="high",
            )

            await _score_and_persist(
                db, run, audit_data, run.store_domain, run.selected_domains or [], candidate_meta,
                market, run.include_checkout_probe,
                force_domains=set(force_domains or []),
            )
        except Exception as exc:
            logger.exception("Competitor set update failed for run %s: %s", run_id, exc)
            await _fail(run_id, str(exc))

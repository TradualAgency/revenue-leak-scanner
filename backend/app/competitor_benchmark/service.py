"""Orchestrates a competitor benchmark run: discovery -> per-domain measurement
(cache-aware) -> scoring -> euro gap pricing -> persistence. Mirrors the
queued/processing/ready status-machine pattern in full_audit/service.py, including
"never raise out of the background task" — every failure path writes a status and an
error_message rather than leaving the row stuck.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.scraper import scrape_store
from app.competitor_benchmark import snapshot_cache
from app.competitor_benchmark.comparison import build_comparisons, score_layers, store_snapshot_from_audit
from app.competitor_benchmark.discovery import discover_candidates
from app.competitor_benchmark.gap_pricing import price_gap_to_market
from app.competitor_benchmark.measure import measure_all
from app.competitor_benchmark.models import CompetitorBenchmarkRun
from app.competitor_benchmark.schemas import (
    CandidateDomain,
    CompetitorBenchmarkData,
    CompetitorRosterEntry,
    CompetitorSnapshot,
    DiscoveryResult,
    MarketInfo,
)
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
    db: AsyncSession, domains: list[str], *, probe_checkout: bool, force: bool = False,
) -> list[CompetitorSnapshot]:
    """Cache-aware measurement: reuse a fresh snapshot when one exists, measure the
    rest. This is what makes an operator override cheap (only newly-added domains
    lack a cache hit) and what lets two prospects in the same niche share
    measurements of the same competitor."""
    cached: dict[str, CompetitorSnapshot] = {}
    to_measure: list[str] = []
    for domain in domains:
        snapshot = None if force else await snapshot_cache.get_fresh(db, domain)
        if snapshot is not None:
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
) -> None:
    await _set_status(db, run.id, "measuring")
    snapshots = await _resolve_snapshots(db, selected_domains, probe_checkout=include_checkout_probe)
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
        manually_curated=bool(run.operator_removed),
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
    return {c.domain: c for c in discovery.kept}


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
            if discovery is None:
                raise RuntimeError("DataForSEO is niet geconfigureerd — concurrent-discovery niet mogelijk")

            run.store_domain = store_domain
            run.location_code = discovery.market.location_code
            run.language_code = discovery.market.language_code
            run.market_source = discovery.market.source
            run.discovery_json = discovery.model_dump(mode="json")
            await db.commit()

            selected_domains = [c.domain for c in discovery.kept][: settings.COMPETITOR_MEASURE_LIMIT]
            candidate_meta = _candidate_meta_from_discovery(discovery)

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


async def update_competitor_set(
    run_id: uuid.UUID,
    add: list[str],
    remove: list[str],
    market_override: tuple[int, str] | None,
) -> None:
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(CompetitorBenchmarkRun).where(CompetitorBenchmarkRun.id == run_id))
            run = result.scalar_one()

            # A market change re-derives the whole competitor universe — a different
            # market is a different set of plausible peers, not a tweak to this one.
            if market_override is not None and (market_override[0], market_override[1]) != (run.location_code, run.language_code):
                run.location_code, run.language_code = market_override
                run.market_source = "operator"
                run.status = "queued"
                await db.commit()
                await run_competitor_benchmark(run_id)
                return

            current = list(run.selected_domains or [])
            remove_set = {d.lower() for d in remove}
            new_selected = [d for d in current if d.lower() not in remove_set]
            for d in add:
                if d.lower() not in {x.lower() for x in new_selected}:
                    new_selected.append(d)
            new_selected = new_selected[: settings.COMPETITOR_MEASURE_LIMIT]

            run.operator_added = sorted(set((run.operator_added or [])) | set(add))
            run.operator_removed = sorted(set((run.operator_removed or [])) | set(remove))

            discovery = DiscoveryResult.model_validate(run.discovery_json) if run.discovery_json else None
            candidate_meta = _candidate_meta_from_discovery(discovery) if discovery else {}
            for d in add:
                if d not in candidate_meta:
                    operator_candidate = CandidateDomain(
                        domain=d, discovery_source="operator", classification="operator",
                        reason_nl="Handmatig toegevoegd door operator", enrichment_status="skipped",
                    )
                    candidate_meta[d] = operator_candidate
                    if discovery is not None:
                        discovery.kept.append(operator_candidate)
            if discovery is not None:
                run.discovery_json = discovery.model_dump(mode="json")

            audit_result = await db.execute(select(FullAudit).where(FullAudit.id == run.full_audit_id))
            audit_row = audit_result.scalar_one()
            audit_data = FullAuditData.model_validate(audit_row.audit_data)
            market = discovery.market if discovery else MarketInfo(
                location_code=run.location_code, language_code=run.language_code,
                source=run.market_source, confidence="high",
            )

            await _score_and_persist(
                db, run, audit_data, run.store_domain, new_selected, candidate_meta,
                market, run.include_checkout_probe,
            )
        except Exception as exc:
            logger.exception("Competitor set update failed for run %s: %s", run_id, exc)
            await _fail(run_id, str(exc))

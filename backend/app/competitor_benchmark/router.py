import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.competitor_benchmark.models import CompetitorBenchmarkRun
from app.competitor_benchmark.schemas import (
    CompetitorBenchmarkCreateRequest,
    CompetitorBenchmarkCreateResponse,
    CompetitorBenchmarkData,
    CompetitorBenchmarkResponse,
    CompetitorBenchmarkStatusResponse,
    CompetitorCandidatesResponse,
    CompetitorRemeasureRequest,
    CompetitorRosterEntry,
    CompetitorRunStatus,
    CompetitorSetUpdateRequest,
    CompetitorSetUpdateResponse,
    DiscoveryResult,
    MarketInfo,
)
from app.competitor_benchmark.seeds import resolve_seeds
from app.competitor_benchmark.service import (
    measure_competitor_set,
    plan_competitor_set_update,
    remeasure,
    run_competitor_benchmark,
)
from app.config import settings
from app.dependencies import get_db, require_operator_key
from app.domains import extract_domain
from app.full_audit.models import FullAudit

router = APIRouter(prefix="/api/v1/competitor-benchmark", tags=["competitor-benchmark"])

_PHASE_LABELS_NL: dict[str, str] = {
    "queued": "In wachtrij",
    "discovering": "Concurrenten opsporen",
    "measuring": "Concurrenten meten",
    "scoring": "Resultaten berekenen",
    "ready": "Klaar",
    "insufficient_data": "Onvoldoende data gemeten",
    "failed": "Mislukt",
}


@router.post("", response_model=CompetitorBenchmarkCreateResponse, status_code=201, dependencies=[Depends(require_operator_key)])
async def create_competitor_benchmark(
    body: CompetitorBenchmarkCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> CompetitorBenchmarkCreateResponse:
    audit_result = await db.execute(select(FullAudit).where(FullAudit.id == body.full_audit_id))
    audit = audit_result.scalar_one_or_none()
    if audit is None:
        raise HTTPException(status_code=404, detail="Full audit not found")
    if audit.status != "ready_for_review":
        raise HTTPException(status_code=409, detail="Full audit is not yet ready")

    store_domain = extract_domain(audit.store_url)
    # Never above the ceiling: COMPETITOR_CONCURRENCY=2 x COMPETITOR_DOMAIN_TIMEOUT_S=180
    # means 8 domains is already up to ~12 minutes of work inside the API process.
    limit = max(1, min(body.max_competitors or settings.COMPETITOR_MEASURE_LIMIT,
                       settings.COMPETITOR_MEASURE_LIMIT))
    seed_domains, outcomes = resolve_seeds(body.seed_domains, store_domain, [], limit)

    run = CompetitorBenchmarkRun(
        id=uuid.uuid4(),
        full_audit_id=audit.id,
        store_domain=store_domain,
        location_code=body.location_code or 2840,
        language_code=body.language_code or "en",
        market_source="operator" if body.location_code and body.language_code else "tld",
        status="queued",
        include_checkout_probe=body.include_checkout_probe,
        seed_domains=seed_domains,
        seed_outcomes=[o.model_dump(mode="json") for o in outcomes],
        measure_limit=limit,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background_tasks.add_task(run_competitor_benchmark, run_id=run.id)

    return CompetitorBenchmarkCreateResponse(
        id=run.id, status=run.status, created_at=run.created_at,  # type: ignore[arg-type]
        seed_domains=seed_domains, outcomes=outcomes,
    )


async def _get_run_or_404(run_id: uuid.UUID, db: AsyncSession) -> CompetitorBenchmarkRun:
    result = await db.execute(select(CompetitorBenchmarkRun).where(CompetitorBenchmarkRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Competitor benchmark run not found")
    return run


@router.get("/{run_id}/status", response_model=CompetitorBenchmarkStatusResponse)
async def get_competitor_benchmark_status(
    run_id: uuid.UUID, db: AsyncSession = Depends(get_db),
) -> CompetitorBenchmarkStatusResponse:
    run = await _get_run_or_404(run_id, db)
    measured_count = total_count = 0
    if run.selected_domains:
        total_count = len(run.selected_domains)
        if run.benchmark_data:
            measured_count = sum(
                1 for entry in run.benchmark_data.get("roster", [])
                if entry.get("measure_status") in ("ok", "partial")
            )
    return CompetitorBenchmarkStatusResponse(
        id=run.id,
        status=run.status,  # type: ignore[arg-type]
        store_domain=run.store_domain,
        phase_label_nl=_PHASE_LABELS_NL.get(run.status),
        measured_count=measured_count,
        total_count=total_count,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.get("/{run_id}", response_model=CompetitorBenchmarkResponse)
async def get_competitor_benchmark(
    run_id: uuid.UUID, db: AsyncSession = Depends(get_db),
) -> CompetitorBenchmarkResponse:
    run = await _get_run_or_404(run_id, db)
    data: CompetitorBenchmarkData | None = None
    if run.benchmark_data and run.status in ("ready", "insufficient_data"):
        data = CompetitorBenchmarkData.model_validate(run.benchmark_data)
    return CompetitorBenchmarkResponse(
        id=run.id,
        status=run.status,  # type: ignore[arg-type]
        store_domain=run.store_domain,
        data=data,
        error_message=run.error_message,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.get("/{run_id}/candidates", response_model=CompetitorCandidatesResponse, dependencies=[Depends(require_operator_key)])
async def get_competitor_candidates(
    run_id: uuid.UUID, db: AsyncSession = Depends(get_db),
) -> CompetitorCandidatesResponse:
    run = await _get_run_or_404(run_id, db)
    # Deliberately does NOT 404 when discovery produced nothing. The operator panel is
    # gated on this payload, so 404-ing here hid the manual-add UI in exactly the case
    # where it is the only way to get a benchmark at all.
    discovery = DiscoveryResult.model_validate(run.discovery_json) if run.discovery_json else None
    roster = [
        CompetitorRosterEntry.model_validate(entry)
        for entry in ((run.benchmark_data or {}).get("roster") or [])
    ]
    return CompetitorCandidatesResponse(
        kept=discovery.kept if discovery else [],
        rejected=discovery.rejected if discovery else [],
        market=discovery.market if discovery else None,
        market_note_nl=discovery.market_note_nl if discovery else None,
        selected_domains=run.selected_domains or [],
        seed_domains=run.seed_domains or [],
        seed_outcomes=run.seed_outcomes or [],
        operator_added=run.operator_added or [],
        operator_removed=run.operator_removed or [],
        measure_limit=run.measure_limit or settings.COMPETITOR_MEASURE_LIMIT,
        discovery_available=discovery is not None,
        roster=roster,
    )


@router.patch("/{run_id}/competitors", response_model=CompetitorSetUpdateResponse, dependencies=[Depends(require_operator_key)])
async def update_competitors(
    run_id: uuid.UUID,
    body: CompetitorSetUpdateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> CompetitorSetUpdateResponse:
    run = await _get_run_or_404(run_id, db)
    if run.status not in ("ready", "insufficient_data", "failed"):
        raise HTTPException(status_code=409, detail="Run is nog bezig — wacht tot de meting klaar is")

    market_override = (body.location_code, body.language_code) if body.location_code and body.language_code else None

    # Decide synchronously so the response can report per-domain outcomes; only the
    # measuring runs in the background.
    plan = await plan_competitor_set_update(db, run, body.add, body.remove, market_override)

    if plan.needs_rediscovery:
        background_tasks.add_task(run_competitor_benchmark, run_id=run.id)
    elif plan.changed:
        background_tasks.add_task(measure_competitor_set, run_id=run.id, force_domains=plan.accepted)
    # Otherwise nothing was accepted and nothing was removed: a typo shouldn't cost a
    # full re-measure of the whole set, so the run is left exactly as it was.

    return CompetitorSetUpdateResponse(
        id=run.id, status=run.status, created_at=run.created_at,  # type: ignore[arg-type]
        selected_domains=plan.selected_domains, outcomes=plan.outcomes,
        measure_limit=run.measure_limit or settings.COMPETITOR_MEASURE_LIMIT,
    )


@router.post("/{run_id}/remeasure", response_model=CompetitorBenchmarkCreateResponse, dependencies=[Depends(require_operator_key)])
async def remeasure_competitors(
    run_id: uuid.UUID,
    body: CompetitorRemeasureRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> CompetitorBenchmarkCreateResponse:
    run = await _get_run_or_404(run_id, db)
    if run.status not in ("ready", "insufficient_data", "failed"):
        raise HTTPException(status_code=409, detail="Run is still processing")

    run.status = "measuring"
    await db.commit()

    background_tasks.add_task(remeasure, run_id=run.id, force=body.force)

    return CompetitorBenchmarkCreateResponse(id=run.id, status="measuring", created_at=run.created_at)

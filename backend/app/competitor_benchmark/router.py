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
    CompetitorRunStatus,
    CompetitorSetUpdateRequest,
    DiscoveryResult,
    MarketInfo,
)
from app.competitor_benchmark.service import remeasure, run_competitor_benchmark, update_competitor_set
from app.dependencies import get_db, require_operator_key
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

    run = CompetitorBenchmarkRun(
        id=uuid.uuid4(),
        full_audit_id=audit.id,
        store_domain="",
        location_code=body.location_code or 2840,
        language_code=body.language_code or "en",
        market_source="operator" if body.location_code and body.language_code else "tld",
        status="queued",
        include_checkout_probe=body.include_checkout_probe,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background_tasks.add_task(run_competitor_benchmark, run_id=run.id)

    return CompetitorBenchmarkCreateResponse(id=run.id, status=run.status, created_at=run.created_at)  # type: ignore[arg-type]


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
    if not run.discovery_json:
        raise HTTPException(status_code=404, detail="Discovery not yet available")
    discovery = DiscoveryResult.model_validate(run.discovery_json)
    return CompetitorCandidatesResponse(
        kept=discovery.kept, rejected=discovery.rejected,
        market=discovery.market, market_note_nl=discovery.market_note_nl,
    )


@router.patch("/{run_id}/competitors", response_model=CompetitorBenchmarkCreateResponse, dependencies=[Depends(require_operator_key)])
async def update_competitors(
    run_id: uuid.UUID,
    body: CompetitorSetUpdateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> CompetitorBenchmarkCreateResponse:
    run = await _get_run_or_404(run_id, db)
    if run.status not in ("ready", "insufficient_data", "failed"):
        raise HTTPException(status_code=409, detail="Run is still processing")

    market_override = (body.location_code, body.language_code) if body.location_code and body.language_code else None
    run.status = "measuring"
    await db.commit()

    background_tasks.add_task(update_competitor_set, run_id=run.id, add=body.add, remove=body.remove, market_override=market_override)

    return CompetitorBenchmarkCreateResponse(id=run.id, status="measuring", created_at=run.created_at)


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

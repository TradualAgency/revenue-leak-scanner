import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_operator_key
from app.full_audit.client_report import build_client_report
from app.full_audit.models import FullAudit
from app.full_audit.overview import FullAuditListResponse, list_full_audits
from app.full_audit.schemas import (
    ClientAuditReport,
    FullAuditCreateResponse,
    FullAuditData,
    FullAuditRequest,
    FullAuditResponse,
    FullAuditStatusResponse,
)
from app.full_audit.service import run_full_audit

router = APIRouter(prefix="/api/v1/full-audit", tags=["full-audit"])


@router.post(
    "", response_model=FullAuditCreateResponse, status_code=201,
    dependencies=[Depends(require_operator_key)],
)
async def create_full_audit(
    body: FullAuditRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> FullAuditCreateResponse:
    audit = FullAudit(
        id=uuid.uuid4(),
        store_url=str(body.store_url),
        company_name=body.company_name,
        industry=body.industry,
        contact_email=body.contact_email,
        contact_person=body.contact_person,
        scan_level=body.scan_level,
        estimated_annual_revenue_eur=body.estimated_annual_revenue_eur,
        aov_eur=body.aov_eur,
        monthly_sessions=body.monthly_sessions,
        conversion_rate_pct=body.conversion_rate_pct,
        monthly_ad_spend_eur=body.monthly_ad_spend_eur,
        mobile_share_pct=body.mobile_share_pct,
        mobile_conversion_rate_pct=body.mobile_conversion_rate_pct,
        status="queued",
    )
    db.add(audit)
    await db.commit()
    await db.refresh(audit)

    background_tasks.add_task(run_full_audit, audit_id=audit.id)

    return FullAuditCreateResponse(
        id=audit.id,
        status=audit.status,  # type: ignore[arg-type]
        created_at=audit.created_at,
    )


@router.get("", response_model=FullAuditListResponse, dependencies=[Depends(require_operator_key)])
async def get_full_audit_list(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=200),
    db: AsyncSession = Depends(get_db),
) -> FullAuditListResponse:
    """Every stored audit, newest first. Operator-only — a list of every prospect we
    have ever scanned is not shareable data."""
    return await list_full_audits(db, limit=limit, offset=offset, q=q)


@router.get("/{audit_id}/status", response_model=FullAuditStatusResponse)
async def get_full_audit_status(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FullAuditStatusResponse:
    result = await db.execute(select(FullAudit).where(FullAudit.id == audit_id))
    audit = result.scalar_one_or_none()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    return FullAuditStatusResponse(
        id=audit.id,
        status=audit.status,  # type: ignore[arg-type]
        scan_level=audit.scan_level,  # type: ignore[arg-type]
        store_url=audit.store_url,
        created_at=audit.created_at,
        completed_at=audit.completed_at,
    )


@router.get("/{audit_id}/report", response_model=ClientAuditReport)
async def get_client_audit_report(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ClientAuditReport:
    """The prospect-facing projection (see client_report.py). Public by design: this is
    what the shareable `/revenue-leak/{id}` link reads."""
    result = await db.execute(select(FullAudit).where(FullAudit.id == audit_id))
    audit = result.scalar_one_or_none()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    data: FullAuditData | None = None
    if audit.audit_data and audit.status == "ready_for_review":
        data = FullAuditData.model_validate(audit.audit_data)
    return build_client_report(audit, data)


@router.get("/{audit_id}", response_model=FullAuditResponse, dependencies=[Depends(require_operator_key)])
async def get_full_audit(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FullAuditResponse:
    """The full operator working file. Clients read `/{audit_id}/report` instead."""
    result = await db.execute(select(FullAudit).where(FullAudit.id == audit_id))
    audit = result.scalar_one_or_none()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    data: FullAuditData | None = None
    if audit.audit_data and audit.status == "ready_for_review":
        data = FullAuditData.model_validate(audit.audit_data)
        # The Sanity export (with its page password) has its own endpoint below; keep
        # this payload the same shape it has always been for the dashboard.
        data.sanity_export = None

    return FullAuditResponse(
        id=audit.id,
        status=audit.status,  # type: ignore[arg-type]
        scan_level=audit.scan_level,  # type: ignore[arg-type]
        store_url=audit.store_url,
        company_name=audit.company_name,
        created_at=audit.created_at,
        completed_at=audit.completed_at,
        data=data,
        error_message=audit.error_message,
    )


@router.get("/{audit_id}/sanity-export", dependencies=[Depends(require_operator_key)])
async def get_full_audit_sanity_export(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(FullAudit).where(FullAudit.id == audit_id))
    audit = result.scalar_one_or_none()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    sanity_export = (audit.audit_data or {}).get("sanity_export") if audit.status == "ready_for_review" else None
    if sanity_export is None:
        raise HTTPException(status_code=404, detail="Sanity export not available")
    return sanity_export

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.full_audit.models import FullAudit
from app.full_audit.schemas import (
    FullAuditCreateResponse,
    FullAuditData,
    FullAuditRequest,
    FullAuditResponse,
    FullAuditStatusResponse,
)
from app.full_audit.service import run_full_audit

router = APIRouter(prefix="/api/v1/full-audit", tags=["full-audit"])


@router.post("", response_model=FullAuditCreateResponse, status_code=201)
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


@router.get("/{audit_id}", response_model=FullAuditResponse)
async def get_full_audit(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FullAuditResponse:
    result = await db.execute(select(FullAudit).where(FullAudit.id == audit_id))
    audit = result.scalar_one_or_none()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    data: FullAuditData | None = None
    if audit.audit_data and audit.status == "ready_for_review":
        data = FullAuditData.model_validate(audit.audit_data)

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

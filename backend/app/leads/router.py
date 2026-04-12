from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.leads.schemas import LeadCreate, LeadCreateResponse
from app.leads.service import create_report_for_lead, get_or_create_lead
from app.reports.service import run_analysis

router = APIRouter(prefix="/api/v1/leads", tags=["leads"])


@router.post("", response_model=LeadCreateResponse, status_code=201)
async def create_lead(
    body: LeadCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> LeadCreateResponse:
    lead, _ = await get_or_create_lead(db, body)
    report = await create_report_for_lead(db, lead)
    await db.commit()

    background_tasks.add_task(run_analysis, report_id=report.id, store_url=str(body.store_url), platform=body.platform, monthly_revenue=body.monthly_revenue)

    return LeadCreateResponse(
        lead_id=lead.id,
        report_id=report.id,
        status=report.status,
        created_at=report.created_at,
    )

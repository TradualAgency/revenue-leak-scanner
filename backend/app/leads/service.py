import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.leads.models import Lead
from app.leads.schemas import LeadCreate
from app.reports.models import Report


async def get_or_create_lead(db: AsyncSession, data: LeadCreate) -> tuple[Lead, bool]:
    """Return (lead, created). If lead with same email exists, return it."""
    result = await db.execute(select(Lead).where(Lead.email == data.email))
    existing = result.scalar_one_or_none()
    if existing:
        existing.platform = data.platform
        existing.store_url = str(data.store_url)
        existing.monthly_revenue = data.monthly_revenue
        existing.monthly_traffic = data.monthly_traffic
        await db.flush()
        return existing, False

    lead = Lead(
        id=uuid.uuid4(),
        email=data.email,
        platform=data.platform,
        store_url=str(data.store_url),
        monthly_revenue=data.monthly_revenue,
        monthly_traffic=data.monthly_traffic,
    )
    db.add(lead)
    await db.flush()
    return lead, True


async def create_report_for_lead(db: AsyncSession, lead: Lead) -> Report:
    report = Report(
        id=uuid.uuid4(),
        lead_id=lead.id,
        status="pending",
    )
    db.add(report)
    await db.flush()
    return report

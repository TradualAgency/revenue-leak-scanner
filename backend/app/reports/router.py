import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.leads.models import Lead
from app.reports.models import DetectedPlugin, Report
from app.reports.schemas import (
    DetectedPluginOut,
    ReportFullResponse,
    ReportStatusResponse,
    ReportSummaryResponse,
)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


async def _get_report_or_404(db: AsyncSession, report_id: uuid.UUID) -> Report:
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/{report_id}/status", response_model=ReportStatusResponse)
async def get_report_status(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ReportStatusResponse:
    report = await _get_report_or_404(db, report_id)
    return ReportStatusResponse(
        report_id=report.id,
        status=report.status,
        pages_discovered=report.pages_discovered,
        avg_load_time_ms=report.avg_load_time_ms,
        performance_score=report.performance_score,
        created_at=report.created_at,
        completed_at=report.completed_at,
    )


@router.get("/{report_id}/summary", response_model=ReportSummaryResponse)
async def get_report_summary(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ReportSummaryResponse:
    report = await _get_report_or_404(db, report_id)

    plugin_count_result = await db.execute(
        select(func.count()).where(DetectedPlugin.report_id == report_id)
    )
    plugin_count = plugin_count_result.scalar_one()

    loss = report.estimated_monthly_loss
    loss_min = Decimal(str(round(float(loss) * 0.8, 2))) if loss is not None else None
    loss_max = Decimal(str(round(float(loss) * 1.2, 2))) if loss is not None else None

    rd = report.report_data or {}
    blended_loss_rate: float | None = rd.get("blended_loss_rate")
    excess_load_time: float | None = rd.get("excess_load_time")
    pages_scanned: list[str] | None = rd.get("pages_scraped")

    plugins_list: list[DetectedPluginOut] | None = None
    if report.status == "completed":
        plugins_result = await db.execute(
            select(DetectedPlugin).where(DetectedPlugin.report_id == report_id)
        )
        plugins_list = [
            DetectedPluginOut(
                name=p.name,
                slug=p.slug,
                platform=p.platform,
                estimated_monthly_cost=p.estimated_monthly_cost,
                detection_method=p.detection_method,
                confidence=p.confidence,
            )
            for p in plugins_result.scalars().all()
        ]

    quick_wins: list[str] = []
    if report.status == "completed":
        if excess_load_time is not None and excess_load_time > 1.5:
            pct = round(excess_load_time * 7)
            quick_wins.append(
                f"Laadtijd optimaliseren kan ~{pct}% extra conversie opleveren"
            )
        if plugins_list:
            paid_plugins = [p for p in plugins_list if p.estimated_monthly_cost and p.estimated_monthly_cost > 0]
            if paid_plugins:
                total_cost = sum(float(p.estimated_monthly_cost) for p in paid_plugins)  # type: ignore[arg-type]
                quick_wins.append(
                    f"Evalueer of alle {len(paid_plugins)} betaalde plugins nodig zijn — bespaar tot ${round(total_cost)}/mo"
                )
        if plugin_count > 5:
            quick_wins.append(
                f"Te veel plugins ({plugin_count}) vertragen je store — overweeg consolidatie"
            )
        perf = report.performance_score
        if perf is not None and perf < 50:
            quick_wins.append("Je performance score is kritiek laag — dit kost je direct omzet")

    return ReportSummaryResponse(
        report_id=report.id,
        status=report.status,
        performance_score=report.performance_score,
        plugin_count=plugin_count if report.status == "completed" else None,
        estimated_monthly_loss_min=loss_min,
        estimated_monthly_loss_max=loss_max,
        total_plugin_cost_monthly=report.total_plugin_cost_monthly,
        avg_load_time_ms=report.avg_load_time_ms,
        excess_load_time=excess_load_time,
        blended_loss_rate=blended_loss_rate,
        pages_scanned=pages_scanned,
        plugins=plugins_list,
        quick_wins=quick_wins if quick_wins else None,
    )


@router.get("/{report_id}", response_model=ReportFullResponse)
async def get_full_report(
    report_id: uuid.UUID,
    email: str = Query(..., description="Email used when creating the lead"),
    db: AsyncSession = Depends(get_db),
) -> ReportFullResponse:
    report = await _get_report_or_404(db, report_id)

    # Validate email matches lead
    lead_result = await db.execute(select(Lead).where(Lead.id == report.lead_id))
    lead = lead_result.scalar_one_or_none()
    if not lead or lead.email.lower() != email.lower():
        raise HTTPException(status_code=403, detail="Email does not match this report")

    if report.status != "completed":
        raise HTTPException(status_code=202, detail=f"Report is {report.status}")

    plugins_result = await db.execute(
        select(DetectedPlugin).where(DetectedPlugin.report_id == report_id)
    )
    plugins = plugins_result.scalars().all()

    return ReportFullResponse(
        report_id=report.id,
        lead_id=report.lead_id,
        status=report.status,
        pages_discovered=report.pages_discovered,
        avg_load_time_ms=report.avg_load_time_ms,
        performance_score=report.performance_score,
        estimated_monthly_loss=report.estimated_monthly_loss,
        total_plugin_cost_monthly=report.total_plugin_cost_monthly,
        plugins=[
            DetectedPluginOut(
                name=p.name,
                slug=p.slug,
                platform=p.platform,
                estimated_monthly_cost=p.estimated_monthly_cost,
                detection_method=p.detection_method,
                confidence=p.confidence,
            )
            for p in plugins
        ],
        report_data=report.report_data,
        created_at=report.created_at,
        completed_at=report.completed_at,
    )

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.leads.models import Lead
from app.reports.models import DetectedPlugin, Report
from app.reports.service import build_free_scan_summary
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

    rd = report.report_data or {}
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

    priced = (
        build_free_scan_summary(rd)
        if report.status == "completed" and rd.get("revenue_leak")
        else {}
    )
    legacy = (
        float(report.estimated_monthly_loss)
        if not priced and report.estimated_monthly_loss is not None
        else None
    )

    return ReportSummaryResponse(
        report_id=report.id,
        status=report.status,
        performance_score=report.performance_score,
        plugin_count=plugin_count if report.status == "completed" else None,
        total_plugin_cost_monthly=report.total_plugin_cost_monthly,
        lcp_ms=priced.get("lcp_ms"),
        pages_scanned=rd.get("pages_scraped"),
        plugins=plugins_list,
        legacy_monthly_loss_estimate=legacy,
        **{k: v for k, v in priced.items() if k != "lcp_ms"},
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

    if report.status not in ("completed", "failed"):
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
        error_message=report.error_message,
        created_at=report.created_at,
        completed_at=report.completed_at,
    )

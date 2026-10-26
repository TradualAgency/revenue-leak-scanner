import uuid
from datetime import datetime
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel

from app.full_audit.schemas import ActionItem, ClientAssumption, DataConflict, FindingOut


class ReportStatusResponse(BaseModel):
    report_id: uuid.UUID
    status: str
    pages_discovered: int | None
    avg_load_time_ms: int | None
    performance_score: int | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class DetectedPluginOut(BaseModel):
    name: str
    slug: str
    platform: str
    estimated_monthly_cost: Decimal | None
    detection_method: str
    confidence: str

    model_config = {"from_attributes": True}


class ReportSummaryResponse(BaseModel):
    report_id: uuid.UUID
    status: str
    currency: Literal["EUR"] = "EUR"
    # Set on scans priced by the full audit's funnel model; None on older scans.
    model_version: str | None = None
    performance_score: int | None = None
    plugin_count: int | None = None
    estimated_monthly_loss_low: float | None = None
    estimated_monthly_loss_high: float | None = None
    # Older scans only: the single figure the retired model produced. Shown as an
    # indication, never dressed up as a range.
    legacy_monthly_loss_estimate: float | None = None
    total_plugin_cost_monthly: Decimal | None = None
    lcp_ms: float | None = None
    pages_scanned: list[str] | None = None
    plugins: list[DetectedPluginOut] | None = None
    findings: list[FindingOut] = []
    actions: list[ActionItem] = []
    assumptions: list[ClientAssumption] = []
    # Structured, not the Dutch `message_nl`: the scan page (English) phrases them itself.
    data_conflicts: list[DataConflict] = []

    model_config = {"from_attributes": True}


class ReportFullResponse(BaseModel):
    report_id: uuid.UUID
    lead_id: uuid.UUID
    status: str
    pages_discovered: int | None
    avg_load_time_ms: int | None
    performance_score: int | None
    estimated_monthly_loss: Decimal | None
    total_plugin_cost_monthly: Decimal | None
    plugins: list[DetectedPluginOut]
    report_data: dict | None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


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
    performance_score: int | None
    plugin_count: int | None
    estimated_monthly_loss_min: Decimal | None
    estimated_monthly_loss_max: Decimal | None
    total_plugin_cost_monthly: Decimal | None
    avg_load_time_ms: int | None
    excess_load_time: float | None
    blended_loss_rate: float | None
    pages_scanned: list[str] | None
    plugins: list[DetectedPluginOut] | None
    quick_wins: list[str] | None

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
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}

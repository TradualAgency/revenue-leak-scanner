import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    pages_discovered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_load_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    performance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_monthly_loss: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_plugin_cost_monthly: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    report_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DetectedPlugin(Base):
    __tablename__ = "detected_plugins"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reports.id"))
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(50))
    estimated_monthly_cost: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    detection_method: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[str] = mapped_column(String(20))


class KnownPlugin(Base):
    __tablename__ = "known_plugins"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(50))
    monthly_cost_low: Mapped[float] = mapped_column(Numeric(8, 2))
    monthly_cost_high: Mapped[float] = mapped_column(Numeric(8, 2))
    detection_patterns: Mapped[dict] = mapped_column(JSONB)

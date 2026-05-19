import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FullAudit(Base):
    __tablename__ = "full_audits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    store_url: Mapped[str] = mapped_column(String(2048))
    company_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scan_level: Mapped[str] = mapped_column(String(20), default="outside-only")
    status: Mapped[str] = mapped_column(String(30), default="queued")
    audit_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    estimated_annual_revenue_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    seranking_traffic_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    seranking_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

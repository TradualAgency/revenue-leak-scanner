import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditScreenshot(Base):
    """A screenshot the funnel agent took as evidence. Bytes in Postgres rather than in
    `audit_data` so the audit JSON stays small; served by uuid, like the public report."""

    __tablename__ = "audit_screenshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    full_audit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("full_audits.id", ondelete="CASCADE"), index=True,
    )
    image: Mapped[bytes] = mapped_column(LargeBinary)
    caption: Mapped[str | None] = mapped_column(String(500), nullable=True)
    page_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

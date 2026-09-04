import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CompetitorBenchmarkRun(Base):
    __tablename__ = "competitor_benchmark_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    full_audit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("full_audits.id", ondelete="CASCADE"), index=True,
    )
    store_domain: Mapped[str] = mapped_column(String(253))
    location_code: Mapped[int] = mapped_column(Integer)
    language_code: Mapped[str] = mapped_column(String(10))
    market_source: Mapped[str] = mapped_column(String(30), default="tld")
    status: Mapped[str] = mapped_column(String(30), default="queued")
    include_checkout_probe: Mapped[bool] = mapped_column(Boolean, default=False)
    # Full audit trail: kept + rejected candidates with reasons, AI ranking output.
    # Operator-only (see router.py's /candidates endpoint) — never shipped on the
    # public GET, which only returns `benchmark_data`.
    discovery_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    selected_domains: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Competitors supplied up-front, before discovery ran. Kept separate from
    # `operator_added` (which is the after-the-fact list) because a re-run has to be
    # able to re-apply both, and because "we were told about these" and "we corrected
    # the machine's answer" are different provenance claims on the report.
    seed_domains: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    seed_outcomes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    operator_added: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    operator_removed: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    measure_limit: Mapped[int] = mapped_column(Integer, default=8, server_default="8")
    benchmark_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompetitorSnapshot(Base):
    """Cached per-domain measurement, keyed on domain alone (not domain+market) — the
    measurement (LCP, stack, checkout, DNS, schema) is a property of the site, not of
    whichever market a discovery run happened to find it through. This is what lets
    two prospects in the same niche share one measurement instead of each audit
    re-paying for it, unlike the old per-audit-row DataForSEO cache this feature also
    replaces the intent of."""
    __tablename__ = "competitor_snapshots"
    __table_args__ = (UniqueConstraint("domain", "schema_version", name="uq_competitor_snapshot_domain_version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(253), index=True)
    location_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    snapshot_json: Mapped[dict] = mapped_column(JSONB)
    measure_status: Mapped[str] = mapped_column(String(20))
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    checkout_probed: Mapped[bool] = mapped_column(Boolean, default=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)

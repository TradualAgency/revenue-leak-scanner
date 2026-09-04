"""Per-domain snapshot cache. 14-day TTL for real measurements (shorter than the
30-day DataForSEO cache, deliberately — "your competitor loads in 1.9s" is said out
loud in a sales meeting, and a competitor's LCP can change with any theme deploy). A
short 2-day negative TTL for unreachable/timeout results means a competitor's site
being down for twenty minutes doesn't blacklist it from measurement for two weeks.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.competitor_benchmark.models import CompetitorSnapshot as CompetitorSnapshotRow
from app.competitor_benchmark.schemas import CompetitorSnapshot
from app.config import settings
from app.domains import extract_domain

SCHEMA_VERSION = 1


def _ttl_for_status(status: str) -> timedelta:
    if status in ("unreachable", "timeout"):
        return timedelta(days=settings.COMPETITOR_SNAPSHOT_NEGATIVE_TTL_DAYS)
    return timedelta(days=settings.COMPETITOR_SNAPSHOT_TTL_DAYS)


async def get_fresh(db: AsyncSession, domain: str) -> CompetitorSnapshot | None:
    domain = extract_domain(domain)
    result = await db.execute(
        select(CompetitorSnapshotRow).where(
            CompetitorSnapshotRow.domain == domain,
            CompetitorSnapshotRow.schema_version == SCHEMA_VERSION,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    age = datetime.now(UTC) - row.measured_at
    if age > _ttl_for_status(row.measure_status):
        return None
    return CompetitorSnapshot.model_validate(row.snapshot_json)


async def upsert(db: AsyncSession, snapshot: CompetitorSnapshot) -> None:
    domain = extract_domain(snapshot.domain)
    platform = snapshot.platform.detected_platform if snapshot.platform else None
    values = {
        "domain": domain,
        "snapshot_json": snapshot.model_dump(mode="json"),
        "measure_status": snapshot.measure_status,
        "platform": platform,
        "checkout_probed": snapshot.checkout_probed,
        "measured_at": snapshot.measured_at,
        "schema_version": SCHEMA_VERSION,
    }
    stmt = pg_insert(CompetitorSnapshotRow).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_competitor_snapshot_domain_version",
        set_={k: v for k, v in values.items() if k not in ("domain", "schema_version")},
    )
    await db.execute(stmt)
    await db.commit()

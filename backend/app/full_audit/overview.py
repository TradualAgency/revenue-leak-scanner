"""The operator's list of every stored full audit, with its competitor-benchmark state.

Leaf module on purpose. These schemas do *not* belong in `full_audit/schemas.py`:
`competitor_benchmark/schemas.py` already imports from there, so pulling
`BenchmarkRunSummary` in the other direction would close an import cycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.competitor_benchmark.models import CompetitorBenchmarkRun
from app.competitor_benchmark.schemas import BenchmarkRunSummary
from app.full_audit.models import FullAudit


class FullAuditListItem(BaseModel):
    """One row of the operator scan list.

    `audit_data`, `seranking_traffic_json` and `competitor_benchmark_json` are absent
    DELIBERATELY. Those are the three JSONB columns on `full_audits`, and the first is
    the entire audit payload — every analyzer's output for every sampled page. Shipping
    46 of them to render a table of store name, date and status is tens of megabytes.

    If you are here to add a field: add the scalar column you need. Do not reach for
    `audit_data` to derive it, and do not change the query below to `select(FullAudit)`
    — that pulls all three blobs back in without anyone noticing until production.
    """
    id: uuid.UUID
    store_url: str
    company_name: str | None = None
    industry: str | None = None
    scan_level: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    latest_benchmark: BenchmarkRunSummary | None = None
    benchmark_run_count: int = 0


class FullAuditListResponse(BaseModel):
    items: list[FullAuditListItem]
    total: int
    limit: int
    offset: int


# Explicit column list — see the note on FullAuditListItem. Never `select(FullAudit)`.
_LIST_COLUMNS = (
    FullAudit.id,
    FullAudit.store_url,
    FullAudit.company_name,
    FullAudit.industry,
    FullAudit.scan_level,
    FullAudit.status,
    FullAudit.created_at,
    FullAudit.completed_at,
)


def _escape_like(term: str) -> str:
    """Neutralise the LIKE metacharacters so a search for `50%` looks for `50%`.

    The backslash must go first, otherwise it re-escapes the escapes added after it.
    Pair with `ilike(..., escape="\\\\")`; without that argument Postgres uses its
    default escape character, which happens to be the same backslash but is not
    guaranteed by the standard.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _apply_search(stmt: Select, q: str | None) -> Select:
    if not q or not q.strip():
        return stmt
    pattern = f"%{_escape_like(q.strip())}%"
    return stmt.where(
        or_(
            FullAudit.store_url.ilike(pattern, escape="\\"),
            FullAudit.company_name.ilike(pattern, escape="\\"),
        )
    )


async def _benchmark_state_for(
    db: AsyncSession, audit_ids: list[uuid.UUID],
) -> dict[uuid.UUID, tuple[BenchmarkRunSummary, int]]:
    """Newest run plus total run count, for the audits on this page only.

    One statement, not a join onto the list query: `DISTINCT ON` collapses to the
    newest run per audit while `count() OVER (PARTITION BY ...)` still sees every row,
    because Postgres evaluates window functions before DISTINCT. Joining instead would
    either multiply the audit rows or need a second round trip for the count.

    The `id DESC` tie-break is not cosmetic. `created_at` is `server_default=func.now()`,
    which is `transaction_timestamp()` in Postgres — constant for the whole transaction.
    Two runs inserted together carry byte-identical timestamps, and without the tie-break
    "the newest one" is whichever the planner happened to emit first.
    """
    if not audit_ids:
        return {}

    # Explicit columns again: `benchmark_data` and `discovery_json` are JSONB and must
    # never ride along on a list response.
    stmt = (
        select(
            CompetitorBenchmarkRun.full_audit_id,
            CompetitorBenchmarkRun.id,
            CompetitorBenchmarkRun.status,
            CompetitorBenchmarkRun.store_domain,
            CompetitorBenchmarkRun.created_at,
            CompetitorBenchmarkRun.completed_at,
            func.count().over(partition_by=CompetitorBenchmarkRun.full_audit_id).label("run_count"),
        )
        .where(CompetitorBenchmarkRun.full_audit_id.in_(audit_ids))
        .distinct(CompetitorBenchmarkRun.full_audit_id)
        .order_by(
            CompetitorBenchmarkRun.full_audit_id,  # DISTINCT ON requires this to lead
            CompetitorBenchmarkRun.created_at.desc(),
            CompetitorBenchmarkRun.id.desc(),
        )
    )

    rows = (await db.execute(stmt)).all()
    return {
        row.full_audit_id: (
            BenchmarkRunSummary(
                id=row.id,
                status=row.status,
                store_domain=row.store_domain,
                created_at=row.created_at,
                completed_at=row.completed_at,
            ),
            row.run_count,
        )
        for row in rows
    }


async def list_full_audits(
    db: AsyncSession, *, limit: int = 50, offset: int = 0, q: str | None = None,
) -> FullAuditListResponse:
    """Page of audits, newest first, each annotated with its benchmark state.

    Offset paging rather than a cursor: there is one operator and no realtime stream,
    and offset is what supports "jump to page 3". The usual offset weakness only bites
    at tens of thousands of rows.
    """
    count_stmt = _apply_search(select(func.count()).select_from(FullAudit), q)
    total = (await db.execute(count_stmt)).scalar_one()

    list_stmt = (
        _apply_search(select(*_LIST_COLUMNS), q)
        .order_by(FullAudit.created_at.desc(), FullAudit.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(list_stmt)).all()

    benchmarks = await _benchmark_state_for(db, [row.id for row in rows])

    items = []
    for row in rows:
        latest, count = benchmarks.get(row.id, (None, 0))
        items.append(
            FullAuditListItem(
                id=row.id,
                store_url=row.store_url,
                company_name=row.company_name,
                industry=row.industry,
                scan_level=row.scan_level,
                status=row.status,
                created_at=row.created_at,
                completed_at=row.completed_at,
                latest_benchmark=latest,
                benchmark_run_count=count,
            )
        )

    return FullAuditListResponse(items=items, total=total, limit=limit, offset=offset)

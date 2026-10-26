"""Operator-only fix agents. Nothing here is reachable through the public `/report`
projection, and the stored Admin token is never returned — only whether one exists."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_operator_key
from app.fix_agents.models import FixAgentRun
from app.fix_agents.schemas import (
    AdminTokenRequest,
    AdminTokenResponse,
    FixAgentRunOut,
    FixAgentRunRequest,
    FixAgentRunsResponse,
)
from app.fix_agents.service import run_fix_agents
from app.fix_agents.shopify_admin import (
    ShopifyAdminClient,
    ShopifyAdminError,
    encrypt_token,
    normalize_shop_domain,
    write_scopes,
)
from app.full_audit.models import FullAudit

router = APIRouter(
    prefix="/api/v1/full-audit", tags=["fix-agents"], dependencies=[Depends(require_operator_key)],
)


async def _get_audit(db: AsyncSession, audit_id: uuid.UUID) -> FullAudit:
    audit = await db.get(FullAudit, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    return audit


@router.put("/{audit_id}/admin-token", response_model=AdminTokenResponse)
async def put_admin_token(
    audit_id: uuid.UUID, body: AdminTokenRequest, db: AsyncSession = Depends(get_db),
) -> AdminTokenResponse:
    audit = await _get_audit(db, audit_id)
    try:
        domain = normalize_shop_domain(body.shop_domain)
        shop_name, scopes = await ShopifyAdminClient(domain, body.access_token).verify()
        if write := write_scopes(scopes):
            raise ShopifyAdminError(
                f"Token heeft schrijfrechten ({', '.join(write)}). Maak een custom app met "
                "alleen read-scopes (read_themes, read_products)."
            )
        token_enc = encrypt_token(body.access_token)
    except ShopifyAdminError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    audit.shopify_shop_domain = domain
    audit.shopify_admin_token_enc = token_enc
    await db.commit()
    return AdminTokenResponse(has_admin_token=True, shopify_shop_domain=domain, shop_name=shop_name, scopes=scopes)


@router.delete("/{audit_id}/admin-token", response_model=AdminTokenResponse)
async def delete_admin_token(audit_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AdminTokenResponse:
    audit = await _get_audit(db, audit_id)
    audit.shopify_shop_domain = None
    audit.shopify_admin_token_enc = None
    await db.commit()
    return AdminTokenResponse(has_admin_token=False)


@router.post("/{audit_id}/fix-agents", response_model=FixAgentRunsResponse, status_code=202)
async def start_fix_agents(
    audit_id: uuid.UUID,
    body: FixAgentRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> FixAgentRunsResponse:
    audit = await _get_audit(db, audit_id)
    if audit.status != "ready_for_review" or not audit.audit_data:
        raise HTTPException(status_code=409, detail="Audit is nog niet klaar")

    runs = [
        FixAgentRun(id=uuid.uuid4(), full_audit_id=audit.id, agent=agent, status="queued")
        for agent in dict.fromkeys(body.agents)
    ]
    db.add_all(runs)
    await db.commit()
    for run in runs:
        await db.refresh(run)

    background_tasks.add_task(run_fix_agents, audit_id=audit.id, run_ids=[r.id for r in runs])
    return _runs_response(audit, runs)


@router.get("/{audit_id}/fix-agents", response_model=FixAgentRunsResponse)
async def list_fix_agent_runs(audit_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> FixAgentRunsResponse:
    audit = await _get_audit(db, audit_id)
    runs = (await db.execute(
        select(FixAgentRun).where(FixAgentRun.full_audit_id == audit_id).order_by(FixAgentRun.created_at.desc())
    )).scalars().all()
    return _runs_response(audit, list(runs))


def _runs_response(audit: FullAudit, runs: list[FixAgentRun]) -> FixAgentRunsResponse:
    return FixAgentRunsResponse(
        audit_id=audit.id,
        has_admin_token=bool(audit.shopify_admin_token_enc),
        shopify_shop_domain=audit.shopify_shop_domain,
        runs=[
            FixAgentRunOut(
                id=r.id, agent=r.agent, status=r.status, result=r.result, error_message=r.error_message,  # type: ignore[arg-type]
                model=r.model, input_tokens=r.input_tokens, output_tokens=r.output_tokens,
                created_at=r.created_at, completed_at=r.completed_at,
            )
            for r in runs
        ],
    )

import asyncio
import logging
import uuid
from datetime import UTC, datetime

import anthropic
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.agents.funnel.service import walk_funnel
from app.agents.verifier.schemas import VerificationReport
from app.agents.verifier.service import run_verifier, verifier_model
from app.fix_agents.agents import AGENTS
from app.fix_agents.models import FixAgentRun
from app.fix_agents.runtime import AgentError, run_agent
from app.fix_agents.shopify_admin import ShopifyAdminClient, ShopifyAdminError, decrypt_token
from app.agents.tools import ToolContext
from app.full_audit.models import FullAudit
from app.full_audit.schemas import FullAuditData

logger = logging.getLogger(__name__)


async def _finish(run_id: uuid.UUID, **fields) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(FixAgentRun, run_id)
        if run is None:
            return
        for key, value in fields.items():
            setattr(run, key, value)
        run.completed_at = datetime.now(UTC)
        await db.commit()


def _model_for(agent: str) -> str:
    if agent == "verifier":
        return verifier_model()
    if agent == "funnel":
        return settings.FUNNEL_AGENT_MODEL
    return settings.FIX_AGENT_MODEL


async def _run_verifier(run_id: uuid.UUID, data: FullAuditData, admin, client) -> None:
    report = await run_verifier(data, admin=admin, client=client, force=True)
    if report is None:
        report = VerificationReport(model=verifier_model(), errors=["Geen geprijsde findings om te controleren."])
    await _finish(
        run_id, status="done", result=report.model_dump(mode="json"),
        input_tokens=report.input_tokens, output_tokens=report.output_tokens,
    )


async def _run_funnel(run_id: uuid.UUID, audit_id: uuid.UUID, data: FullAuditData, client) -> None:
    # The scraped page set isn't stored with the audit; the agent finds a product from
    # the homepage itself.
    walk = await walk_funnel(audit_id, data.store_url, [{"url": data.store_url}], client=client, force=True)
    await _finish(
        run_id, status="failed" if walk.status == "failed" else "done",
        result=walk.model_dump(mode="json"),
        error_message="; ".join(walk.warnings)[:2000] if walk.status == "failed" else None,
        input_tokens=walk.input_tokens, output_tokens=walk.output_tokens,
    )


async def run_fix_agents(audit_id: uuid.UUID, run_ids: list[uuid.UUID]) -> None:
    """Run the queued agents for one audit in parallel — fix agents, and manual verifier
    and funnel runs. One failing agent marks only its own run as failed. Results land
    on the run rows only: a manual run never changes the audit or the client report."""
    async with AsyncSessionLocal() as db:
        audit = await db.get(FullAudit, audit_id)
        runs = (await db.execute(select(FixAgentRun).where(FixAgentRun.id.in_(run_ids)))).scalars().all()
        if audit is None or not audit.audit_data:
            for run in runs:
                run.status, run.error_message = "failed", "Audit heeft geen data."
            await db.commit()
            return
        for run in runs:
            run.status = "processing"
            run.model = _model_for(run.agent)
        await db.commit()
        agents = [(run.id, run.agent) for run in runs]
        data = FullAuditData.model_validate(audit.audit_data)
        shop_domain, token_enc = audit.shopify_shop_domain, audit.shopify_admin_token_enc

    admin: ShopifyAdminClient | None = None
    admin_warning: str | None = None
    if shop_domain and token_enc:
        try:
            admin = ShopifyAdminClient(shop_domain, decrypt_token(token_enc))
        except ShopifyAdminError as exc:
            admin_warning = str(exc)

    findings = data.revenue_leak.findings if data.revenue_leak else []
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def one(run_id: uuid.UUID, agent: str) -> None:
        # Each agent gets its own context: page cache and the used-admin flag are per run.
        ctx = ToolContext(audit=data, admin=admin)
        try:
            if agent == "verifier":
                return await _run_verifier(run_id, data, admin, client)
            if agent == "funnel":
                return await _run_funnel(run_id, audit_id, data, client)
            result = await run_agent(client, AGENTS[agent], ctx, findings)
        except (AgentError, anthropic.APIError) as exc:
            await _finish(run_id, status="failed", error_message=str(exc)[:2000])
            return
        except Exception as exc:
            logger.exception("Fix agent %s failed for audit %s", agent, audit_id)
            await _finish(run_id, status="failed", error_message=f"{type(exc).__name__}: {exc}"[:2000])
            return
        if admin_warning:
            result.package.warnings.append(admin_warning)
        await _finish(
            run_id, status="done", result=result.package.model_dump(mode="json"),
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
        )

    await asyncio.gather(*(one(run_id, agent) for run_id, agent in agents))

"""Finding-verifier: before the euros of a full audit are final, an agent re-checks
every priced finding on the live store and returns confirmed / refuted /
unverifiable. The verdicts are applied deterministically in
revenue_leak.calculate_revenue_leak — the model never touches a euro.

Findings are split over the same four groups as the fix agents (fix_agents/agents.py)
so each run starts with the audit sections that matter for its findings, and the
groups run in parallel. A failing group leaves its findings unjudged (priced as the
analyzers had them) and records an error; it never costs the report its euros.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import anthropic

from app.agents.runtime import AgentError, run_tool_loop, submit_definition
from app.agents.tools import AUDIT_SECTIONS, ToolContext, get_audit_section, tool_definitions
from app.agents.verifier.schemas import FindingVerdict, VerificationReport, VerificationSubmission
from app.config import settings
from app.fix_agents.agents import AGENTS, AgentSpec
from app.fix_agents.shopify_admin import ShopifyAdminClient, ShopifyAdminError, decrypt_token
from app.full_audit.analyzers.ai_analysis import _business_context
from app.full_audit.schemas import FindingOut, FullAuditData

logger = logging.getLogger(__name__)

SUBMIT_TOOL = "submit_verification"
_SYSTEM = (Path(__file__).parent / "skills" / "verifier.md").read_text(encoding="utf-8")
_FALLBACK_GROUP = "speed_bloat"

_SUBMIT_DEFINITION = submit_definition(
    SUBMIT_TOOL,
    "Lever je oordelen in: één verdict per finding. Roep dit precies één keer aan, als "
    "laatste stap. Een validatiefout komt terug als tool-fout; corrigeer en dien opnieuw in.",
    VerificationSubmission,
)


def admin_client_for(shop_domain: str | None, token_enc: str | None) -> ShopifyAdminClient | None:
    """The audit's read-only Admin client, or None (no token, or it can't be decrypted —
    the verifier then works from the public storefront only)."""
    if not (shop_domain and token_enc):
        return None
    try:
        return ShopifyAdminClient(shop_domain, decrypt_token(token_enc))
    except (ShopifyAdminError, ValueError):  # ValueError: malformed TOKEN_ENCRYPTION_KEY
        logger.warning("Verifier: Admin token for %s could not be decrypted", shop_domain)
        return None


def verifier_model() -> str:
    return settings.VERIFIER_MODEL or settings.FIX_AGENT_MODEL


def verification_candidates(data: FullAuditData) -> list[FindingOut]:
    """Only findings that put a euro in the report are worth an agent's time. Funnel-walk
    findings are skipped: they were observed in a real browser with a screenshot, and
    this agent has no browser to re-check them with."""
    findings = data.revenue_leak.findings if data.revenue_leak else []
    return [f for f in findings if f.priced and f.status != "good" and not f.finding_id.startswith("walk.")]


def group_findings(findings: list[FindingOut]) -> dict[str, list[FindingOut]]:
    groups: dict[str, list[FindingOut]] = {}
    for f in findings:
        name = next((n for n, spec in AGENTS.items() if spec.owns(f.finding_id)), _FALLBACK_GROUP)
        groups.setdefault(name, []).append(f)
    return groups


def collect_verdicts(submission: VerificationSubmission, findings: list[FindingOut]) -> list[FindingVerdict]:
    """Allowlist + completeness: ids outside the group are dropped, the first verdict
    per id wins, and a finding the agent skipped is 'unverifiable'."""
    allowed = [f.finding_id for f in findings]
    by_id: dict[str, FindingVerdict] = {}
    for v in submission.verdicts:
        if v.finding_id in allowed and v.finding_id not in by_id:
            by_id[v.finding_id] = v
    return [
        by_id.get(fid) or FindingVerdict(
            finding_id=fid, verdict="unverifiable", evidence_nl="",
            reason_nl="De controle-agent gaf geen oordeel over deze finding.",
        )
        for fid in allowed
    ]


async def _first_message(spec: AgentSpec, ctx: ToolContext, findings: list[FindingOut]) -> str:
    audit = ctx.audit
    return json.dumps({
        "store_url": audit.store_url,
        "company_name": audit.company_name,
        "industry": audit.industry,
        "platform": audit.platform_architecture.model_dump(mode="json") if audit.platform_architecture else None,
        "business_context": _business_context(audit),
        "has_admin_token": ctx.admin is not None,
        # No euros: the agent judges whether a problem exists, not what it is worth.
        "findings": [
            f.model_dump(mode="json", include={"finding_id", "metric", "signal", "stage", "priority", "status", "confidence", "pages_affected", "sources"})
            for f in findings
        ],
        "sections": {s: await get_audit_section(ctx, s) for s in spec.primary_sections},
        "other_sections_available": [s for s in AUDIT_SECTIONS if s not in spec.primary_sections],
    }, ensure_ascii=False, sort_keys=True)


async def run_verifier(
    data: FullAuditData,
    admin: ShopifyAdminClient | None = None,
    client: anthropic.AsyncAnthropic | None = None,
    force: bool = False,
) -> VerificationReport | None:
    """None when disabled (unless `force`: a manual start from the operator UI),
    unconfigured, or there's nothing priced to check."""
    if (not settings.VERIFIER_ENABLED and not force) or (client is None and not settings.ANTHROPIC_API_KEY):
        return None
    groups = group_findings(verification_candidates(data))
    if not groups:
        return None
    client = client or anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    model = verifier_model()

    async def one(name: str, findings: list[FindingOut]):
        spec = AGENTS[name]
        # Own context per group: page cache and the used-admin flag are per run.
        ctx = ToolContext(audit=data, admin=admin)
        try:
            loop = await run_tool_loop(
                client,
                model=model,
                system=_SYSTEM,
                tools=tool_definitions(list(spec.tools)),
                submit_tool=_SUBMIT_DEFINITION,
                submission_model=VerificationSubmission,
                first_message=await _first_message(spec, ctx, findings),
                ctx=ctx,
                max_turns=settings.VERIFIER_MAX_TURNS,
            )
        except (AgentError, anthropic.APIError) as exc:
            error = f"{name}: {exc}"
        except Exception as exc:
            logger.exception("Verifier group %s failed for %s", name, data.store_url)
            error = f"{name}: {type(exc).__name__}: {exc}"
        else:
            return collect_verdicts(loop.submission, findings), loop.input_tokens, loop.output_tokens, ctx.used_admin, None
        # A failed run says nothing about the store: its findings stay as the analyzers
        # priced them, and the error is shown to the operator.
        return [], 0, 0, False, error[:500]

    results = await asyncio.gather(*(one(n, fs) for n, fs in groups.items()))
    report = VerificationReport(model=model)
    for verdicts, in_tok, out_tok, used_admin, error in results:
        report.verdicts.extend(verdicts)
        report.input_tokens += in_tok
        report.output_tokens += out_tok
        report.used_admin_data |= used_admin
        if error:
            report.errors.append(error)
    return report

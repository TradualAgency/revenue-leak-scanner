"""The fix agents on top of the shared loop in app/agents/runtime.py, ending when the
agent calls `submit_fix_package`.

Same rule as the roadmap (ai_analysis.attach_roadmap_impact): the model only picks
which `finding_ids` a fix resolves. Euros come from the registry, effort/owner/
remeasure from analyzers/actions.py — never from the LLM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import anthropic

from app.agents.runtime import AgentError, run_tool_loop, submit_definition
from app.agents.tools import AUDIT_SECTIONS, ToolContext, get_audit_section, tool_definitions
from app.config import settings
from app.fix_agents.agents import AgentSpec
from app.fix_agents.schemas import FixItem, FixPackage, FixPackageSubmission
from app.full_audit.analyzers.actions import ACTIONS, FINDING_ACTIONS
from app.full_audit.analyzers.ai_analysis import _business_context
from app.full_audit.schemas import FindingOut

__all__ = ["AgentError", "AgentResult", "agent_findings", "attach_fix_impact", "run_agent"]

SUBMIT_TOOL = "submit_fix_package"

_SUBMIT_DEFINITION = submit_definition(
    SUBMIT_TOOL,
    "Lever het eindresultaat in: het volledige fix-pakket. Roep dit precies één keer "
    "aan, als laatste stap. Een validatiefout komt terug als tool-fout; corrigeer en "
    "dien opnieuw in.",
    FixPackageSubmission,
)


@dataclass
class AgentResult:
    package: FixPackage
    input_tokens: int
    output_tokens: int


def agent_findings(spec: AgentSpec, findings: list[FindingOut]) -> list[FindingOut]:
    return [f for f in findings if spec.owns(f.finding_id) and f.status != "good"]


def _round_100(value: float) -> float:
    return float(round(value / 100) * 100)


def attach_fix_impact(submission: FixPackageSubmission, findings: list[FindingOut]) -> list[FixItem]:
    """Drop ids outside the allowlist, count each finding in the first fix that claims
    it only, and fill euros/effort from the registry and the action table."""
    by_id = {f.finding_id: f for f in findings}
    claimed: set[str] = set()
    items: list[FixItem] = []
    for sub in submission.fixes:
        ids = [fid for fid in dict.fromkeys(sub.finding_ids) if fid in by_id and fid not in claimed]
        claimed.update(ids)
        item = FixItem(**{**sub.model_dump(), "finding_ids": ids})
        priced = [by_id[fid] for fid in ids if by_id[fid].priced]
        if priced:
            item.priced = True
            item.monthly_low = _round_100(sum(f.monthly_low or 0 for f in priced))
            item.monthly_high = _round_100(sum(f.monthly_high or 0 for f in priced))
        specs = [ACTIONS[FINDING_ACTIONS[fid]] for fid in ids if fid in FINDING_ACTIONS]
        if specs:
            # Several actions in one fix: plan for the biggest one.
            spec = max(specs, key=lambda s: s.effort_days_high)
            item.effort = spec.effort
            item.effort_days_low = spec.effort_days_low
            item.effort_days_high = spec.effort_days_high
            item.owner = spec.owner
            item.remeasure_metric = spec.remeasure_metric
            item.remeasure_after_days = spec.remeasure_after_days
        items.append(item)
    return items


async def _initial_message(spec: AgentSpec, ctx: ToolContext, findings: list[FindingOut]) -> str:
    audit = ctx.audit
    actions = [
        a.model_dump(mode="json")
        for a in (audit.revenue_leak.actions if audit.revenue_leak else [])
        if any(spec.owns(fid) for fid in a.finding_ids)
    ]
    return json.dumps({
        "store_url": audit.store_url,
        "company_name": audit.company_name,
        "industry": audit.industry,
        "platform": audit.platform_architecture.model_dump(mode="json") if audit.platform_architecture else None,
        "business_context": _business_context(audit),
        "has_admin_token": ctx.admin is not None,
        "findings": [f.model_dump(mode="json") for f in findings],
        "existing_actions": actions,
        "sections": {s: await get_audit_section(ctx, s) for s in spec.primary_sections},
        "other_sections_available": [s for s in AUDIT_SECTIONS if s not in spec.primary_sections],
    }, ensure_ascii=False, sort_keys=True)


async def run_agent(
    client: anthropic.AsyncAnthropic, spec: AgentSpec, ctx: ToolContext, findings: list[FindingOut],
) -> AgentResult:
    owned = agent_findings(spec, findings)
    loop = await run_tool_loop(
        client,
        model=settings.FIX_AGENT_MODEL,
        system=spec.system_prompt,
        tools=tool_definitions(list(spec.tools)),
        submit_tool=_SUBMIT_DEFINITION,
        submission_model=FixPackageSubmission,
        first_message=await _initial_message(spec, ctx, owned),
        ctx=ctx,
        max_turns=settings.FIX_AGENT_MAX_TURNS,
    )
    submission = loop.submission
    package = FixPackage(
        agent=spec.name,
        summary_nl=submission.summary_nl,
        fixes=attach_fix_impact(submission, owned),
        assumptions=submission.assumptions,
        used_admin_data=ctx.used_admin,
        warnings=[] if ctx.admin else ["Geen Admin-token: theme-code en productdata zijn niet ingezien."],
    )
    return AgentResult(package, loop.input_tokens, loop.output_tokens)

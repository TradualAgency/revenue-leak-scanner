"""Funnel agent: walks a store as a mobile visitor (home -> search -> collection ->
PDP -> variant -> add to cart -> cart -> checkout, read-only there) and reports what
blocked or slowed it, with screenshots as evidence.

Runs inside the full-audit pipeline next to the analyzers. It never fails the audit:
disabled, blocked or crashed walks come back as a FunnelWalk with that status, and
revenue_leak only registers findings from an 'ok' walk.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

import anthropic

from app.agents.funnel.browser import BrowserSession, close_session, open_session
from app.agents.funnel.browser_tools import (
    EVIDENCE_ATC_NO_CART_REQUEST,
    EVIDENCE_CHECKOUT_ERROR,
    EVIDENCE_INTERCEPTED_CLICK,
    TOOL_SPECS,
    execute_browser_tool,
)
from app.agents.funnel.models import AuditScreenshot
from app.agents.funnel.schemas import FunnelIssue, FunnelWalk, FunnelWalkSubmission
from app.agents.runtime import AgentError, run_tool_loop, submit_definition
from app.config import settings
from app.database import AsyncSessionLocal
from app.full_audit.page_sampling import sample_pages_by_type

logger = logging.getLogger(__name__)

SUBMIT_TOOL = "submit_funnel_walk"
_SYSTEM = (Path(__file__).parent / "skills" / "funnel.md").read_text(encoding="utf-8")

_SUBMIT_DEFINITION = submit_definition(
    SUBMIT_TOOL,
    "Lever het resultaat van de walk in: stappen, issues en samenvatting. Roep dit precies "
    "één keer aan, als laatste stap. Een validatiefout komt terug als tool-fout; corrigeer "
    "en dien opnieuw in.",
    FunnelWalkSubmission,
)


def _first_message(store_url: str, pages: list[dict]) -> str:
    by_type = sample_pages_by_type(pages)
    return json.dumps({
        "store_url": store_url,
        "example_product_url": (by_type.get("pdp") or {}).get("url"),
        "example_collection_url": (by_type.get("collection") or {}).get("url"),
    }, ensure_ascii=False)


# The fact the browser layer must have recorded before an issue key may carry euros.
# The model can misread its own failed click as a store problem; these facts can't.
PRICED_EVIDENCE: dict[str, str] = {
    "atc_blocked_by_overlay": EVIDENCE_INTERCEPTED_CLICK,
    "atc_no_feedback": EVIDENCE_ATC_NO_CART_REQUEST,
    "checkout_unreachable": EVIDENCE_CHECKOUT_ERROR,
}


def build_walk(
    submission: FunnelWalkSubmission, session_screenshots: set[str], evidence: set[str] = frozenset(),  # type: ignore[assignment]
) -> tuple[str, list[FunnelIssue], list[str]]:
    """Status + issues the report may use. A blocked walk carries no issues; an issue
    pointing at a screenshot this session didn't take loses the reference (never a
    link to an image that doesn't exist); and an issue is only machine_confirmed —
    priceable — when the browser recorded the fact its key needs."""
    if submission.blocked:
        return "blocked", [], ["De winkel blokkeerde de browser (bot-bescherming, wachtwoord of landkeuze)."]
    warnings: list[str] = []
    issues: list[FunnelIssue] = []
    for sub in submission.issues:
        needed = PRICED_EVIDENCE.get(sub.issue_key)
        issue = FunnelIssue(**sub.model_dump(), machine_confirmed=needed is not None and needed in evidence)
        if needed and not issue.machine_confirmed:
            warnings.append(f"'{issue.issue_key}' niet door de browser bevestigd ({needed}); getoond zonder bedrag.")
        if issue.screenshot_id and issue.screenshot_id not in session_screenshots:
            warnings.append(f"Issue '{issue.issue_key}' verwees naar een onbekende screenshot; verwijzing verwijderd.")
            issue.screenshot_id = None
        issues.append(issue)
    return "ok", issues, warnings


async def _save_screenshots(audit_id: uuid.UUID, session: BrowserSession, used: set[str]) -> None:
    """Only screenshots an issue refers to (plus none else) are stored."""
    shots = [s for sid, s in session.screenshots.items() if sid in used]
    if not shots:
        return
    async with AsyncSessionLocal() as db:
        db.add_all(
            AuditScreenshot(id=uuid.UUID(s.id), full_audit_id=audit_id, image=s.image, caption=s.caption, page_url=s.page_url[:2000])
            for s in shots
        )
        await db.commit()


async def walk_funnel(
    audit_id: uuid.UUID,
    store_url: str,
    pages: list[dict],
    client: anthropic.AsyncAnthropic | None = None,
    force: bool = False,
) -> FunnelWalk:
    """`force`: a manual start from the operator UI runs even when the automatic run
    inside the audit pipeline is switched off."""
    if (not settings.FUNNEL_AGENT_ENABLED and not force) or (client is None and not settings.ANTHROPIC_API_KEY):
        return FunnelWalk(status="skipped")
    client = client or anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    model = settings.FUNNEL_AGENT_MODEL

    try:
        session = await open_session(store_url)
    except Exception as exc:  # Chromium not installed, sandbox issues, ...
        logger.warning("Funnel agent could not start a browser: %s", exc)
        return FunnelWalk(status="failed", warnings=[f"Browser kon niet starten: {type(exc).__name__}: {str(exc)[:300]}"], model=model)

    try:
        loop = await asyncio.wait_for(
            run_tool_loop(
                client,
                model=model,
                system=_SYSTEM,
                tools=TOOL_SPECS,
                submit_tool=_SUBMIT_DEFINITION,
                submission_model=FunnelWalkSubmission,
                first_message=_first_message(store_url, pages),
                ctx=session,
                max_turns=settings.FUNNEL_AGENT_MAX_TURNS,
                executor=execute_browser_tool,
            ),
            timeout=settings.FUNNEL_AGENT_TIMEOUT_S,
        )
    except (AgentError, anthropic.APIError, TimeoutError) as exc:
        await close_session(session)
        reason = "Tijdslimiet bereikt" if isinstance(exc, TimeoutError) else str(exc)
        return FunnelWalk(status="failed", warnings=[f"Walk mislukt: {reason}"[:500]], model=model)
    except Exception as exc:
        logger.exception("Funnel agent crashed for %s", store_url)
        await close_session(session)
        return FunnelWalk(status="failed", warnings=[f"Walk mislukt: {type(exc).__name__}"], model=model)

    blocked_requests = len(session.blocked)
    await close_session(session)

    status, issues, warnings = build_walk(loop.submission, set(session.screenshots), session.evidence)
    used = {i.screenshot_id for i in issues if i.screenshot_id}
    try:
        await _save_screenshots(audit_id, session, used)
    except Exception as exc:
        logger.warning("Funnel agent could not store screenshots for %s: %s", audit_id, exc)
        warnings.append("Screenshots konden niet worden opgeslagen.")
        for issue in issues:
            issue.screenshot_id = None

    if blocked_requests:
        warnings.append(f"{blocked_requests} tracking- en schrijfverzoeken geblokkeerd (geen data van de klant vervuild).")
    return FunnelWalk(
        status=status,  # type: ignore[arg-type]
        steps=loop.submission.steps,
        issues=issues,
        summary_nl=loop.submission.summary_nl,
        warnings=warnings,
        model=model,
        input_tokens=loop.input_tokens,
        output_tokens=loop.output_tokens,
    )

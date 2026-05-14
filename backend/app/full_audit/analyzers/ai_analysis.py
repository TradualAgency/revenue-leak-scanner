import asyncio
import json
import logging
from pathlib import Path

import anthropic
from pydantic import ValidationError

from app.config import settings
from app.full_audit.schemas import AiAnalysis, AiSkillInsight, FullAuditData

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

_SKILLS_DIR = Path(__file__).parent.parent / "skills"


def _load_skill(name: str) -> str:
    return (_SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8")


_SYSTEM_CRO = _load_skill("cro")
_SYSTEM_DELIVERABILITY = _load_skill("deliverability")
_SYSTEM_TECH = _load_skill("tech_architecture")


def _cro_payload(audit: FullAuditData) -> str:
    return json.dumps({
        "checkout_flow": audit.checkout_flow.model_dump(mode="json") if audit.checkout_flow else None,
        "cro_observations": [o.model_dump(mode="json") for o in audit.cro_observations],
        "performance": {
            "mobile": audit.performance.mobile.model_dump(mode="json") if (audit.performance and audit.performance.mobile) else None,
            "lighthouse": audit.performance.lighthouse.model_dump(mode="json") if (audit.performance and audit.performance.lighthouse) else None,
        } if audit.performance else None,
        "rich_results": audit.rich_results.model_dump(mode="json") if audit.rich_results else None,
        "owned_channels": audit.owned_channels.model_dump(mode="json") if audit.owned_channels else None,
    }, ensure_ascii=False)


def _deliverability_payload(audit: FullAuditData) -> str:
    return json.dumps({
        "dns_email": audit.dns_email.model_dump(mode="json") if audit.dns_email else None,
        "domain_health": audit.domain_health.model_dump(mode="json") if audit.domain_health else None,
        "owned_channels": audit.owned_channels.model_dump(mode="json") if audit.owned_channels else None,
        "security_compliance": audit.security_compliance.model_dump(mode="json") if audit.security_compliance else None,
    }, ensure_ascii=False)


def _tech_payload(audit: FullAuditData) -> str:
    return json.dumps({
        "platform_architecture": audit.platform_architecture.model_dump(mode="json") if audit.platform_architecture else None,
        "performance": audit.performance.model_dump(mode="json") if audit.performance else None,
        "third_party_scripts": audit.third_party_scripts.model_dump(mode="json") if audit.third_party_scripts else None,
        "cost_analysis": audit.cost_analysis.model_dump(mode="json") if audit.cost_analysis else None,
        "server_side_tracking": audit.server_side_tracking.model_dump(mode="json") if audit.server_side_tracking else None,
    }, ensure_ascii=False)


def _extract_json(raw: str) -> str:
    """Strip markdown code fences if Claude wraps the JSON despite instructions."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return inner.strip()
    return stripped


async def _call_skill(client: anthropic.AsyncAnthropic, system: str, payload: str) -> AiSkillInsight:
    message = await client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": payload}],
    )
    raw = message.content[0].text
    try:
        data = json.loads(_extract_json(raw))
        return AiSkillInsight.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("AI skill raw response: %.500s", raw)
        raise ValueError(f"Invalid AI skill response: {exc}") from exc


async def run_ai_analysis(audit: FullAuditData) -> AiAnalysis | None:
    if not settings.ANTHROPIC_API_KEY:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    results = await asyncio.gather(
        _call_skill(client, _SYSTEM_CRO, _cro_payload(audit)),
        _call_skill(client, _SYSTEM_DELIVERABILITY, _deliverability_payload(audit)),
        _call_skill(client, _SYSTEM_TECH, _tech_payload(audit)),
        return_exceptions=True,
    )

    def _safe(val: object) -> AiSkillInsight | None:
        if isinstance(val, BaseException):
            logger.warning("AI skill failed: %s", val)
            return None
        return val  # type: ignore[return-value]

    return AiAnalysis(
        cro=_safe(results[0]),
        deliverability=_safe(results[1]),
        tech_architecture=_safe(results[2]),
    )

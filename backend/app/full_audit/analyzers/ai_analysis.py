import asyncio
import json
import logging
from pathlib import Path

import anthropic
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import settings
from app.full_audit.analyzers.cro import _detect_social_proof, _sample_pages_by_type
from app.full_audit.schemas import (
    AiAnalysis,
    AiBloatInsight,
    AiSkillInsight,
    FullAuditData,
    ShopifyMigrationInsight,
    StrategicRoadmap,
)

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

_SKILLS_DIR = Path(__file__).parent.parent / "skills"


def _load_skill(name: str) -> str:
    return (_SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8")


_SYSTEM_CRO = _load_skill("cro")
_SYSTEM_DELIVERABILITY = _load_skill("deliverability")
_SYSTEM_TECH = _load_skill("tech_architecture")
_SYSTEM_SHOPIFY = _load_skill("shopify_migration")
_SYSTEM_AD_BOUNCE = _load_skill("ad_bounce_revenue")
_SYSTEM_BLOAT = _load_skill("bloat")
_SYSTEM_ROADMAP = _load_skill("roadmap")
_SYSTEM_TOP_SUMMARY = _load_skill("top_summary")

_FORBIDDEN_TOP_SUMMARY_TERMS = (
    "aggregaterating",
    "attribution loss",
    "capi",
    "lcp",
    "post-click",
    "render blocking",
    "render-blocking",
    "roas",
    "serp",
    "sgtm",
)


class TopSummaryResponse(BaseModel):
    core_thesis: str = Field(min_length=20)
    biggest_tech_risk: str = Field(min_length=10)
    biggest_tech_opportunity: str = Field(min_length=10)

    @field_validator("core_thesis", "biggest_tech_risk", "biggest_tech_opportunity")
    @classmethod
    def _strip_and_reject_jargon(cls, value: str) -> str:
        cleaned = value.strip()
        lowered = cleaned.lower()
        forbidden = [term for term in _FORBIDDEN_TOP_SUMMARY_TERMS if term in lowered]
        if forbidden:
            raise ValueError(f"contains forbidden jargon: {', '.join(forbidden)}")
        return cleaned


def _business_context(audit: FullAuditData) -> dict:
    annual = audit.estimated_annual_revenue_eur
    monthly = (annual or 108_000) / 12
    return {
        "estimated_annual_revenue_eur": annual,
        "estimated_monthly_revenue_eur": monthly,
        "source": "operator_input" if annual else "fallback_benchmark",
    }


def _checkout_for_ai(audit: FullAuditData) -> dict | None:
    cf = audit.checkout_flow
    if not cf:
        return None
    if cf.errors_encountered:
        return {
            "probe_status": "unreachable",
            "reason": cf.errors_encountered[0],
            "note": "Geen betrouwbare data over volgorde/velden/methodes — geen claims doen.",
        }
    return cf.model_dump(mode="json")


def _page_snapshot(page: dict, has_aggregate_rating: bool = False) -> dict:
    soup = BeautifulSoup(page["html"], "lxml")
    sp_found, sp_evidence = _detect_social_proof(page["html"], has_aggregate_rating)
    h1_tag = soup.find("h1")
    return {
        "url": page["url"],
        "title": (soup.title.string or "").strip()[:120] if soup.title else None,
        "h1": h1_tag.get_text(strip=True)[:160] if h1_tag else None,
        "primary_cta_texts": [
            t for t in (
                el.get_text(strip=True)[:60]
                for el in soup.find_all(["a", "button"], limit=25)
            )
            if t and len(t) <= 60
        ][:5],
        "has_email_input": bool(soup.find("input", attrs={"type": "email"})),
        "review_widget_detected": sp_found,
        "review_widget_evidence": sp_evidence,
    }


def _cro_payload(audit: FullAuditData, pages: list[dict] | None = None) -> str:
    has_agg_rating = bool(audit.rich_results and audit.rich_results.has_aggregate_rating)

    pages_sampled: dict = {}
    social_proof_by_page: dict = {}

    if pages:
        sampled = _sample_pages_by_type(pages)
        for ptype, page in sampled.items():
            if ptype in ("cart", "checkout", "account", "other"):
                continue
            snap = _page_snapshot(page, has_agg_rating if ptype == "pdp" else False)
            pages_sampled[ptype] = snap
            social_proof_by_page[ptype] = {
                "detected": snap["review_widget_detected"],
                "evidence": snap["review_widget_evidence"],
            }
    else:
        sp_detected = not any(
            "vertrouwenssignalen" in o.observation.lower()
            for o in audit.cro_observations
        )
        social_proof_by_page["homepage"] = {"detected": sp_detected, "evidence": None}

    return json.dumps({
        "checkout_flow": _checkout_for_ai(audit),
        "cro_observations": [o.model_dump(mode="json") for o in audit.cro_observations],
        "performance": {
            "mobile": audit.performance.mobile.model_dump(mode="json") if (audit.performance and audit.performance.mobile) else None,
            "lighthouse": audit.performance.lighthouse.model_dump(mode="json") if (audit.performance and audit.performance.lighthouse) else None,
        } if audit.performance else None,
        "rich_results": audit.rich_results.model_dump(mode="json") if audit.rich_results else None,
        "owned_channels": audit.owned_channels.model_dump(mode="json") if audit.owned_channels else None,
        "pages_sampled": pages_sampled,
        "social_proof_by_page": social_proof_by_page,
        "business_context": _business_context(audit),
    }, ensure_ascii=False)


def _deliverability_payload(audit: FullAuditData) -> str:
    return json.dumps({
        "dns_email": audit.dns_email.model_dump(mode="json") if audit.dns_email else None,
        "domain_health": audit.domain_health.model_dump(mode="json") if audit.domain_health else None,
        "owned_channels": audit.owned_channels.model_dump(mode="json") if audit.owned_channels else None,
        "security_compliance": audit.security_compliance.model_dump(mode="json") if audit.security_compliance else None,
        "business_context": _business_context(audit),
    }, ensure_ascii=False)


def _shopify_payload(audit: FullAuditData) -> str:
    return json.dumps({
        "platform_architecture": audit.platform_architecture.model_dump(mode="json") if audit.platform_architecture else None,
        "performance": {
            "mobile": audit.performance.mobile.model_dump(mode="json") if (audit.performance and audit.performance.mobile) else None,
            "lighthouse": audit.performance.lighthouse.model_dump(mode="json") if (audit.performance and audit.performance.lighthouse) else None,
        } if audit.performance else None,
        "third_party_scripts": audit.third_party_scripts.model_dump(mode="json") if audit.third_party_scripts else None,
        "cost_analysis": audit.cost_analysis.model_dump(mode="json") if audit.cost_analysis else None,
        "checkout_flow": _checkout_for_ai(audit),
        "owned_channels": audit.owned_channels.model_dump(mode="json") if audit.owned_channels else None,
        "tracking_data_quality": audit.tracking_data_quality.model_dump(mode="json") if audit.tracking_data_quality else None,
        "business_context": _business_context(audit),
    }, ensure_ascii=False)


def _ad_bounce_payload(audit: FullAuditData) -> str:
    return json.dumps({
        "ad_traffic_impact": audit.ad_traffic_impact.model_dump(mode="json") if audit.ad_traffic_impact else None,
        "performance": {
            "mobile": audit.performance.mobile.model_dump(mode="json") if (audit.performance and audit.performance.mobile) else None,
        } if audit.performance else None,
        "third_party_scripts": {
            "total_third_party_blocking_ms": audit.third_party_scripts.total_third_party_blocking_ms,
            "total_third_party_domains": audit.third_party_scripts.total_third_party_domains,
        } if audit.third_party_scripts else None,
        "tracking_data_quality": audit.tracking_data_quality.model_dump(mode="json") if audit.tracking_data_quality else None,
        "server_side_tracking": audit.server_side_tracking.model_dump(mode="json") if audit.server_side_tracking else None,
        "checkout_flow": _checkout_for_ai(audit),
        "business_context": _business_context(audit),
    }, ensure_ascii=False)


def _tech_payload(audit: FullAuditData) -> str:
    return json.dumps({
        "platform_architecture": audit.platform_architecture.model_dump(mode="json") if audit.platform_architecture else None,
        "performance": audit.performance.model_dump(mode="json") if audit.performance else None,
        "third_party_scripts": audit.third_party_scripts.model_dump(mode="json") if audit.third_party_scripts else None,
        "cost_analysis": audit.cost_analysis.model_dump(mode="json") if audit.cost_analysis else None,
        "server_side_tracking": audit.server_side_tracking.model_dump(mode="json") if audit.server_side_tracking else None,
        "business_context": _business_context(audit),
    }, ensure_ascii=False)


def _bloat_payload(audit: FullAuditData) -> str:
    return json.dumps({
        "platform_architecture": audit.platform_architecture.model_dump(mode="json") if audit.platform_architecture else None,
        "third_party_scripts": audit.third_party_scripts.model_dump(mode="json") if audit.third_party_scripts else None,
        "cost_analysis": audit.cost_analysis.model_dump(mode="json") if audit.cost_analysis else None,
        "performance": {
            "mobile": audit.performance.mobile.model_dump(mode="json") if (audit.performance and audit.performance.mobile) else None,
            "lighthouse": audit.performance.lighthouse.model_dump(mode="json") if (audit.performance and audit.performance.lighthouse) else None,
        } if audit.performance else None,
        "bloat_what_must_go_deterministic": [b.model_dump(mode="json") for b in audit.bloat_what_must_go],
        "business_context": _business_context(audit),
    }, ensure_ascii=False)


def _top_summary_payload(audit: FullAuditData) -> str:
    return json.dumps({
        "store_url": audit.store_url,
        "company_name": audit.company_name,
        "industry": audit.industry,
        "scan_level": audit.scan_level,
        "fallback_synthesis": {
            "core_thesis": audit.core_thesis,
            "biggest_tech_risk": audit.biggest_tech_risk,
            "biggest_tech_opportunity": audit.biggest_tech_opportunity,
            "est_performance_lift_percent": audit.est_performance_lift_percent,
            "audit_summary": audit.audit_summary,
        },
        "platform_architecture": audit.platform_architecture.model_dump(mode="json") if audit.platform_architecture else None,
        "performance": audit.performance.model_dump(mode="json") if audit.performance else None,
        "third_party_scripts": audit.third_party_scripts.model_dump(mode="json") if audit.third_party_scripts else None,
        "tracking_data_quality": audit.tracking_data_quality.model_dump(mode="json") if audit.tracking_data_quality else None,
        "checkout_flow": _checkout_for_ai(audit),
        "owned_channels": audit.owned_channels.model_dump(mode="json") if audit.owned_channels else None,
        "seo_health": audit.seo_health.model_dump(mode="json") if audit.seo_health else None,
        "security_compliance": audit.security_compliance.model_dump(mode="json") if audit.security_compliance else None,
        "cost_analysis": audit.cost_analysis.model_dump(mode="json") if audit.cost_analysis else None,
        "cro_observations": [o.model_dump(mode="json") for o in audit.cro_observations],
        "bloat_what_must_go": [b.model_dump(mode="json") for b in audit.bloat_what_must_go],
        "dns_email": audit.dns_email.model_dump(mode="json") if audit.dns_email else None,
        "domain_health": audit.domain_health.model_dump(mode="json") if audit.domain_health else None,
        "rich_results": audit.rich_results.model_dump(mode="json") if audit.rich_results else None,
        "server_side_tracking": audit.server_side_tracking.model_dump(mode="json") if audit.server_side_tracking else None,
        "accessibility": audit.accessibility.model_dump(mode="json") if audit.accessibility else None,
        "product_feeds": audit.product_feeds.model_dump(mode="json") if audit.product_feeds else None,
        "site_search": audit.site_search.model_dump(mode="json") if audit.site_search else None,
        "shipping": audit.shipping.model_dump(mode="json") if audit.shipping else None,
        "returns": audit.returns.model_dump(mode="json") if audit.returns else None,
        "multi_region": audit.multi_region.model_dump(mode="json") if audit.multi_region else None,
        "marketplaces": audit.marketplaces.model_dump(mode="json") if audit.marketplaces else None,
        "ad_traffic_impact": audit.ad_traffic_impact.model_dump(mode="json") if audit.ad_traffic_impact else None,
        "revenue_leak": audit.revenue_leak.model_dump(mode="json") if audit.revenue_leak else None,
        "business_context": _business_context(audit),
    }, ensure_ascii=False)


def _roadmap_payload(audit: FullAuditData, prior: dict) -> str:
    return json.dumps({
        "store_url": audit.store_url,
        "company_name": audit.company_name,
        "industry": audit.industry,
        "synthesis": {
            "core_thesis": audit.core_thesis,
            "biggest_tech_risk": audit.biggest_tech_risk,
            "biggest_tech_opportunity": audit.biggest_tech_opportunity,
            "est_performance_lift_percent": audit.est_performance_lift_percent,
        },
        "performance": {
            "mobile": audit.performance.mobile.model_dump(mode="json") if (audit.performance and audit.performance.mobile) else None,
            "lighthouse": audit.performance.lighthouse.model_dump(mode="json") if (audit.performance and audit.performance.lighthouse) else None,
        } if audit.performance else None,
        "platform_architecture": audit.platform_architecture.model_dump(mode="json") if audit.platform_architecture else None,
        "third_party_scripts": {
            "total_third_party_blocking_ms": audit.third_party_scripts.total_third_party_blocking_ms,
            "total_third_party_domains": audit.third_party_scripts.total_third_party_domains,
        } if audit.third_party_scripts else None,
        "tracking_data_quality": audit.tracking_data_quality.model_dump(mode="json") if audit.tracking_data_quality else None,
        "checkout_flow": _checkout_for_ai(audit),
        "dns_email": audit.dns_email.model_dump(mode="json") if audit.dns_email else None,
        "cost_analysis": audit.cost_analysis.model_dump(mode="json") if audit.cost_analysis else None,
        "ad_traffic_impact": audit.ad_traffic_impact.model_dump(mode="json") if audit.ad_traffic_impact else None,
        "revenue_leak": audit.revenue_leak.model_dump(mode="json") if audit.revenue_leak else None,
        "owned_channels": audit.owned_channels.model_dump(mode="json") if audit.owned_channels else None,
        "rich_results": audit.rich_results.model_dump(mode="json") if audit.rich_results else None,
        "business_context": _business_context(audit),
        "prior_skill_insights": prior,
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
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": payload}],
    )
    raw = message.content[0].text
    try:
        data = json.loads(_extract_json(raw))
        return AiSkillInsight.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning(
            "AI skill parse failed (stop_reason=%s, raw_len=%d): %.500s",
            message.stop_reason,
            len(raw),
            raw,
        )
        raise ValueError(f"Invalid AI skill response: {exc}") from exc


async def _call_top_summary(client: anthropic.AsyncAnthropic, payload: str) -> TopSummaryResponse:
    message = await client.messages.create(
        model=MODEL,
        max_tokens=1200,
        system=_SYSTEM_TOP_SUMMARY,
        messages=[{"role": "user", "content": payload}],
    )
    raw = message.content[0].text
    try:
        data = json.loads(_extract_json(raw))
        return TopSummaryResponse.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning(
            "Top summary parse failed (stop_reason=%s, raw_len=%d): %.500s",
            message.stop_reason,
            len(raw),
            raw,
        )
        raise ValueError(f"Invalid top summary response: {exc}") from exc


async def _call_shopify_skill(client: anthropic.AsyncAnthropic, payload: str) -> ShopifyMigrationInsight:
    message = await client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=_SYSTEM_SHOPIFY,
        messages=[{"role": "user", "content": payload}],
    )
    raw = message.content[0].text
    try:
        data = json.loads(_extract_json(raw))
        return ShopifyMigrationInsight.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning(
            "Shopify skill parse failed (stop_reason=%s, raw_len=%d): %.500s",
            message.stop_reason,
            len(raw),
            raw,
        )
        raise ValueError(f"Invalid shopify skill response: {exc}") from exc


async def _call_bloat_skill(client: anthropic.AsyncAnthropic, payload: str) -> AiBloatInsight:
    message = await client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=_SYSTEM_BLOAT,
        messages=[{"role": "user", "content": payload}],
    )
    raw = message.content[0].text
    try:
        data = json.loads(_extract_json(raw))
        return AiBloatInsight.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning(
            "Bloat skill parse failed (stop_reason=%s, raw_len=%d): %.500s",
            message.stop_reason,
            len(raw),
            raw,
        )
        raise ValueError(f"Invalid bloat skill response: {exc}") from exc


async def _call_roadmap_skill(client: anthropic.AsyncAnthropic, payload: str) -> StrategicRoadmap:
    message = await client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=_SYSTEM_ROADMAP,
        messages=[{"role": "user", "content": payload}],
    )
    raw = message.content[0].text
    try:
        data = json.loads(_extract_json(raw))
        return StrategicRoadmap.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning(
            "Roadmap skill parse failed (stop_reason=%s, raw_len=%d): %.500s",
            message.stop_reason,
            len(raw),
            raw,
        )
        raise ValueError(f"Invalid roadmap skill response: {exc}") from exc


async def generate_top_summary(audit: FullAuditData) -> TopSummaryResponse | None:
    if not settings.ANTHROPIC_API_KEY:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        return await _call_top_summary(client, _top_summary_payload(audit))
    except Exception as exc:
        logger.warning("Top summary AI failed; using deterministic fallback: %s", exc)
        return None


async def enrich_top_summary(audit: FullAuditData) -> bool:
    top_summary = await generate_top_summary(audit)
    if not top_summary:
        return False

    audit.core_thesis = top_summary.core_thesis
    audit.biggest_tech_risk = top_summary.biggest_tech_risk
    audit.biggest_tech_opportunity = top_summary.biggest_tech_opportunity
    return True


async def run_ai_analysis(audit: FullAuditData, pages: list[dict] | None = None) -> AiAnalysis | None:
    if not settings.ANTHROPIC_API_KEY:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    results = await asyncio.gather(
        _call_skill(client, _SYSTEM_CRO, _cro_payload(audit, pages)),
        _call_skill(client, _SYSTEM_DELIVERABILITY, _deliverability_payload(audit)),
        _call_skill(client, _SYSTEM_TECH, _tech_payload(audit)),
        _call_shopify_skill(client, _shopify_payload(audit)),
        _call_skill(client, _SYSTEM_AD_BOUNCE, _ad_bounce_payload(audit)),
        _call_bloat_skill(client, _bloat_payload(audit)),
        return_exceptions=True,
    )

    def _safe(val: object) -> AiSkillInsight | None:
        if isinstance(val, BaseException):
            logger.warning("AI skill failed: %s", val)
            return None
        return val  # type: ignore[return-value]

    def _safe_shopify(val: object) -> ShopifyMigrationInsight | None:
        if isinstance(val, BaseException):
            logger.warning("Shopify skill failed: %s", val)
            return None
        return val  # type: ignore[return-value]

    def _safe_bloat(val: object) -> AiBloatInsight | None:
        if isinstance(val, BaseException):
            logger.warning("Bloat skill failed: %s", val)
            return None
        return val  # type: ignore[return-value]

    cro = _safe(results[0])
    deliverability = _safe(results[1])
    tech = _safe(results[2])
    shopify = _safe_shopify(results[3])
    ad_bounce = _safe(results[4])
    bloat = _safe_bloat(results[5])

    prior_insights = {
        "cro": {"summary": cro.summary, "top_actions": cro.top_actions} if cro else None,
        "deliverability": {"summary": deliverability.summary, "top_actions": deliverability.top_actions} if deliverability else None,
        "tech_architecture": {"summary": tech.summary, "top_actions": tech.top_actions} if tech else None,
        "shopify_migration": {
            "recommendation": shopify.recommendation,
            "summary": shopify.summary,
            "rationale": shopify.rationale,
        } if shopify else None,
        "ad_bounce_revenue": {"summary": ad_bounce.summary, "top_actions": ad_bounce.top_actions} if ad_bounce else None,
        "bloat": {"summary": bloat.summary, "top_actions": bloat.top_actions} if bloat else None,
    }

    roadmap: StrategicRoadmap | None = None
    try:
        roadmap = await _call_roadmap_skill(client, _roadmap_payload(audit, prior_insights))
    except Exception as exc:
        logger.warning("Roadmap skill failed: %s", exc)

    return AiAnalysis(
        cro=cro,
        deliverability=deliverability,
        tech_architecture=tech,
        shopify_migration=shopify,
        ad_bounce_revenue=ad_bounce,
        bloat=bloat,
        roadmap=roadmap,
    )

"""The client-facing projection and the Sanity export: what a prospect may see.

Pure — no database: `build_client_report` takes an unsaved `FullAudit` row, and the
Sanity export runs without an Anthropic key (prose generation is skipped)."""

import asyncio
import json
import uuid
from datetime import UTC, datetime

from app.config import settings
from app.full_audit.analyzers.revenue_leak import calculate_revenue_leak
from app.full_audit.client_report import build_client_report
from app.full_audit.models import FullAudit
from app.full_audit.sanity_export import _prose_payload, build_sanity_export
from app.full_audit.schemas import FullAuditData, MobileCWV, Performance, SeRankingTraffic

INTERNAL_KEYS = {
    "tradual_pitch", "tradual_solution", "alarm_signal", "roi", "stack_rebuild_cost_eur",
    "contact_email", "contact_person", "sanity_export", "raw_response",
    "tradualPitch", "tradualSolution", "alarmSignal", "stackRebuildCostEur",
}


def _keys(node) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in _keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in _keys(v)}
    return set()


def _audit_data() -> FullAuditData:
    leak = calculate_revenue_leak(
        performance=Performance(mobile=MobileCWV(lcp_ms=5200.0, inp_ms=450.0, cls=0.3)),
        third_party=None, checkout=None, cro_observations=[],
        rich_results=None, product_feeds=None, accessibility=None, ad_traffic=None,
        annual_revenue_eur=2_000_000, aov_override=80.0, sessions_override=60_000,
        cr_override_pct=1.8, ad_spend_override=8_000.0,
    )
    assert leak.roi is not None and leak.ceo_triggers, "fixture must exercise the internal fields"
    return FullAuditData(
        store_url="https://store.nl", company_name="Store BV", scan_level="outside-only",
        contact_email="ceo@store.nl", contact_person="Sam", revenue_leak=leak,
        seranking_traffic=SeRankingTraffic(domain="store.nl", monthly_organic_sessions=40_000,
                                           monthly_paid_sessions=9_000, raw_response={"x": 1}),
        sanity_export={"password": "secret"},
    )


def _row() -> FullAudit:
    return FullAudit(
        id=uuid.uuid4(), store_url="https://store.nl", company_name="Store BV",
        scan_level="outside-only", status="ready_for_review", completed_at=datetime.now(UTC),
    )


def test_client_report_carries_no_internal_fields():
    report = build_client_report(_row(), _audit_data())
    payload = report.model_dump(mode="json")

    assert not (_keys(payload) & INTERNAL_KEYS)
    assert "secret" not in json.dumps(payload)
    # ...while keeping what the report page needs.
    leak = payload["revenue_leak"]
    assert leak["layers"] and leak["ceo_triggers"]
    assert leak["total_monthly_loss_eur_high"] > 0
    assert payload["seranking_traffic"] == {"monthly_organic_sessions": 40_000, "monthly_paid_sessions": 9_000}


def test_client_report_drops_warnings_about_the_sales_proposal():
    from app.full_audit.schemas import ModelWarning

    data = _audit_data()
    data.revenue_leak.model_warnings = [
        ModelWarning(kind="negative_payback", detail="Stack Rebuild-investering (€35.000) niet terugverdiend"),
        ModelWarning(kind="stage_ceiling_bound", detail="plafond"),
    ]
    kinds = [w.kind for w in build_client_report(_row(), data).revenue_leak.model_warnings]
    assert kinds == ["stage_ceiling_bound"]


def test_client_report_without_data_is_empty_not_an_error():
    report = build_client_report(_row(), None)
    assert report.revenue_leak is None and report.seranking_traffic is None


def test_sanity_export_carries_no_sales_copy_or_rebuild_pricing(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    export = asyncio.run(build_sanity_export(_audit_data()))

    leaked = _keys(export) & {"tradualPitch", "tradualSolution", "alarmSignal", "roi", "stackRebuildCostEur"}
    assert not leaked
    assert export["ctaSection"]["primaryButtonUrl"] == settings.CONTACT_URL


def test_prose_model_never_reads_sales_copy_or_contact_details():
    payload = _prose_payload(_audit_data())
    assert not (_keys(payload) & INTERNAL_KEYS)


def test_client_report_carries_actions_assumptions_and_citations():
    report = build_client_report(_row(), _audit_data())
    leak = report.revenue_leak
    assert leak.actions and leak.actions[0].priced
    keys = {a.key: a for a in report.assumptions}
    assert keys["monthly_sessions"].source == "operator"
    assert keys["aov_eur"].source == "operator"
    assert keys["mobile_share"].source == "benchmark"
    cited = {c.key for c in report.citations}
    assert "DELOITTE_MS_MILLIONS" in cited
    assert all(c.source for c in report.citations)


def test_client_roadmap_drops_llm_euros_and_keeps_registry_euros():
    from app.full_audit.schemas import AiAnalysis, RoadmapPhase, StrategicRoadmap

    data = _audit_data()
    data.ai_analysis = AiAnalysis(roadmap=StrategicRoadmap(
        executive_summary="x", north_star_metric="y",
        phases=[RoadmapPhase(phase=1, name="a", timeframe="", objective="", expected_outcome="",
                             est_monthly_revenue_impact_eur=123_456,  # stored LLM figure
                             finding_ids=["perf.lcp_mobile"],
                             est_monthly_impact_eur_low=1.0, est_monthly_impact_eur_high=2.0)],
    ))
    phase = build_client_report(_row(), data).roadmap.phases[0]
    assert phase.est_monthly_revenue_impact_eur is None
    assert (phase.est_monthly_impact_eur_low, phase.est_monthly_impact_eur_high) == (1.0, 2.0)
    assert data.ai_analysis.roadmap.phases[0].est_monthly_revenue_impact_eur == 123_456  # source untouched


def test_sanity_revenue_leak_matches_the_client_projection(monkeypatch):
    from app.full_audit.schemas import ModelWarning

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    data = _audit_data()
    data.revenue_leak.model_warnings.append(ModelWarning(kind="negative_payback", detail="Stack Rebuild €35.000"))
    export = asyncio.run(build_sanity_export(data))
    client = build_client_report(_row(), data)

    leak = export["revenueLeak"]
    assert leak["totalMonthlyLossEurHigh"] == client.revenue_leak.total_monthly_loss_eur_high
    assert [w["kind"] for w in leak["modelWarnings"]] == [w.kind for w in client.revenue_leak.model_warnings]
    assert "negative_payback" not in json.dumps(export)
    assert [a["actionKey"] for a in export["actions"]] == [a.action_key for a in client.revenue_leak.actions]
    assert len(export["assumptions"]) == len(client.assumptions)
    assert "Stack Rebuild €35" not in json.dumps(_prose_payload(data))

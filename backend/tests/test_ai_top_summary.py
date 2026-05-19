import json
from types import SimpleNamespace

import pytest

from app.config import settings
from app.full_audit.analyzers import ai_analysis
from app.full_audit.schemas import (
    FullAuditData,
    RevenueLeakReport,
    RichResultsHealth,
    TrackingDataQuality,
)


def _audit() -> FullAuditData:
    return FullAuditData(
        store_url="https://example.com",
        scan_level="outside-only",
        core_thesis="Fallback kernthese",
        biggest_tech_risk="Fallback risico",
        biggest_tech_opportunity="Fallback kans",
        tracking_data_quality=TrackingDataQuality(est_attribution_loss_percent=35),
        rich_results=RichResultsHealth(has_aggregate_rating=False),
        revenue_leak=RevenueLeakReport(total_monthly_loss_eur=48900),
    )


def _mock_anthropic(monkeypatch: pytest.MonkeyPatch, response_text: str) -> list[dict]:
    calls: list[dict] = []

    class FakeMessages:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(text=response_text)],
                stop_reason="end_turn",
            )

    class FakeClient:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.messages = FakeMessages()

    monkeypatch.setattr(ai_analysis.anthropic, "AsyncAnthropic", FakeClient)
    return calls


@pytest.mark.asyncio
async def test_enrich_top_summary_keeps_fallback_without_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    audit = _audit()

    changed = await ai_analysis.enrich_top_summary(audit)

    assert changed is False
    assert audit.core_thesis == "Fallback kernthese"
    assert audit.biggest_tech_risk == "Fallback risico"
    assert audit.biggest_tech_opportunity == "Fallback kans"


@pytest.mark.asyncio
async def test_enrich_top_summary_replaces_fallback_with_valid_ai_output(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    response = {
        "core_thesis": "Ongeveer een derde van je bestellingen komt waarschijnlijk niet goed aan in Meta of Google. Daardoor leren je advertenties van onvolledige data.",
        "biggest_tech_risk": "Je campagnes sturen waarschijnlijk op onvolledige verkoopdata en blijven daardoor te dure klikken inkopen.",
        "biggest_tech_opportunity": "Je reviews worden nog niet als sterren in Google getoond, waardoor je zoekresultaat minder snel opvalt.",
    }
    calls = _mock_anthropic(monkeypatch, json.dumps(response))
    audit = _audit()

    changed = await ai_analysis.enrich_top_summary(audit)

    assert changed is True
    assert audit.core_thesis == response["core_thesis"]
    assert audit.biggest_tech_risk == response["biggest_tech_risk"]
    assert audit.biggest_tech_opportunity == response["biggest_tech_opportunity"]
    payload = calls[0]["messages"][0]["content"]
    assert "tracking_data_quality" in payload
    assert "rich_results" in payload
    assert "revenue_leak" in payload


@pytest.mark.asyncio
async def test_enrich_top_summary_keeps_fallback_for_invalid_ai_json(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    _mock_anthropic(monkeypatch, '{"core_thesis": "Mist verplichte velden"}')
    audit = _audit()

    changed = await ai_analysis.enrich_top_summary(audit)

    assert changed is False
    assert audit.core_thesis == "Fallback kernthese"
    assert audit.biggest_tech_risk == "Fallback risico"
    assert audit.biggest_tech_opportunity == "Fallback kans"


@pytest.mark.asyncio
async def test_enrich_top_summary_rejects_jargon_in_ai_output(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    response = {
        "core_thesis": "Mobile LCP is slecht en attribution loss is hoog, waardoor de rapportage onbetrouwbaar blijft.",
        "biggest_tech_risk": "35% attribution loss door tracking-gaps.",
        "biggest_tech_opportunity": "Geen AggregateRating schema in de SERP.",
    }
    _mock_anthropic(monkeypatch, json.dumps(response))
    audit = _audit()

    changed = await ai_analysis.enrich_top_summary(audit)

    assert changed is False
    assert audit.core_thesis == "Fallback kernthese"
    assert audit.biggest_tech_risk == "Fallback risico"
    assert audit.biggest_tech_opportunity == "Fallback kans"

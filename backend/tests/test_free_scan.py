"""The free lead scan runs the full audit's euro model — no second model, no dollars,
no invented range."""

import json
import uuid
from decimal import Decimal

import pytest

from app.full_audit.schemas import LighthouseScores, MobileCWV, Performance, ThirdPartyScripts
from app.leads.models import Lead
from app.reports import service as free_scan
from app.reports.models import Report
from tests.conftest import TestSessionLocal


def _slow_performance() -> Performance:
    return Performance(
        mobile=MobileCWV(lcp_ms=5_200.0, inp_ms=450.0, cls=0.3),
        lighthouse=LighthouseScores(performance=38),
        tbt_ms=650.0,
    )


def _report_data(monthly_revenue=Decimal("40000"), monthly_traffic=20_000) -> dict:
    leak = free_scan._revenue_leak(_slow_performance(), None, monthly_revenue, monthly_traffic)
    return {"revenue_leak": leak.model_dump(mode="json"), "lcp_ms": 5_200.0, "model_version": leak.model_version}


def test_summary_is_a_real_eur_range_from_the_funnel_model():
    summary = free_scan.build_free_scan_summary(_report_data())

    assert summary["model_version"] is not None
    assert 0 < summary["estimated_monthly_loss_low"] < summary["estimated_monthly_loss_high"]
    assert summary["findings"] and summary["findings"][0].priced
    assert [f.monthly_high for f in summary["findings"] if f.priced] == sorted(
        (f.monthly_high for f in summary["findings"] if f.priced), reverse=True
    )
    assert summary["actions"] and all(a.title_nl for a in summary["actions"])
    sources = {a.key: a.source for a in summary["assumptions"]}
    assert sources["monthly_sessions"] == "operator" and sources["conversion_rate"] == "derived"
    dumped = json.dumps({k: str(v) for k, v in summary.items()})
    assert "stack_rebuild" not in dumped and "tradual_pitch" not in dumped


def test_free_scan_prices_performance_exactly_like_the_full_audit():
    """Same inputs, same performance → the same perf findings, euro for euro."""
    from app.full_audit.analyzers.ad_traffic import calculate_ad_traffic_impact
    from app.full_audit.analyzers.revenue_leak import calculate_revenue_leak

    performance = _slow_performance()
    third_party = ThirdPartyScripts(total_third_party_blocking_ms=1_800)
    inputs = dict(annual_revenue_eur=40_000 * 12, sessions_override=20_000)
    ad = calculate_ad_traffic_impact(performance, third_party, None, None, **inputs)
    audit = calculate_revenue_leak(performance, third_party, None, [], None, None, None, ad, **inputs)
    scan = free_scan._revenue_leak(performance, third_party, Decimal("40000"), 20_000)

    def perf(report):
        return {f.finding_id: (f.monthly_low, f.monthly_high) for f in report.findings if f.finding_id.startswith(("perf.", "adtraffic."))}

    assert perf(scan) == perf(audit) and perf(scan)


def test_revenue_that_the_traffic_cannot_carry_is_flagged():
    summary = free_scan.build_free_scan_summary(_report_data(Decimal("100000"), 1_000))
    assert summary["data_conflicts"], "€100k/mnd from 1,000 visitors must be questioned"


# --- persistence + endpoint -------------------------------------------------------------



async def _lead_and_report(db_session) -> Report:
    lead = Lead(id=uuid.uuid4(), email=f"{uuid.uuid4().hex}@example.com", platform="shopify",
                store_url="https://store.nl", monthly_revenue=40_000, monthly_traffic=20_000)
    report = Report(id=uuid.uuid4(), lead_id=lead.id, status="pending")
    db_session.add_all([lead, report])
    await db_session.commit()
    return report


@pytest.mark.asyncio
async def test_run_analysis_stores_the_funnel_model_result(db_session, monkeypatch):
    report = await _lead_and_report(db_session)
    pages = [{"url": "https://store.nl/", "html": "<html></html>", "headers": {}, "load_time_ms": 90}]

    async def fake_scrape(url):
        return {"pages": pages, "pages_discovered": 1}

    async def fake_performance(url, pages, include_desktop=True):
        assert include_desktop is False  # the free scan skips the desktop PSI run
        return _slow_performance(), {}

    async def fake_third_party(pages):
        return ThirdPartyScripts()

    monkeypatch.setattr(free_scan, "scrape_store", fake_scrape)
    monkeypatch.setattr(free_scan, "analyze_performance", fake_performance)
    monkeypatch.setattr(free_scan, "scan_third_party", fake_third_party)
    monkeypatch.setattr(free_scan, "AsyncSessionLocal", TestSessionLocal)

    await free_scan.run_analysis(report.id, "https://store.nl", "shopify", Decimal("40000"), 20_000)

    async with TestSessionLocal() as db:
        stored = await db.get(Report, report.id)
    assert stored.status == "completed", stored.error_message
    assert stored.report_data["model_version"] == stored.report_data["revenue_leak"]["model_version"]
    assert stored.avg_load_time_ms == 5_200


@pytest.mark.asyncio
async def test_summary_of_an_old_scan_shows_one_figure_and_no_invented_range(client, db_session):
    report = await _lead_and_report(db_session)
    report.status = "completed"
    report.estimated_monthly_loss = 1_234
    report.report_data = {"pages_scraped": ["https://store.nl/"], "blended_loss_rate": 0.1}
    await db_session.commit()

    resp = await client.get(f"/api/v1/reports/{report.id}/summary")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["legacy_monthly_loss_estimate"] == 1_234
    assert body["estimated_monthly_loss_low"] is None and body["estimated_monthly_loss_high"] is None
    assert body["currency"] == "EUR"

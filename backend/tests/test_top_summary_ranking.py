"""Tests for the full-audit headline ranking (`_synthesize` / `_build_thesis`).

Regression coverage for a real report where a DMARC finding with €0 priced impact
anywhere in the report became "Grootste risico" ahead of a 16.8s collection-page LCP
that the Revenue Leak section priced in the thousands of euros — because the old
selection was `risks[0]` over a hand-ordered append list, not a ranking.
"""

from app.full_audit.analyzers.revenue_leak import calculate_revenue_leak
from app.full_audit.schemas import DnsEmailHealth, LighthouseScores, MobileCWV, Performance
from app.full_audit.service import _build_thesis, _synthesize


def _dmarc_missing() -> DnsEmailHealth:
    return DnsEmailHealth(dmarc_policy="missing", spf_status="valid")


def _slow_performance() -> Performance:
    return Performance(
        mobile=MobileCWV(lcp_ms=5_000.0),
        lighthouse=LighthouseScores(performance=60),
    )


def _healthy_performance() -> Performance:
    return Performance(
        mobile=MobileCWV(lcp_ms=1_400.0, inp_ms=80.0, cls=0.02),
        lighthouse=LighthouseScores(performance=95),
        tbt_ms=100.0,
    )


def test_priced_lcp_outranks_unpriced_dmarc():
    """DMARC has no euro figure anywhere in the report (dns_email is never passed to
    calculate_revenue_leak); a priced LCP finding must win the headline instead of
    losing on append order."""
    performance = _slow_performance()
    revenue_leak = calculate_revenue_leak(
        performance=performance,
        third_party=None,
        tracking=None,
        checkout=None,
        owned=None,
        cro_observations=[],
        rich_results=None,
        product_feeds=None,
        accessibility=None,
        ad_traffic=None,
        annual_revenue_eur=1_152_000,
        aov_override=120.0,
        sessions_override=20_000,
        cr_override_pct=4.0,
    )
    assert revenue_leak.total_monthly_loss_eur_low, "fixture must actually price something"

    synthesis = _synthesize(
        performance=performance,
        third_party=None,
        tracking=None,
        cost=None,
        platform=None,
        dns_email=_dmarc_missing(),
        rich_results=None,
        store_url="https://example.com",
        revenue_leak_monthly_eur=revenue_leak.total_monthly_loss_eur_low,
        revenue_leak=revenue_leak,
    )

    assert "seconden" in synthesis["biggest_tech_risk"]
    assert "e-mail" not in synthesis["biggest_tech_risk"].lower()
    assert synthesis["core_thesis"] is not None
    assert "Geschatte lekkage" in synthesis["core_thesis"]


def test_dmarc_headline_drops_leak_clause_when_it_has_no_priced_impact():
    """When nothing else is wrong, DMARC still becomes the headline (it's the only
    signal) — but it must not borrow the report-wide leak figure it didn't cause."""
    performance = _healthy_performance()

    synthesis = _synthesize(
        performance=performance,
        third_party=None,
        tracking=None,
        cost=None,
        platform=None,
        dns_email=_dmarc_missing(),
        rich_results=None,
        store_url="https://example.com",
        # Simulates a report where SOME other, unrelated finding produced a total —
        # it must not get glued onto the DMARC sentence.
        revenue_leak_monthly_eur=1_500.0,
        revenue_leak=None,
    )

    assert synthesis["biggest_tech_risk"] is not None
    assert "e-mailbeveiliging" in synthesis["biggest_tech_risk"].lower()
    assert synthesis["core_thesis"] is not None
    assert "Geschatte lekkage" not in synthesis["core_thesis"]


def test_build_thesis_omits_amount_for_zero_impact_signal():
    signal = {"kind": "dmarc", "policy": "missing"}
    thesis = _build_thesis(signal, monthly_leak_eur=None)
    assert "Geschatte lekkage" not in thesis


def test_build_thesis_includes_amount_for_priced_signal():
    signal = {"kind": "lcp_critical", "lcp_s": 5.0, "lcp_caveat": ""}
    thesis = _build_thesis(signal, monthly_leak_eur=1500.0)
    assert "Geschatte lekkage: €1,500 per maand." in thesis

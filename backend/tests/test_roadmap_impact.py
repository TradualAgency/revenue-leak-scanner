"""Roadmap euros come from the registry, not from the LLM."""

from app.full_audit.analyzers.ai_analysis import attach_roadmap_impact
from app.full_audit.schemas import FindingOut, RoadmapPhase, StrategicRoadmap


def _finding(fid, low=None, high=None):
    return FindingOut(finding_id=fid, owning_layer=1, metric=fid,
                      monthly_low=low, monthly_high=high, priced=low is not None)


def _phase(n, ids, llm_eur=None):
    return RoadmapPhase(phase=n, name=f"Fase {n}", timeframe="", objective="", expected_outcome="",
                        finding_ids=ids, est_monthly_revenue_impact_eur=llm_eur)


def test_phase_euros_are_the_sum_of_the_findings_it_claims():
    roadmap = StrategicRoadmap(executive_summary="", north_star_metric="", phases=[
        _phase(1, ["perf.lcp_mobile", "checkout.no_guest"], llm_eur=99_999),
        _phase(2, ["cro.social_proof"]),
    ])
    findings = [
        _finding("perf.lcp_mobile", 1_000, 3_000),
        _finding("checkout.no_guest", 500, 1_500),
        _finding("cro.social_proof"),  # unpriced
    ]
    out = attach_roadmap_impact(roadmap, findings)

    p1, p2 = out.phases
    assert (p1.est_monthly_impact_eur_low, p1.est_monthly_impact_eur_high) == (1_500, 4_500)
    assert p1.est_monthly_revenue_impact_eur is None  # the LLM's number is discarded
    assert p2.finding_ids == ["cro.social_proof"]
    assert p2.est_monthly_impact_eur_low is None  # nothing priced in this phase


def test_unknown_ids_are_dropped_and_a_finding_counts_in_one_phase_only():
    roadmap = StrategicRoadmap(executive_summary="", north_star_metric="", phases=[
        _phase(2, ["perf.lcp_mobile"]),
        _phase(1, ["perf.lcp_mobile", "made.up_by_llm", "perf.lcp_mobile"]),
    ])
    out = attach_roadmap_impact(roadmap, [_finding("perf.lcp_mobile", 1_000, 3_000)])

    by_phase = {p.phase: p for p in out.phases}
    assert by_phase[1].finding_ids == ["perf.lcp_mobile"]
    assert by_phase[1].est_monthly_impact_eur_high == 3_000
    assert by_phase[2].finding_ids == []
    assert by_phase[2].est_monthly_impact_eur_high is None

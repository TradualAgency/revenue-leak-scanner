"""The prospect-facing projection of a full audit.

`/full-audit/{id}` is the operator's dashboard and carries everything: contact details,
sales pitch copy per CEO trigger, Stack Rebuild pricing, the Sanity export. Client
output — the `/revenue-leak/{id}` page and the Sanity report — is built from
`build_client_content` instead, by allowlist, so a new internal field can't leak just
because nobody remembered to strip it, and the two client outputs can't disagree.
"""

from __future__ import annotations

from app.full_audit.analyzers.benchmarks import CITATIONS
from app.full_audit.models import FullAudit
from app.full_audit.schemas import (
    INTERNAL_WARNING_KINDS,
    ClientAssumption,
    ClientAuditReport,
    ClientCeoTrigger,
    ClientCitation,
    ClientReportContent,
    ClientRevenueLeakReport,
    ClientSeRankingTraffic,
    FullAuditData,
    FunnelModel,
    RevenueLeakReport,
    StrategicRoadmap,
)

_SOURCE_EXPLANATION_NL = {
    "operator": "Door jullie opgegeven.",
    "seranking": "Schatting van SE Ranking op basis van zoek- en advertentieverkeer.",
    "derived": "Berekend uit jullie opgegeven omzet en bezoekersaantal.",
    "benchmark": (
        "Branchegemiddelde: er was geen eigen cijfer beschikbaar. "
        "Met een eigen cijfer worden de bedragen nauwkeuriger."
    ),
}


def client_revenue_leak(leak: RevenueLeakReport) -> ClientRevenueLeakReport:
    return ClientRevenueLeakReport.model_validate({
        **leak.model_dump(exclude={"ceo_triggers", "roi", "model_warnings", "verification"}),
        "model_warnings": [w for w in leak.model_warnings if w.kind not in INTERNAL_WARNING_KINDS],
        "ceo_triggers": [
            ClientCeoTrigger(
                category=t.category,
                kpi=t.kpi,
                what_ceo_sees=t.what_ceo_sees,
                benchmark=t.benchmark,
                real_meaning=t.real_meaning,
                triggered=t.triggered,
            )
            for t in leak.ceo_triggers
        ],
    })


def client_roadmap(roadmap: StrategicRoadmap) -> StrategicRoadmap:
    """Phases keep only registry-derived euros. Rows stored before that change carry an
    LLM-written `est_monthly_revenue_impact_eur` — dropped, never shown as a model figure."""
    copy = roadmap.model_copy(deep=True)
    for phase in copy.phases:
        phase.est_monthly_revenue_impact_eur = None
    return copy


def client_assumptions(funnel: FunnelModel) -> list[ClientAssumption]:
    def row(key, label, value, unit, source, explanation=None):
        return ClientAssumption(
            key=key, label_nl=label, value=value, unit=unit, source=source,
            explanation_nl=explanation or _SOURCE_EXPLANATION_NL[source],
        )

    return [
        row("monthly_sessions", "Bezoekers per maand", funnel.monthly_sessions, "count", funnel.sessions_source),
        row("conversion_rate", "Conversieratio", funnel.conversion_rate * 100, "pct", funnel.cr_source),
        row("aov_eur", "Gemiddelde bestelwaarde", funnel.aov_eur, "eur", funnel.aov_source),
        row(
            "monthly_revenue_eur", "Omzet per maand", funnel.monthly_revenue_eur, "eur",
            "benchmark" if funnel.data_source == "heuristic" else "derived",
            "Bezoekers × conversieratio × bestelwaarde. Elk bedrag in dit rapport is een aandeel van dit getal.",
        ),
        row("mobile_share", "Aandeel mobiel verkeer", funnel.mobile_share * 100, "pct", funnel.mobile_share_source),
        row(
            "paid_share", "Aandeel betaald verkeer", funnel.paid_share * 100, "pct",
            "seranking" if funnel.sessions_source == "seranking" else "benchmark",
        ),
        row("monthly_ad_spend_eur", "Advertentiebudget per maand", funnel.monthly_ad_spend_eur, "eur", funnel.ad_spend_source),
    ]


def client_citations(leak: RevenueLeakReport) -> list[ClientCitation]:
    keys = [f.citation for f in leak.findings if f.citation]
    keys += [m.citation for layer in leak.layers for m in layer.metrics if m.citation]  # v1 rows have no findings
    return [
        ClientCitation(
            key=key, source=c.source_nl or c.source, figure_nl=c.figure_nl, note_nl=c.note_nl, verified=c.verified,
        )
        for key in dict.fromkeys(keys)
        if (c := CITATIONS.get(key)) is not None
    ]


def build_client_content(data: FullAuditData | None) -> ClientReportContent:
    if data is None:
        return ClientReportContent()
    leak = data.revenue_leak
    seranking = data.seranking_traffic
    roadmap = data.ai_analysis.roadmap if data.ai_analysis else None
    return ClientReportContent(
        revenue_leak=client_revenue_leak(leak) if leak else None,
        ad_traffic_impact=data.ad_traffic_impact,
        seranking_traffic=ClientSeRankingTraffic(
            monthly_organic_sessions=seranking.monthly_organic_sessions,
            monthly_paid_sessions=seranking.monthly_paid_sessions,
        ) if seranking is not None else None,
        roadmap=client_roadmap(roadmap) if roadmap else None,
        assumptions=client_assumptions(leak.funnel) if leak and leak.funnel else [],
        citations=client_citations(leak) if leak else [],
        methodology_note=data.methodology_note,
    )


def build_client_report(audit: FullAudit, data: FullAuditData | None) -> ClientAuditReport:
    return ClientAuditReport(
        **build_client_content(data).model_dump(),
        id=audit.id,
        status=audit.status,  # type: ignore[arg-type]
        store_url=audit.store_url,
        company_name=audit.company_name,
        completed_at=audit.completed_at,
    )

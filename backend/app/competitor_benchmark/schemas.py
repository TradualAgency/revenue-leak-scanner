from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.full_audit.schemas import (
    AccessibilityHealth,
    CheckoutFlow,
    CostAnalysis,
    DnsEmailHealth,
    DomainHealth,
    PlatformArchitecture,
    Performance,
    ProductFeedHealth,
    RichResultsHealth,
    SeoHealth,
    ServerSideTracking,
    ThirdPartyScripts,
    TrackingDataQuality,
)

# --- discovery -----------------------------------------------------------------

DiscoverySource = Literal["competitors_domain", "serp_competitors", "both", "operator"]
Classification = Literal["direct", "category", "marketplace", "retailer", "irrelevant", "operator"]
RejectReasonCode = Literal[
    "self", "same_brand", "blocklist", "size_band", "min_intersections",
    "market_coherence", "ai_excluded", "enrichment_unreachable",
]


class CandidateDomain(BaseModel):
    domain: str
    discovery_source: DiscoverySource
    organic_keywords_count: int | None = None
    est_organic_traffic_value_usd: float | None = None
    avg_keyword_position: float | None = None
    intersections: int | None = None
    serp_keyword_hits: int | None = None
    size_ratio_to_store: float | None = None
    title: str | None = None
    meta_description: str | None = None
    og_site_name: str | None = None
    platform_guess: str | None = None
    html_lang: str | None = None
    enrichment_status: Literal["ok", "unreachable", "skipped"] = "skipped"
    classification: Classification | None = None
    relevance_score: float | None = None
    reason_nl: str | None = None
    rank: int | None = None


class RejectedCandidate(BaseModel):
    domain: str
    reason_code: RejectReasonCode
    reason_nl: str
    category: str | None = None


class MarketInfo(BaseModel):
    location_code: int
    language_code: str
    source: str
    confidence: Literal["high", "medium", "low"]


class AiRankedCompetitor(BaseModel):
    domain: str
    rank: int
    classification: Literal["direct", "category", "marketplace", "retailer", "irrelevant"]
    relevance_score: float
    reason_nl: str
    shared_audience: str | None = None


class AiExcludedCompetitor(BaseModel):
    domain: str
    classification: Literal["marketplace", "retailer", "irrelevant"]
    reason_nl: str


class CompetitorRelevanceResponse(BaseModel):
    ranked: list[AiRankedCompetitor] = []
    excluded: list[AiExcludedCompetitor] = []
    market_note_nl: str | None = None


class DiscoveryResult(BaseModel):
    """Full audit trail of one discovery run — the operator-only /candidates payload."""
    market: MarketInfo
    store_organic_keywords_count: int | None = None
    store_est_organic_traffic_value_usd: float | None = None
    kept: list[CandidateDomain] = []
    rejected: list[RejectedCandidate] = []
    market_note_nl: str | None = None
    ai_ranking_used: bool = False


# --- measurement ---------------------------------------------------------------

MeasureStatus = Literal["ok", "partial", "unreachable", "timeout"]


class CompetitorSnapshot(BaseModel):
    """One domain's measurement across all 5 audit layers — reuses the same
    per-analyzer schemas the full audit already produces, so metric extraction can
    read them identically regardless of whether the domain is the audited store or a
    competitor."""
    domain: str
    measure_status: MeasureStatus
    measured_at: datetime
    unavailable_metrics: list[str] = []
    checkout_probed: bool = False
    platform: PlatformArchitecture | None = None
    performance: Performance | None = None
    third_party: ThirdPartyScripts | None = None
    checkout: CheckoutFlow | None = None
    tracking: TrackingDataQuality | None = None
    server_side_tracking: ServerSideTracking | None = None
    dns_email: DnsEmailHealth | None = None
    domain_health: DomainHealth | None = None
    rich_results: RichResultsHealth | None = None
    product_feeds: ProductFeedHealth | None = None
    seo: SeoHealth | None = None
    accessibility: AccessibilityHealth | None = None
    cost: CostAnalysis | None = None


# --- comparison / scoring --------------------------------------------------------

Sufficiency = Literal["sufficient", "thin", "insufficient"]


class CompetitorMetricValue(BaseModel):
    domain: str
    value: float | None = None
    available: bool
    unavailable_reason: str | None = None
    source: str | None = None  # e.g. CrUX "field" vs "lab" for LCP


class MetricComparison(BaseModel):
    key: str
    layer: int
    label_nl: str
    unit: str
    direction: Literal["lower_is_better", "higher_is_better"]
    store_value: float | None = None
    store_measured: bool = False
    competitor_values: list[CompetitorMetricValue] = []
    median: float | None = None
    best: float | None = None
    best_domain: str | None = None
    p25: float | None = None
    store_rank: int | None = None
    domains_ranked: int | None = None
    store_percentile: float | None = None
    gap_to_median_abs: float | None = None
    gap_to_median_pct: float | None = None
    measured_domains: int = 0
    eligible_domains: int = 0
    total_domains: int = 0
    coverage_label_nl: str = ""
    sufficiency: Sufficiency = "insufficient"
    unavailable_reasons: dict[str, str] = {}


class LayerScore(BaseModel):
    layer: int
    name_nl: str
    relative_score: float | None = None
    absolute_score: float | None = None
    metrics_used: int = 0
    metrics_unavailable: int = 0
    rank_in_set: int | None = None
    summary_nl: str | None = None


class GapFinding(BaseModel):
    finding_id: str
    layer: int
    label_nl: str
    store_value: float | None = None
    median_value: float | None = None
    best_value: float | None = None
    gap_to_median_eur_low: float | None = None
    gap_to_median_eur_high: float | None = None
    gap_to_best_eur_low: float | None = None
    gap_to_best_eur_high: float | None = None
    market_is_also_below_benchmark: bool = False
    kind: Literal["revenue", "diagnostic"] = "revenue"
    confidence: Literal["high", "medium", "low"] = "medium"
    citation: str | None = None
    note_nl: str | None = None


class CompetitorRosterEntry(BaseModel):
    domain: str
    classification: Classification | None = None
    reason_nl: str | None = None
    measure_status: MeasureStatus
    measured_at: datetime | None = None
    is_shopify: bool | None = None
    discovery_source: DiscoverySource | None = None


class CompetitorBenchmarkData(BaseModel):
    store_domain: str
    market: MarketInfo
    roster: list[CompetitorRosterEntry] = []
    comparisons: list[MetricComparison] = []
    layer_scores: list[LayerScore] = []
    overall_relative_score: float | None = None
    gaps: list[GapFinding] = []
    gap_to_median_monthly_eur_low: float | None = None
    gap_to_median_monthly_eur_high: float | None = None
    gap_to_best_monthly_eur_low: float | None = None
    gap_to_best_monthly_eur_high: float | None = None
    market_is_also_below_benchmark: bool = False
    # True once the operator has removed at least one auto-discovered competitor — the
    # page must stop calling this "je markt" and say it was hand-assembled instead,
    # since a curated median is no longer an honest market median.
    manually_curated: bool = False
    checkout_probe_included: bool = False
    methodology_note_nl: str | None = None
    narrative_nl: str | None = None
    generated_at: datetime


# --- run lifecycle ---------------------------------------------------------------

CompetitorRunStatus = Literal[
    "queued", "discovering", "measuring", "scoring", "ready", "insufficient_data", "failed",
]


class CompetitorBenchmarkCreateRequest(BaseModel):
    full_audit_id: uuid.UUID
    location_code: int | None = None
    language_code: str | None = None
    max_competitors: int | None = None
    include_checkout_probe: bool = False


class CompetitorBenchmarkCreateResponse(BaseModel):
    id: uuid.UUID
    status: CompetitorRunStatus
    created_at: datetime


class CompetitorBenchmarkStatusResponse(BaseModel):
    id: uuid.UUID
    status: CompetitorRunStatus
    store_domain: str
    phase_label_nl: str | None = None
    measured_count: int = 0
    total_count: int = 0
    created_at: datetime
    completed_at: datetime | None = None


class CompetitorBenchmarkResponse(BaseModel):
    id: uuid.UUID
    status: CompetitorRunStatus
    store_domain: str
    data: CompetitorBenchmarkData | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class CompetitorCandidatesResponse(BaseModel):
    kept: list[CandidateDomain] = []
    rejected: list[RejectedCandidate] = []
    market: MarketInfo | None = None
    market_note_nl: str | None = None


class CompetitorSetUpdateRequest(BaseModel):
    add: list[str] = []
    remove: list[str] = []
    location_code: int | None = None
    language_code: str | None = None


class CompetitorRemeasureRequest(BaseModel):
    force: bool = False

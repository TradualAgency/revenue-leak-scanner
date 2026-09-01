import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ScanLevel = Literal["outside-only", "semi", "full-access"]
AuditStatus = Literal["queued", "processing", "ready_for_review", "failed"]
Rating = Literal["good", "needs-improvement", "poor"]
DetectionConfidence = Literal["confirmed", "probable", "unknown"]
ArchitectureType = Literal["monolith", "headless", "hybrid", "unknown"]
Necessity = Literal["critical", "useful", "removable", "replaceable"]
HealthStatus = Literal["healthy", "partial", "missing", "to-validate"]
SslStatus = Literal["valid", "issues", "missing"]
TrafficTrend = Literal["rising", "stable", "declining", "unknown"]
ConsentModeStatus = Literal["v2-correct", "v2-incorrect", "none", "to-validate"]
HreflangSetup = Literal["correct", "incorrect", "n-a", "to-validate"]
PciStatus = Literal["likely", "concerns", "n-a"]
ServerSideTagging = Literal["yes", "no", "to-validate"]
BloatCategory = Literal["app", "script", "code", "process"]
CroSeverity = Literal["high", "medium", "low"]
ShopifyMigrationRecommendation = Literal["aanbevolen", "overwegen", "niet-nu", "af-te-raden", "niet-van-toepassing"]
MigrationComplexity = Literal["laag", "middel", "hoog"]
SpfStatus = Literal["valid", "missing", "misconfigured"]
DmarcPolicy = Literal["none", "quarantine", "reject", "missing"]
MetaCapiStatus = Literal["detected", "browser-only", "absent"]
AttributionLossRisk = Literal["low", "medium", "high"]
MerchantReadyEstimate = Literal["ready", "partial", "not-ready"]
WwwRedirectStatus = Literal["www-to-apex", "apex-to-www", "inconsistent"]


class PlatformArchitecture(BaseModel):
    detected_platform: str | None = None
    detection_confidence: DetectionConfidence | None = None
    detection_evidence: str | None = None
    hosting: str | None = None
    hosting_detection_evidence: str | None = None
    cdn_detected: str | None = None
    cdn_evidence: str | None = None
    server_location: str | None = None
    theme_or_framework: str | None = None
    architecture_type: ArchitectureType | None = None
    architecture_rationale: str | None = None
    recommended_architecture: ArchitectureType | None = None
    architecture_assessment: str | None = None


class MobileCWV(BaseModel):
    lcp_ms: float | None = None
    lcp_rating: Rating | None = None
    inp_ms: float | None = None
    inp_rating: Rating | None = None
    cls: float | None = None
    cls_rating: Rating | None = None
    fcp_ms: float | None = None
    ttfb_ms: float | None = None


class LighthouseScores(BaseModel):
    performance: int | None = None
    accessibility: int | None = None
    best_practices: int | None = None
    seo: int | None = None


class Performance(BaseModel):
    mobile: MobileCWV | None = None
    desktop_lcp_ms: float | None = None
    lighthouse: LighthouseScores | None = None  # from the MOBILE PageSpeed run
    desktop_lighthouse: LighthouseScores | None = None  # from the separate DESKTOP run
    tbt_ms: float | None = None
    speed_index_ms: float | None = None
    tti_ms: float | None = None
    render_blocking_resources: list[str] = []
    large_images_uncompressed: list[str] = []
    unused_javascript_kb: float | None = None
    total_page_weight_kb: float | None = None
    number_of_requests: int | None = None
    # Everything above is measured on the homepage — commercially the least relevant
    # page. This is the one PSI run (mobile) on an actual revenue page: a PDP if one was
    # scraped, else a collection page.
    money_page_url: str | None = None
    money_page_type: Literal["pdp", "collection"] | None = None
    money_page_lcp_ms: float | None = None
    # CrUX returns real-user field data per-URL, not just per-origin — "field" when
    # PSI had enough real-user traffic for this exact page to report it, "lab" when it
    # fell back to the simulated Lighthouse run (common for lower-traffic pages).
    money_page_lcp_source: Literal["field", "lab"] | None = None
    money_page_lighthouse: LighthouseScores | None = None
    notes: str | None = None


class DetectedScript(BaseModel):
    name: str
    domain: str | None = None
    purpose: str | None = None
    size_kb: float | None = None
    blocking_time_ms: float | None = None
    necessity: Necessity | None = None
    monthly_cost_eur: float | None = None
    recommendation: str | None = None


class ThirdPartyScripts(BaseModel):
    total_third_party_domains: int | None = None
    total_third_party_kb: float | None = None
    total_third_party_blocking_ms: float | None = None
    detected_scripts: list[DetectedScript] = []
    dangerous_patterns: list[str] = []
    notes: str | None = None


class TrackingDataQuality(BaseModel):
    analytics_stack: str | None = None
    detection_evidence: str | None = None
    pixels_health: HealthStatus | None = None
    capi_status: HealthStatus | None = None
    consent_mode_status: ConsentModeStatus | None = None
    cmp_provider: str | None = None
    est_attribution_loss_percent: float | None = None
    attribution_loss_confidence: str = "outside-only-estimate"
    server_side_tagging: ServerSideTagging | None = None
    duplicate_tracking_detected: bool | None = None
    notes: str | None = None


class ObservedFriction(BaseModel):
    step: str
    issue: str
    est_impact: str | None = None


class CheckoutFlow(BaseModel):
    # "ok" = probe reached a checkout-like page; "unreachable" = it didn't (redirect,
    # 404, exception — common on Shopify where checkout needs items in cart or lives on
    # a separate domain). The AI skills already gate on this field name; it used to only
    # exist ad-hoc in the AI payload builder, not on the schema itself.
    probe_status: Literal["ok", "unreachable"] | None = None
    tested_as_mobile: bool | None = None
    fields_in_address_form: int | None = None
    guest_checkout_available: bool | None = None
    payment_methods_order: list[str] = []
    express_checkout_methods: list[str] = []
    redirects_before_payment: int | None = None
    errors_encountered: list[str] = []
    total_checkout_time_seconds: float | None = None
    observed_friction: list[ObservedFriction] = []
    post_purchase_observations: str | None = None
    notes: str | None = None


class OwnedChannels(BaseModel):
    # Email/SMS *flow* observability (welcome, abandoned cart, post-purchase, win-back,
    # and the revenue % they drive) requires inbox or ESP-account access — structurally
    # impossible outside-only, not "not yet implemented". Those fields used to ship as
    # permanent nulls next to a hardcoded 30% benchmark; dropped rather than shipping
    # dead placeholders forever.
    esp_detected: str | None = None
    esp_detection_evidence: str | None = None
    newsletter_signup_tested: bool | None = None
    sms_active: bool | None = None
    notes: str | None = None


class SeoHealth(BaseModel):
    organic_traffic_trend: TrafficTrend | None = None
    organic_traffic_source: str | None = None
    branded_vs_nonbranded_ratio: str | None = None
    has_schema_markup: bool | None = None
    schema_issues: str | None = None
    programmatic_pages_detected: bool | None = None
    programmatic_quality: str | None = None
    hreflang_setup: HreflangSetup | None = None
    notes: str | None = None


class SecurityCompliance(BaseModel):
    ssl_status: SslStatus | None = None
    ssl_details: str | None = None
    cookie_banner_behavior: str | None = None
    gdpr_concerns: list[str] = []
    pci_compliance: PciStatus | None = None
    notes: str | None = None


class CostBreakdownRow(BaseModel):
    category: str
    current_tool: str | None = None
    current_cost: float | None = None
    recommended_tool: str | None = None
    recommended_cost: float | None = None
    savings: float | None = None


class CostAnalysis(BaseModel):
    current_monthly_app_cost_eur: float | None = None
    recommended_monthly_app_cost_eur: float | None = None
    est_monthly_savings_eur: float | None = None
    cost_breakdown: list[CostBreakdownRow] = []
    notes: str | None = None


class CroObservation(BaseModel):
    page: str
    observation: str
    severity: CroSeverity
    est_impact: str | None = None


class AiSkillInsight(BaseModel):
    skill: str
    summary: str
    top_actions: list[str] = []
    signals_used: list[str] = []
    observations: list[CroObservation] = []


class RoadmapPhase(BaseModel):
    phase: int
    name: str
    timeframe: str
    objective: str
    actions: list[str] = []
    expected_outcome: str
    est_monthly_revenue_impact_eur: float | None = None
    dependencies: list[str] = []


class StrategicRoadmap(BaseModel):
    skill: str = "roadmap"
    executive_summary: str
    north_star_metric: str
    top_priorities: list[str] = []
    quick_wins: list[str] = []
    phases: list[RoadmapPhase] = []
    total_timeline: str | None = None
    signals_used: list[str] = []


class AiAnalysis(BaseModel):
    cro: AiSkillInsight | None = None
    deliverability: AiSkillInsight | None = None
    tech_architecture: AiSkillInsight | None = None
    shopify_migration: ShopifyMigrationInsight | None = None
    ad_bounce_revenue: AiSkillInsight | None = None
    bloat: AiBloatInsight | None = None
    roadmap: StrategicRoadmap | None = None
    cross_section_thesis: str | None = None


class SeRankingTraffic(BaseModel):
    domain: str
    monthly_organic_sessions: int = 0
    monthly_paid_sessions: int = 0
    organic_keywords_count: int = 0
    paid_keywords_count: int = 0
    est_organic_traffic_value_usd: float = 0.0
    raw_response: dict | None = None


class CompetitorBenchmark(BaseModel):
    domain: str
    avg_keyword_position: float | None = None
    organic_keywords_count: int | None = None
    est_organic_traffic_value_usd: float | None = None
    intersecting_keywords: int | None = None


class CompetitorBenchmarkReport(BaseModel):
    """Via DataForSEO Labs (not SE Ranking — the account configured for this app
    doesn't have access to SE Ranking's domain-overview endpoint). Real per-call cost,
    so this is cached on the audit row like SE Ranking traffic is."""
    store_domain: str
    store_organic_keywords_count: int | None = None
    store_est_organic_traffic_value_usd: float | None = None
    competitors: list[CompetitorBenchmark] = []
    location_code: int
    language_code: str
    data_source: Literal["dataforseo"] = "dataforseo"
    notes: str | None = None


class AdTrafficImpact(BaseModel):
    est_post_click_bounce_pct: float | None = None
    bounce_baseline_pct: float = 45.0
    est_drop_off_per_1000_clicks: int | None = None
    est_monthly_lost_revenue_eur_low: float | None = None
    est_monthly_lost_revenue_eur_high: float | None = None
    est_wasted_ad_spend_pct: float | None = None
    bounce_drivers: list[str] = []
    methodology_note: str | None = None
    data_source: Literal["measured", "heuristic"] = "heuristic"


MetricStatus = Literal["good", "warning", "critical", "not-measured"]

# --- Funnel model (analyzers/funnel.py) --------------------------------------------
# Replaces the old `scale = monthly_revenue / 9_000` mechanism: every revenue-leak
# euro figure is now `funnel.monthly_revenue_eur * exposure_share * relative_uplift`,
# where `monthly_revenue_eur` comes from the funnel (sessions x cr x aov), not from
# the operator-supplied revenue figure alone.
Confidence = Literal["high", "medium", "low"]
FunnelStage = Literal["session", "product_view", "add_to_cart", "reach_checkout", "purchase"]
MetricKind = Literal["revenue", "cost", "diagnostic", "restatement"]
InputSource = Literal["operator", "seranking", "derived", "benchmark"]


class FunnelStageModel(BaseModel):
    stage: FunnelStage
    entering: float
    exit_rate: float
    exit_rate_source: Literal["benchmark", "calibrated", "measured"] = "benchmark"
    citation: str | None = None


class FunnelModel(BaseModel):
    monthly_sessions: float
    conversion_rate: float
    aov_eur: float
    monthly_revenue_eur: float  # sessions x cr x aov — authoritative for all loss math
    monthly_purchases: float
    monthly_ad_spend_eur: float
    mobile_share: float = 0.70
    paid_share: float = 0.30
    stages: list[FunnelStageModel] = []
    calibration_factor: float = 1.0
    sessions_source: InputSource = "benchmark"
    cr_source: InputSource = "benchmark"
    aov_source: InputSource = "benchmark"
    ad_spend_source: InputSource = "benchmark"
    operator_monthly_revenue_eur: float | None = None  # context only, never used for loss math
    data_source: Literal["measured", "heuristic"] = "heuristic"
    methodology_note: str | None = None


class DataConflict(BaseModel):
    kind: Literal["revenue_vs_funnel", "ad_spend_vs_revenue"]
    operator_value_eur: float
    model_value_eur: float
    ratio: float
    severity: Literal["warning", "critical"] = "warning"
    message_nl: str


class ModelWarning(BaseModel):
    kind: Literal["stage_ceiling_bound", "global_ceiling_bound", "duplicate_finding", "negative_payback"]
    detail: str


class RevenueLeakMetric(BaseModel):
    metric: str
    what_we_measure: str
    priority: Literal["critical", "high", "medium", "low"]
    monthly_loss_eur: float | None = None
    annual_loss_eur: float | None = None
    calculation_note: str
    signal: str | None = None
    status: MetricStatus = "not-measured"
    # --- funnel-model additions — all optional so v1 jsonb rows still parse ---
    monthly_loss_eur_low: float | None = None
    monthly_loss_eur_high: float | None = None
    annual_loss_eur_low: float | None = None
    annual_loss_eur_high: float | None = None
    finding_id: str | None = None
    funnel_stage: FunnelStage | None = None
    exposure_share: float | None = None
    uplift_low: float | None = None
    uplift_high: float | None = None
    confidence: Confidence = "medium"
    kind: MetricKind = "revenue"
    basis: str | None = None
    citation: str | None = None
    verify_manually: bool = False
    pages_affected: list[str] = []


class CeoTriggerKpi(BaseModel):
    category: str
    kpi: str
    what_ceo_sees: str
    benchmark: str | None = None
    alarm_signal: str
    real_meaning: str
    tradual_pitch: str
    tradual_solution: str
    triggered: bool = False


class RoiCalculation(BaseModel):
    monthly_leak_eur: float
    annual_leak_eur: float
    stack_rebuild_cost_eur: float = 35000.0
    payback_months: float | None = None
    year_one_net_return_eur: float
    # --- funnel-model additions ---
    monthly_leak_eur_low: float | None = None
    monthly_leak_eur_high: float | None = None
    annual_leak_eur_low: float | None = None
    annual_leak_eur_high: float | None = None
    payback_months_best: float | None = None
    payback_months_worst: float | None = None
    year_one_net_return_eur_low: float | None = None
    year_one_net_return_eur_high: float | None = None
    pays_back_within_12_months: bool | None = None


class RevenueLeakLayer(BaseModel):
    layer: int
    name: str
    core_question: str
    est_monthly_loss_eur: float | None = None
    est_annual_loss_eur: float | None = None
    metric_count: int = 0
    leads_to: str
    key_signals: list[str] = []
    metrics: list[RevenueLeakMetric] = []
    summary: str | None = None
    good_signals: list[str] = []
    improvement_signals: list[str] = []
    readiness_score: int | None = None
    # --- funnel-model additions ---
    est_monthly_loss_eur_low: float | None = None
    est_monthly_loss_eur_high: float | None = None
    est_annual_loss_eur_low: float | None = None
    est_annual_loss_eur_high: float | None = None
    kind: Literal["revenue", "cost", "diagnostic", "restatement", "readiness"] = "revenue"
    unpriced_finding_count: int = 0


class RevenueLeakReport(BaseModel):
    layers: list[RevenueLeakLayer] = []
    total_monthly_loss_eur: float | None = None
    total_annual_loss_eur: float | None = None
    direct_monthly_loss_eur: float | None = None
    direct_annual_loss_eur: float | None = None
    efficiency_monthly_uplift_eur: float | None = None
    efficiency_annual_uplift_eur: float | None = None
    methodology_note: str | None = None
    ceo_triggers: list[CeoTriggerKpi] = []
    roi: RoiCalculation | None = None
    data_source: Literal["measured", "heuristic"] = "heuristic"
    # --- funnel-model additions — all optional; absent/None means a pre-rewrite (v1)
    # report, which the frontend renders via the legacy path ---
    funnel: FunnelModel | None = None
    data_conflicts: list[DataConflict] = []
    model_warnings: list[ModelWarning] = []
    total_monthly_loss_eur_low: float | None = None
    total_monthly_loss_eur_high: float | None = None
    total_annual_loss_eur_low: float | None = None
    total_annual_loss_eur_high: float | None = None
    cost_monthly_eur: float | None = None
    leak_share_of_revenue_low: float | None = None
    leak_share_of_revenue_high: float | None = None
    model_version: str | None = None  # None == pre-rewrite report; new reports set "2.0"


class ShopifyMigrationInsight(BaseModel):
    skill: str = "shopify_migration"
    summary: str
    recommendation: ShopifyMigrationRecommendation
    rationale: str
    migration_complexity: MigrationComplexity | None = None
    estimated_timeline: str | None = None
    key_wins: list[str] = []
    key_risks: list[str] = []
    top_actions: list[str] = []
    signals_used: list[str] = []


class BloatItem(BaseModel):
    item: str
    category: BloatCategory
    reason: str | None = None
    est_savings_eur: float | None = None
    est_performance_gain_ms: float | None = None


BloatConfidence = Literal["high", "medium", "low"]


class AiBloatCandidate(BaseModel):
    item: str
    category: BloatCategory
    reason: str
    est_savings_eur: float | None = None
    est_performance_gain_ms: float | None = None
    confidence: BloatConfidence = "medium"


class AiBloatInsight(BaseModel):
    skill: str = "bloat"
    summary: str
    top_actions: list[str] = []
    signals_used: list[str] = []
    candidates: list[AiBloatCandidate] = []


class DnsEmailHealth(BaseModel):
    spf_record: str | None = None
    spf_status: SpfStatus | None = None
    dmarc_record: str | None = None
    dmarc_policy: DmarcPolicy | None = None
    dkim_selectors_found: list[str] = []
    mx_provider: str | None = None
    mx_evidence: str | None = None
    risk_summary: str | None = None


class DomainHealth(BaseModel):
    hsts_enabled: bool | None = None
    hsts_max_age_days: int | None = None
    www_redirect_status: WwwRedirectStatus | None = None
    http_to_https_forced: bool | None = None
    ipv6_enabled: bool | None = None
    redirect_chain_length: int | None = None
    evidence: str | None = None


class RichResultsHealth(BaseModel):
    schemas_detected: list[str] = []
    has_product_schema: bool | None = None
    has_aggregate_rating: bool | None = None
    has_breadcrumb: bool | None = None
    has_faq: bool | None = None
    pdp_sampled_url: str | None = None
    recommendations: list[str] = []


class ServerSideTracking(BaseModel):
    sgtm_detected: bool | None = None
    sgtm_endpoint: str | None = None
    meta_capi_status: MetaCapiStatus | None = None
    google_enhanced_conv_status: str | None = None
    tiktok_capi_status: str | None = None
    attribution_loss_risk: AttributionLossRisk | None = None


class AccessibilityHealth(BaseModel):
    lighthouse_score: int | None = None
    lang_attribute_set: bool | None = None
    viewport_meta_set: bool | None = None
    img_alt_coverage_pct: float | None = None
    landmarks_present: list[str] = []
    eu_eaa_risk_summary: str | None = None


class ProductFeedHealth(BaseModel):
    platform_feed_endpoint: str | None = None
    feed_endpoint_reachable: bool | None = None
    og_product_tags_present: bool | None = None
    jsonld_product_complete: bool | None = None
    missing_fields: list[str] = []
    google_merchant_ready_estimate: MerchantReadyEstimate | None = None


class ShopifyAppsHealth(BaseModel):
    """Real Shopify app detection via app-extension script UUIDs
    (cdn.shopify.com/extensions/<uuid>/...) — distinct from third_party_scripts, which
    counts *domains* (trackers, embeds, fonts) and isn't an app signal at all. App names
    aren't resolvable from a UUID without Shopify's non-public Admin API, so this reports
    counts/ids, not vendor names."""
    app_extension_count: int | None = None
    app_extension_ids: list[str] = []
    evidence: str | None = None
    notes: str | None = None


class ShopifyCatalogHealth(BaseModel):
    """From Shopify's public /products.json and /collections.json endpoints — a sample,
    not a guaranteed full-catalog count (capped at one page of up to 250 products)."""
    detected: bool | None = None
    product_count_sampled: int | None = None
    products_out_of_stock: int | None = None
    out_of_stock_ratio_pct: float | None = None
    products_missing_images: int | None = None
    products_missing_description: int | None = None
    collection_count_sampled: int | None = None
    theme_name: str | None = None
    theme_id: int | None = None
    evidence: str | None = None


class VendorDetection(BaseModel):
    name: str
    confidence: DetectionConfidence
    evidence: str | None = None


class EuComplianceHealth(BaseModel):
    """Heuristic signals only — NOT a legal compliance verdict. Omnibus (price-history
    disclosure on discounts) and GPSR (responsible-person/manufacturer disclosure) both
    depend on exact page content, product category, and phrasing that a scan can't fully
    verify. Absence of a detected signal means "not found in what we scraped", not
    "missing" — never present this as legal advice."""
    pdp_sampled_url: str | None = None
    has_strikethrough_price: bool | None = None
    has_lowest_price_disclosure: bool | None = None
    omnibus_risk_signal: bool | None = None
    gpsr_responsible_person_mentioned: bool | None = None
    evidence: str | None = None
    notes: str | None = None


class RetentionHealth(BaseModel):
    """Repeat-purchase infrastructure: subscriptions, loyalty/points programs, and
    bundle/upsell tooling. Pure vendor detection — no revenue-impact estimate, since
    repeat-rate impact depends on program design and adoption, neither of which is
    visible from outside."""
    subscription_detected: list[VendorDetection] = []
    loyalty_detected: list[VendorDetection] = []
    bundling_detected: list[VendorDetection] = []
    evidence: str | None = None


class SiteSearchHealth(BaseModel):
    provider_detected: str | None = None
    detected_vendors: list[VendorDetection] = []
    native_search_present: bool | None = None
    evidence: str | None = None


class ShippingHealth(BaseModel):
    providers_detected: list[str] = []
    detected_vendors: list[VendorDetection] = []
    evidence: str | None = None


class ReturnsHealth(BaseModel):
    providers_detected: list[str] = []
    detected_vendors: list[VendorDetection] = []
    returns_portal_url: str | None = None
    evidence: str | None = None


class MultiRegionHealth(BaseModel):
    currency_switcher_detected: bool | None = None
    currencies_detected: list[str] = []
    hreflang_count: int | None = None
    vary_accept_language: bool | None = None
    geo_redirect_detected: bool | None = None
    evidence: str | None = None


class MarketplacePresence(BaseModel):
    platforms_detected: list[str] = []
    review_platforms_detected: list[str] = []
    evidence: str | None = None


class DetectedStack(BaseModel):
    """Pure vendor/signal detection with no benchmark, cost, or action attached — these
    five used to be separate top-level report sections, which made five thin signals
    read as five sections of depth. One combined block, sized to match what it is."""
    site_search: SiteSearchHealth | None = None
    shipping: ShippingHealth | None = None
    returns: ReturnsHealth | None = None
    multi_region: MultiRegionHealth | None = None
    marketplaces: MarketplacePresence | None = None


class FullAuditData(BaseModel):
    store_url: str
    company_name: str | None = None
    scan_level: ScanLevel
    industry: str | None = None
    contact_email: str | None = None
    contact_person: str | None = None
    estimated_annual_revenue_eur: float | None = None
    aov_eur: float | None = None
    monthly_sessions: int | None = None
    conversion_rate_pct: float | None = None
    monthly_ad_spend_eur: float | None = None
    intro: str | None = None
    core_thesis: str | None = None
    audit_summary: str | None = None
    biggest_tech_risk: str | None = None
    biggest_tech_opportunity: str | None = None
    est_performance_lift_percent: float | None = None
    methodology_note: str | None = None
    platform_architecture: PlatformArchitecture | None = None
    performance: Performance | None = None
    third_party_scripts: ThirdPartyScripts | None = None
    tracking_data_quality: TrackingDataQuality | None = None
    checkout_flow: CheckoutFlow | None = None
    owned_channels: OwnedChannels | None = None
    seo_health: SeoHealth | None = None
    security_compliance: SecurityCompliance | None = None
    cost_analysis: CostAnalysis | None = None
    cro_observations: list[CroObservation] = []
    bloat_what_must_go: list[BloatItem] = []
    dns_email: DnsEmailHealth | None = None
    domain_health: DomainHealth | None = None
    rich_results: RichResultsHealth | None = None
    server_side_tracking: ServerSideTracking | None = None
    accessibility: AccessibilityHealth | None = None
    product_feeds: ProductFeedHealth | None = None
    detected_stack: DetectedStack | None = None
    shopify_catalog: ShopifyCatalogHealth | None = None
    shopify_apps: ShopifyAppsHealth | None = None
    retention: RetentionHealth | None = None
    eu_compliance: EuComplianceHealth | None = None
    ad_traffic_impact: AdTrafficImpact | None = None
    revenue_leak: RevenueLeakReport | None = None
    seranking_traffic: SeRankingTraffic | None = None
    competitor_benchmark: CompetitorBenchmarkReport | None = None
    ai_analysis: AiAnalysis | None = None
    sanity_export: dict | None = None


class FullAuditRequest(BaseModel):
    store_url: str
    company_name: str | None = None
    scan_level: ScanLevel = "outside-only"
    industry: str | None = None
    contact_email: str | None = None
    contact_person: str | None = None
    estimated_annual_revenue_eur: float | None = None
    # Optional operator-supplied business inputs. When provided, these replace the
    # revenue-bucket AOV guess, the 3% benchmark CVR, and the 15%-of-revenue ad-spend
    # assumption in the revenue-leak model with the store's real numbers.
    aov_eur: float | None = None
    monthly_sessions: int | None = None
    conversion_rate_pct: float | None = None
    monthly_ad_spend_eur: float | None = None


class FullAuditCreateResponse(BaseModel):
    id: uuid.UUID
    status: AuditStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class FullAuditStatusResponse(BaseModel):
    id: uuid.UUID
    status: AuditStatus
    scan_level: ScanLevel
    store_url: str
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class FullAuditResponse(BaseModel):
    id: uuid.UUID
    status: AuditStatus
    scan_level: ScanLevel
    store_url: str
    company_name: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    data: FullAuditData | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}

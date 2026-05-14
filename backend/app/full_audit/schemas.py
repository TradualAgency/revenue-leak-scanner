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
    lighthouse: LighthouseScores | None = None
    tbt_ms: float | None = None
    speed_index_ms: float | None = None
    tti_ms: float | None = None
    render_blocking_resources: list[str] = []
    large_images_uncompressed: list[str] = []
    unused_javascript_kb: float | None = None
    total_page_weight_kb: float | None = None
    number_of_requests: int | None = None
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
    server_side_tagging: ServerSideTagging | None = None
    duplicate_tracking_detected: bool | None = None
    notes: str | None = None


class ObservedFriction(BaseModel):
    step: str
    issue: str
    est_impact: str | None = None


class CheckoutFlow(BaseModel):
    tested_as_mobile: bool | None = None
    fields_in_address_form: int | None = None
    guest_checkout_available: bool | None = None
    payment_methods_order: list[str] = []
    redirects_before_payment: int | None = None
    errors_encountered: list[str] = []
    total_checkout_time_seconds: float | None = None
    observed_friction: list[ObservedFriction] = []
    post_purchase_observations: str | None = None
    notes: str | None = None


class OwnedChannels(BaseModel):
    esp_detected: str | None = None
    esp_detection_evidence: str | None = None
    newsletter_signup_tested: bool | None = None
    welcome_flow_observed: bool | None = None
    abandoned_cart_flow_observed: bool | None = None
    post_purchase_flow_observed: bool | None = None
    win_back_flow_observed: bool | None = None
    est_email_revenue_percent: float | None = None
    benchmark_email_revenue_percent: float = 30.0
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


class AiAnalysis(BaseModel):
    cro: AiSkillInsight | None = None
    deliverability: AiSkillInsight | None = None
    tech_architecture: AiSkillInsight | None = None
    cross_section_thesis: str | None = None


class BloatItem(BaseModel):
    item: str
    category: BloatCategory
    reason: str | None = None
    est_savings_eur: float | None = None
    est_performance_gain_ms: float | None = None


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


class VendorDetection(BaseModel):
    name: str
    confidence: DetectionConfidence
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


class FullAuditData(BaseModel):
    store_url: str
    company_name: str | None = None
    scan_level: ScanLevel
    industry: str | None = None
    contact_email: str | None = None
    contact_person: str | None = None
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
    site_search: SiteSearchHealth | None = None
    shipping: ShippingHealth | None = None
    returns: ReturnsHealth | None = None
    multi_region: MultiRegionHealth | None = None
    marketplaces: MarketplacePresence | None = None
    ai_analysis: AiAnalysis | None = None


class FullAuditRequest(BaseModel):
    store_url: str
    company_name: str | None = None
    scan_level: ScanLevel = "outside-only"
    industry: str | None = None
    contact_email: str | None = None
    contact_person: str | None = None


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

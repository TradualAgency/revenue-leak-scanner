export interface LeadCreatePayload {
  email: string;
  store_url: string;
  platform: "shopify" | "woocommerce" | "other";
  monthly_revenue: number;
  monthly_traffic: number;
}

export interface LeadCreateResponse {
  lead_id: string;
  report_id: string;
  status: string;
  created_at: string;
}

export interface ReportStatusResponse {
  report_id: string;
  status: string;
  pages_discovered: number | null;
  avg_load_time_ms: number | null;
  performance_score: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface ReportSummaryResponse {
  report_id: string;
  status: string;
  performance_score: number | null;
  plugin_count: number | null;
  estimated_monthly_loss_min: number | null;
  estimated_monthly_loss_max: number | null;
  total_plugin_cost_monthly: number | null;
  avg_load_time_ms: number | null;
  excess_load_time: number | null;
  blended_loss_rate: number | null;
  pages_scanned: string[] | null;
  plugins: DetectedPlugin[] | null;
  quick_wins: string[] | null;
}

export interface DetectedPlugin {
  name: string;
  slug: string;
  platform: string;
  estimated_monthly_cost: number | null;
  detection_method: string;
  confidence: string;
}

export type ScanLevel = "outside-only" | "semi" | "full-access";
export type AuditStatus = "queued" | "processing" | "ready_for_review" | "failed";

export interface FullAuditRequest {
  store_url: string;
  company_name?: string;
  scan_level?: ScanLevel;
  industry?: string;
  contact_email?: string;
  contact_person?: string;
}

export interface FullAuditCreateResponse {
  id: string;
  status: AuditStatus;
  created_at: string;
}

export interface FullAuditStatusResponse {
  id: string;
  status: AuditStatus;
  scan_level: ScanLevel;
  store_url: string;
  created_at: string;
  completed_at: string | null;
}

export interface DetectedScript {
  name: string;
  domain: string | null;
  purpose: string | null;
  size_kb: number | null;
  blocking_time_ms: number | null;
  necessity: "critical" | "useful" | "removable" | "replaceable" | null;
  monthly_cost_eur: number | null;
  recommendation: string | null;
}

export interface CostBreakdownRow {
  category: string;
  current_tool: string | null;
  current_cost: number | null;
  recommended_tool: string | null;
  recommended_cost: number | null;
  savings: number | null;
}

export interface ObservedFriction {
  step: string;
  issue: string;
  est_impact: string | null;
}

export interface CroObservation {
  page: string;
  observation: string;
  severity: "high" | "medium" | "low";
  est_impact: string | null;
}

export interface AiSkillInsight {
  skill: string;
  summary: string;
  top_actions: string[];
  signals_used: string[];
}

export interface AiAnalysis {
  cro: AiSkillInsight | null;
  deliverability: AiSkillInsight | null;
  tech_architecture: AiSkillInsight | null;
  cross_section_thesis: string | null;
}

export interface BloatItem {
  item: string;
  category: "app" | "script" | "code" | "process";
  reason: string | null;
  est_savings_eur: number | null;
  est_performance_gain_ms: number | null;
}

export interface VendorDetection {
  name: string;
  confidence: "confirmed" | "probable" | "unknown";
  evidence: string | null;
}

export interface DnsEmailHealth {
  spf_record: string | null;
  spf_status: "valid" | "missing" | "misconfigured" | null;
  dmarc_record: string | null;
  dmarc_policy: "none" | "quarantine" | "reject" | "missing" | null;
  dkim_selectors_found: string[];
  mx_provider: string | null;
  mx_evidence: string | null;
  risk_summary: string | null;
}

export interface DomainHealth {
  hsts_enabled: boolean | null;
  hsts_max_age_days: number | null;
  www_redirect_status: "www-to-apex" | "apex-to-www" | "inconsistent" | null;
  http_to_https_forced: boolean | null;
  ipv6_enabled: boolean | null;
  redirect_chain_length: number | null;
  evidence: string | null;
}

export interface RichResultsHealth {
  schemas_detected: string[];
  has_product_schema: boolean | null;
  has_aggregate_rating: boolean | null;
  has_breadcrumb: boolean | null;
  has_faq: boolean | null;
  pdp_sampled_url: string | null;
  recommendations: string[];
}

export interface ServerSideTracking {
  sgtm_detected: boolean | null;
  sgtm_endpoint: string | null;
  meta_capi_status: "detected" | "browser-only" | "absent" | null;
  google_enhanced_conv_status: string | null;
  tiktok_capi_status: string | null;
  attribution_loss_risk: "low" | "medium" | "high" | null;
}

export interface AccessibilityHealth {
  lighthouse_score: number | null;
  lang_attribute_set: boolean | null;
  viewport_meta_set: boolean | null;
  img_alt_coverage_pct: number | null;
  landmarks_present: string[];
  eu_eaa_risk_summary: string | null;
}

export interface ProductFeedHealth {
  platform_feed_endpoint: string | null;
  feed_endpoint_reachable: boolean | null;
  og_product_tags_present: boolean | null;
  jsonld_product_complete: boolean | null;
  missing_fields: string[];
  google_merchant_ready_estimate: "ready" | "partial" | "not-ready" | null;
}

export interface SiteSearchHealth {
  provider_detected: string | null;
  detected_vendors: VendorDetection[];
  native_search_present: boolean | null;
  evidence: string | null;
}

export interface ShippingHealth {
  providers_detected: string[];
  detected_vendors: VendorDetection[];
  evidence: string | null;
}

export interface ReturnsHealth {
  providers_detected: string[];
  detected_vendors: VendorDetection[];
  returns_portal_url: string | null;
  evidence: string | null;
}

export interface MultiRegionHealth {
  currency_switcher_detected: boolean | null;
  currencies_detected: string[];
  hreflang_count: number | null;
  vary_accept_language: boolean | null;
  geo_redirect_detected: boolean | null;
  evidence: string | null;
}

export interface MarketplacePresence {
  platforms_detected: string[];
  review_platforms_detected: string[];
  evidence: string | null;
}

export interface FullAuditData {
  store_url: string;
  company_name: string | null;
  scan_level: ScanLevel;
  industry: string | null;
  core_thesis: string | null;
  audit_summary: string | null;
  biggest_tech_risk: string | null;
  biggest_tech_opportunity: string | null;
  est_performance_lift_percent: number | null;
  methodology_note: string | null;
  platform_architecture: {
    detected_platform: string | null;
    detection_confidence: string | null;
    detection_evidence: string | null;
    hosting: string | null;
    cdn_detected: string | null;
    architecture_type: string | null;
    recommended_architecture: string | null;
    architecture_assessment: string | null;
  } | null;
  performance: {
    mobile: {
      lcp_ms: number | null;
      lcp_rating: string | null;
      inp_ms: number | null;
      inp_rating: string | null;
      cls: number | null;
      cls_rating: string | null;
      fcp_ms: number | null;
      ttfb_ms: number | null;
    } | null;
    desktop_lcp_ms: number | null;
    lighthouse: {
      performance: number | null;
      accessibility: number | null;
      best_practices: number | null;
      seo: number | null;
    } | null;
    tbt_ms: number | null;
    speed_index_ms: number | null;
    tti_ms: number | null;
    render_blocking_resources: string[];
    large_images_uncompressed: string[];
    unused_javascript_kb: number | null;
    total_page_weight_kb: number | null;
    number_of_requests: number | null;
    notes: string | null;
  } | null;
  third_party_scripts: {
    total_third_party_domains: number | null;
    total_third_party_kb: number | null;
    total_third_party_blocking_ms: number | null;
    detected_scripts: DetectedScript[];
    dangerous_patterns: string[];
    notes: string | null;
  } | null;
  tracking_data_quality: {
    analytics_stack: string | null;
    pixels_health: string | null;
    consent_mode_status: string | null;
    cmp_provider: string | null;
    est_attribution_loss_percent: number | null;
    server_side_tagging: string | null;
    duplicate_tracking_detected: boolean | null;
    notes: string | null;
  } | null;
  checkout_flow: {
    fields_in_address_form: number | null;
    guest_checkout_available: boolean | null;
    payment_methods_order: string[];
    redirects_before_payment: number | null;
    errors_encountered: string[];
    total_checkout_time_seconds: number | null;
    observed_friction: ObservedFriction[];
    notes: string | null;
  } | null;
  owned_channels: {
    esp_detected: string | null;
    esp_detection_evidence: string | null;
    newsletter_signup_tested: boolean | null;
    sms_active: boolean | null;
    est_email_revenue_percent: number | null;
    benchmark_email_revenue_percent: number;
    notes: string | null;
  } | null;
  seo_health: {
    has_schema_markup: boolean | null;
    schema_issues: string | null;
    programmatic_pages_detected: boolean | null;
    programmatic_quality: string | null;
    hreflang_setup: string | null;
    notes: string | null;
  } | null;
  security_compliance: {
    ssl_status: string | null;
    ssl_details: string | null;
    cookie_banner_behavior: string | null;
    gdpr_concerns: string[];
    pci_compliance: string | null;
  } | null;
  cost_analysis: {
    current_monthly_app_cost_eur: number | null;
    recommended_monthly_app_cost_eur: number | null;
    est_monthly_savings_eur: number | null;
    cost_breakdown: CostBreakdownRow[];
  } | null;
  cro_observations: CroObservation[];
  bloat_what_must_go: BloatItem[];
  dns_email: DnsEmailHealth | null;
  domain_health: DomainHealth | null;
  rich_results: RichResultsHealth | null;
  server_side_tracking: ServerSideTracking | null;
  accessibility: AccessibilityHealth | null;
  product_feeds: ProductFeedHealth | null;
  site_search: SiteSearchHealth | null;
  shipping: ShippingHealth | null;
  returns: ReturnsHealth | null;
  multi_region: MultiRegionHealth | null;
  marketplaces: MarketplacePresence | null;
  ai_analysis: AiAnalysis | null;
}

export interface FullAuditResponse {
  id: string;
  status: AuditStatus;
  scan_level: ScanLevel;
  store_url: string;
  company_name: string | null;
  created_at: string;
  completed_at: string | null;
  data: FullAuditData | null;
  error_message: string | null;
}

export interface ReportFullResponse {
  report_id: string;
  lead_id: string;
  status: string;
  pages_discovered: number | null;
  avg_load_time_ms: number | null;
  performance_score: number | null;
  estimated_monthly_loss: number | null;
  total_plugin_cost_monthly: number | null;
  plugins: DetectedPlugin[];
  report_data: Record<string, unknown> | null;
  created_at: string;
  completed_at: string | null;
}

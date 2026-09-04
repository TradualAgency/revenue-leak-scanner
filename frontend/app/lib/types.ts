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
  speed_source: string | null;
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
  estimated_annual_revenue_eur?: number;
  aov_eur?: number;
  monthly_sessions?: number;
  conversion_rate_pct?: number;
  monthly_ad_spend_eur?: number;
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

export interface ShopifyMigrationInsight {
  skill: string;
  summary: string;
  recommendation: "aanbevolen" | "overwegen" | "niet-nu" | "af-te-raden" | "niet-van-toepassing";
  rationale: string;
  migration_complexity: "laag" | "middel" | "hoog" | null;
  estimated_timeline: string | null;
  key_wins: string[];
  key_risks: string[];
  top_actions: string[];
  signals_used: string[];
}

export interface AiBloatCandidate {
  item: string;
  category: "app" | "script" | "code" | "process";
  reason: string;
  est_savings_eur: number | null;
  est_performance_gain_ms: number | null;
  confidence: "high" | "medium" | "low";
}

export interface AiBloatInsight {
  skill: string;
  summary: string;
  top_actions: string[];
  signals_used: string[];
  candidates: AiBloatCandidate[];
}

export interface AiAnalysis {
  cro: AiSkillInsight | null;
  deliverability: AiSkillInsight | null;
  tech_architecture: AiSkillInsight | null;
  shopify_migration: ShopifyMigrationInsight | null;
  ad_bounce_revenue: AiSkillInsight | null;
  bloat: AiBloatInsight | null;
  cross_section_thesis: string | null;
}

export type DataSource = "measured" | "heuristic";

export interface SeRankingTraffic {
  domain: string;
  monthly_organic_sessions: number;
  monthly_paid_sessions: number;
  organic_keywords_count: number;
  paid_keywords_count: number;
  est_organic_traffic_value_usd: number;
}

export interface CompetitorBenchmark {
  domain: string;
  avg_keyword_position: number | null;
  organic_keywords_count: number | null;
  est_organic_traffic_value_usd: number | null;
  intersecting_keywords: number | null;
}

export interface CompetitorBenchmarkReport {
  store_domain: string;
  store_organic_keywords_count: number | null;
  store_est_organic_traffic_value_usd: number | null;
  competitors: CompetitorBenchmark[];
  location_code: number;
  language_code: string;
  data_source: "dataforseo";
  notes: string | null;
}

export interface AdTrafficImpact {
  est_post_click_bounce_pct: number | null;
  bounce_baseline_pct: number;
  est_drop_off_per_1000_clicks: number | null;
  est_monthly_lost_revenue_eur_low: number | null;
  est_monthly_lost_revenue_eur_high: number | null;
  est_wasted_ad_spend_pct: number | null;
  bounce_drivers: string[];
  methodology_note: string | null;
  data_source: DataSource;
}

export type MetricStatus = "good" | "warning" | "critical" | "not-measured";

// --- Funnel model additions ---------------------------------------------------------
// `monthly_revenue_eur` (sessions x cr x aov) is what every revenue-leak euro figure
// is computed against — NOT `estimated_annual_revenue_eur` from the audit form, which
// is kept only as context and can disagree with the funnel (see DataConflict).
export type Confidence = "high" | "medium" | "low";
export type FunnelStage = "session" | "product_view" | "add_to_cart" | "reach_checkout" | "purchase";
export type MetricKind = "revenue" | "cost" | "diagnostic" | "restatement";
export type InputSource = "operator" | "seranking" | "derived" | "benchmark";

export interface FunnelStageModel {
  stage: FunnelStage;
  entering: number;
  exit_rate: number;
  exit_rate_source: "benchmark" | "calibrated" | "measured";
  citation: string | null;
}

export interface FunnelModel {
  monthly_sessions: number;
  conversion_rate: number;
  aov_eur: number;
  monthly_revenue_eur: number;
  monthly_purchases: number;
  monthly_ad_spend_eur: number;
  mobile_share: number;
  paid_share: number;
  stages: FunnelStageModel[];
  calibration_factor: number;
  sessions_source: InputSource;
  cr_source: InputSource;
  aov_source: InputSource;
  ad_spend_source: InputSource;
  operator_monthly_revenue_eur: number | null;
  data_source: DataSource;
  methodology_note: string | null;
}

export interface DataConflict {
  kind: "revenue_vs_funnel" | "ad_spend_vs_revenue";
  operator_value_eur: number;
  model_value_eur: number;
  ratio: number;
  severity: "warning" | "critical";
  message_nl: string;
}

export interface ModelWarning {
  kind: "stage_ceiling_bound" | "global_ceiling_bound" | "duplicate_finding" | "negative_payback";
  detail: string;
}

export interface RevenueLeakMetric {
  metric: string;
  what_we_measure: string;
  priority: "critical" | "high" | "medium" | "low";
  monthly_loss_eur: number | null;
  annual_loss_eur: number | null;
  calculation_note: string;
  signal: string | null;
  status: MetricStatus;
  // present only on reports computed by the funnel-model rewrite (model_version set)
  monthly_loss_eur_low?: number | null;
  monthly_loss_eur_high?: number | null;
  annual_loss_eur_low?: number | null;
  annual_loss_eur_high?: number | null;
  finding_id?: string | null;
  funnel_stage?: FunnelStage | null;
  exposure_share?: number | null;
  uplift_low?: number | null;
  uplift_high?: number | null;
  confidence?: Confidence;
  kind?: MetricKind;
  basis?: string | null;
  citation?: string | null;
  verify_manually?: boolean;
  pages_affected?: string[];
}

export interface CeoTriggerKpi {
  category: string;
  kpi: string;
  what_ceo_sees: string;
  benchmark: string | null;
  alarm_signal: string;
  real_meaning: string;
  tradual_pitch: string;
  tradual_solution: string;
  triggered: boolean;
}

export interface RoiCalculation {
  monthly_leak_eur: number;
  annual_leak_eur: number;
  stack_rebuild_cost_eur: number;
  payback_months: number | null;
  year_one_net_return_eur: number;
  monthly_leak_eur_low?: number | null;
  monthly_leak_eur_high?: number | null;
  annual_leak_eur_low?: number | null;
  annual_leak_eur_high?: number | null;
  payback_months_best?: number | null;
  payback_months_worst?: number | null;
  year_one_net_return_eur_low?: number | null;
  year_one_net_return_eur_high?: number | null;
  pays_back_within_12_months?: boolean | null;
}

export interface RevenueLeakLayer {
  layer: number;
  name: string;
  core_question: string;
  est_monthly_loss_eur: number | null;
  est_annual_loss_eur: number | null;
  metric_count: number;
  leads_to: string;
  key_signals: string[];
  metrics: RevenueLeakMetric[];
  summary: string | null;
  good_signals: string[];
  improvement_signals: string[];
  readiness_score: number | null;
  est_monthly_loss_eur_low?: number | null;
  est_monthly_loss_eur_high?: number | null;
  est_annual_loss_eur_low?: number | null;
  est_annual_loss_eur_high?: number | null;
  kind?: "revenue" | "cost" | "diagnostic" | "restatement" | "readiness";
  unpriced_finding_count?: number;
}

export interface RevenueLeakReport {
  layers: RevenueLeakLayer[];
  total_monthly_loss_eur: number | null;
  total_annual_loss_eur: number | null;
  direct_monthly_loss_eur: number | null;
  direct_annual_loss_eur: number | null;
  efficiency_monthly_uplift_eur: number | null;
  efficiency_annual_uplift_eur: number | null;
  methodology_note: string | null;
  ceo_triggers: CeoTriggerKpi[];
  roi: RoiCalculation | null;
  data_source: DataSource;
  // Present only when computed by the funnel-model rewrite. `model_version` is the
  // frontend's branch key: absent/null means a pre-rewrite (v1) report stored before
  // this schema existed — render it via the legacy single-value path, not ranges.
  model_version?: string | null;
  funnel?: FunnelModel | null;
  data_conflicts?: DataConflict[];
  model_warnings?: ModelWarning[];
  total_monthly_loss_eur_low?: number | null;
  total_monthly_loss_eur_high?: number | null;
  total_annual_loss_eur_low?: number | null;
  total_annual_loss_eur_high?: number | null;
  cost_monthly_eur?: number | null;
  leak_share_of_revenue_low?: number | null;
  leak_share_of_revenue_high?: number | null;
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

export interface RetentionHealth {
  subscription_detected: VendorDetection[];
  loyalty_detected: VendorDetection[];
  bundling_detected: VendorDetection[];
  evidence: string | null;
}

export interface ShopifyAppsHealth {
  app_extension_count: number | null;
  app_extension_ids: string[];
  evidence: string | null;
  notes: string | null;
}

export interface ShopifyCatalogHealth {
  detected: boolean | null;
  product_count_sampled: number | null;
  products_out_of_stock: number | null;
  out_of_stock_ratio_pct: number | null;
  products_missing_images: number | null;
  products_missing_description: number | null;
  collection_count_sampled: number | null;
  theme_name: string | null;
  theme_id: number | null;
  evidence: string | null;
}

export interface EuComplianceHealth {
  pdp_sampled_url: string | null;
  has_strikethrough_price: boolean | null;
  has_lowest_price_disclosure: boolean | null;
  omnibus_risk_signal: boolean | null;
  gpsr_responsible_person_mentioned: boolean | null;
  evidence: string | null;
  notes: string | null;
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
  estimated_annual_revenue_eur: number | null;
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
    desktop_lighthouse: {
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
    money_page_url: string | null;
    money_page_type: "pdp" | "collection" | null;
    money_page_lcp_ms: number | null;
    money_page_lcp_source: "field" | "lab" | null;
    money_page_lighthouse: {
      performance: number | null;
      accessibility: number | null;
      best_practices: number | null;
      seo: number | null;
    } | null;
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
    probe_status: "ok" | "unreachable" | null;
    fields_in_address_form: number | null;
    guest_checkout_available: boolean | null;
    payment_methods_order: string[];
    express_checkout_methods: string[];
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
  detected_stack: {
    site_search: SiteSearchHealth | null;
    shipping: ShippingHealth | null;
    returns: ReturnsHealth | null;
    multi_region: MultiRegionHealth | null;
    marketplaces: MarketplacePresence | null;
  } | null;
  shopify_catalog: ShopifyCatalogHealth | null;
  shopify_apps: ShopifyAppsHealth | null;
  retention: RetentionHealth | null;
  eu_compliance: EuComplianceHealth | null;
  ad_traffic_impact: AdTrafficImpact | null;
  revenue_leak: RevenueLeakReport | null;
  seranking_traffic: SeRankingTraffic | null;
  competitor_benchmark: CompetitorBenchmarkReport | null;
  ai_analysis: AiAnalysis | null;
  sanity_export: Record<string, unknown> | null;
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

// --- Competitor benchmark (marktvergelijking) --------------------------------------

export type CompetitorRunStatus =
  | "queued"
  | "discovering"
  | "measuring"
  | "scoring"
  | "ready"
  | "insufficient_data"
  | "failed";

export type CandidateClassification = "direct" | "category" | "marketplace" | "retailer" | "irrelevant" | "operator";

export interface MarketInfo {
  location_code: number;
  language_code: string;
  source: string;
  confidence: "high" | "medium" | "low";
}

export interface CandidateDomain {
  domain: string;
  discovery_source: "competitors_domain" | "serp_competitors" | "both" | "operator";
  organic_keywords_count: number | null;
  est_organic_traffic_value_usd: number | null;
  avg_keyword_position: number | null;
  intersections: number | null;
  serp_keyword_hits: number | null;
  size_ratio_to_store: number | null;
  title: string | null;
  meta_description: string | null;
  og_site_name: string | null;
  platform_guess: string | null;
  html_lang: string | null;
  enrichment_status: "ok" | "unreachable" | "skipped";
  classification: CandidateClassification | null;
  relevance_score: number | null;
  reason_nl: string | null;
  rank: number | null;
}

export interface RejectedCandidate {
  domain: string;
  reason_code:
    | "self"
    | "same_brand"
    | "blocklist"
    | "size_band"
    | "min_intersections"
    | "market_coherence"
    | "ai_excluded"
    | "enrichment_unreachable"
    | "operator_removed";
  reason_nl: string;
  category: string | null;
}

// What happened to one manually supplied domain. Reports a *decision*, never a
// measurement — measuring happens afterwards in the background, so never render these
// as "measured successfully".
export interface SeedOutcome {
  input: string;
  domain: string | null;
  status: "accepted" | "rejected" | "warning";
  code:
    | "accepted"
    | "normalized"
    | "duplicate"
    | "invalid"
    | "self"
    | "same_brand"
    | "blocklist"
    | "over_limit";
  message_nl: string;
}

export interface CompetitorCandidatesResponse {
  kept: CandidateDomain[];
  rejected: RejectedCandidate[];
  market: MarketInfo | null;
  market_note_nl: string | null;
  // `kept` is the discovery audit trail; `selected_domains` is what is actually being
  // measured. Render the latter — showing `kept` is how a removed competitor's chip
  // reappeared and how a capped-out domain looked like it had been added.
  selected_domains: string[];
  seed_domains: string[];
  seed_outcomes: SeedOutcome[];
  operator_added: string[];
  operator_removed: string[];
  measure_limit: number;
  discovery_available: boolean;
  roster: CompetitorRosterEntry[];
}

export interface CompetitorMetricValue {
  domain: string;
  value: number | null;
  available: boolean;
  unavailable_reason: string | null;
  source: string | null;
}

export interface MetricComparison {
  key: string;
  layer: number;
  label_nl: string;
  unit: "ms" | "s" | "count" | "pct" | "score" | "eur" | "bool";
  direction: "lower_is_better" | "higher_is_better";
  store_value: number | null;
  store_measured: boolean;
  competitor_values: CompetitorMetricValue[];
  median: number | null;
  best: number | null;
  best_domain: string | null;
  p25: number | null;
  store_rank: number | null;
  domains_ranked: number | null;
  store_percentile: number | null;
  gap_to_median_abs: number | null;
  gap_to_median_pct: number | null;
  measured_domains: number;
  eligible_domains: number;
  total_domains: number;
  coverage_label_nl: string;
  sufficiency: "sufficient" | "thin" | "insufficient";
  unavailable_reasons: Record<string, string>;
}

export interface LayerScore {
  layer: number;
  name_nl: string;
  relative_score: number | null;
  absolute_score: number | null;
  metrics_used: number;
  metrics_unavailable: number;
  rank_in_set: number | null;
  summary_nl: string | null;
}

export interface GapFinding {
  finding_id: string;
  layer: number;
  label_nl: string;
  store_value: number | null;
  median_value: number | null;
  best_value: number | null;
  gap_to_median_eur_low: number | null;
  gap_to_median_eur_high: number | null;
  gap_to_best_eur_low: number | null;
  gap_to_best_eur_high: number | null;
  market_is_also_below_benchmark: boolean;
  kind: "revenue" | "diagnostic";
  confidence: "high" | "medium" | "low";
  citation: string | null;
  note_nl: string | null;
}

export interface CompetitorRosterEntry {
  domain: string;
  classification: CandidateClassification | null;
  reason_nl: string | null;
  measure_status: "ok" | "partial" | "unreachable" | "timeout";
  measured_at: string | null;
  is_shopify: boolean | null;
  discovery_source: string | null;
}

export interface CompetitorBenchmarkData {
  store_domain: string;
  market: MarketInfo;
  roster: CompetitorRosterEntry[];
  comparisons: MetricComparison[];
  layer_scores: LayerScore[];
  overall_relative_score: number | null;
  gaps: GapFinding[];
  gap_to_median_monthly_eur_low: number | null;
  gap_to_median_monthly_eur_high: number | null;
  gap_to_best_monthly_eur_low: number | null;
  gap_to_best_monthly_eur_high: number | null;
  market_is_also_below_benchmark: boolean;
  manually_curated: boolean;
  // Server-side sentence explaining *how* the set was curated (added / removed / both).
  // Null when the set is purely auto-discovered. The page renders it verbatim so the
  // wording of the disclosure lives in one place.
  curation_note_nl: string | null;
  checkout_probe_included: boolean;
  methodology_note_nl: string | null;
  narrative_nl: string | null;
  generated_at: string;
}

export interface CompetitorBenchmarkCreateResponse {
  id: string;
  status: CompetitorRunStatus;
  created_at: string;
  seed_domains: string[];
  outcomes: SeedOutcome[];
}

export interface CompetitorSetUpdateResponse {
  id: string;
  status: CompetitorRunStatus;
  created_at: string;
  selected_domains: string[];
  outcomes: SeedOutcome[];
  measure_limit: number;
}

export interface CompetitorBenchmarkStatusResponse {
  id: string;
  status: CompetitorRunStatus;
  store_domain: string;
  phase_label_nl: string | null;
  measured_count: number;
  total_count: number;
  created_at: string;
  completed_at: string | null;
}

export interface CompetitorBenchmarkResponse {
  id: string;
  status: CompetitorRunStatus;
  store_domain: string;
  data: CompetitorBenchmarkData | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface CompetitorBenchmarkCreatePayload {
  full_audit_id: string;
  location_code?: number | null;
  language_code?: string | null;
  // Clamped server-side to COMPETITOR_MEASURE_LIMIT.
  max_competitors?: number | null;
  // Known competitors, measured with priority over anything discovery finds. Also the
  // only way to run a benchmark when DataForSEO is unavailable.
  seed_domains?: string[];
  include_checkout_probe?: boolean;
}

export interface CompetitorSetUpdatePayload {
  add: string[];
  remove: string[];
  location_code?: number | null;
  language_code?: string | null;
}

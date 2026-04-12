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

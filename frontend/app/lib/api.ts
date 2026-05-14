import type {
  FullAuditCreateResponse,
  FullAuditRequest,
  FullAuditResponse,
  FullAuditStatusResponse,
  LeadCreatePayload,
  LeadCreateResponse,
  ReportFullResponse,
  ReportStatusResponse,
  ReportSummaryResponse,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL || "";
const BASE = `${API_URL}/api/v1`;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function createLead(payload: LeadCreatePayload): Promise<LeadCreateResponse> {
  return request<LeadCreateResponse>("/leads", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getReportStatus(reportId: string): Promise<ReportStatusResponse> {
  return request<ReportStatusResponse>(`/reports/${reportId}/status`);
}

export function getReportSummary(reportId: string): Promise<ReportSummaryResponse> {
  return request<ReportSummaryResponse>(`/reports/${reportId}/summary`);
}

export function getFullReport(reportId: string): Promise<ReportFullResponse> {
  return request<ReportFullResponse>(`/reports/${reportId}`);
}

export function createFullAudit(payload: FullAuditRequest): Promise<FullAuditCreateResponse> {
  return request<FullAuditCreateResponse>("/full-audit", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getFullAuditStatus(auditId: string): Promise<FullAuditStatusResponse> {
  return request<FullAuditStatusResponse>(`/full-audit/${auditId}/status`);
}

export function getFullAudit(auditId: string): Promise<FullAuditResponse> {
  return request<FullAuditResponse>(`/full-audit/${auditId}`);
}

import type {
  CompetitorBenchmarkCreatePayload,
  CompetitorBenchmarkCreateResponse,
  CompetitorBenchmarkResponse,
  CompetitorBenchmarkStatusResponse,
  CompetitorCandidatesResponse,
  CompetitorSetUpdatePayload,
  CompetitorSetUpdateResponse,
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
// Only ever used by the operator-facing full-audit review page — never sent from the
// prospect-facing revenue-leak report.
const OPERATOR_API_KEY = import.meta.env.VITE_OPERATOR_API_KEY || "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers as Record<string, string> | undefined) },
  });
  if (!res.ok) {
    // FastAPI returns {"detail": ...} for every HTTPException, so unwrap it — throwing
    // the raw body meant the operator saw `{"detail":"Run is nog bezig"}` on screen.
    const raw = await res.text().catch(() => res.statusText);
    let message = raw;
    try {
      const parsed = JSON.parse(raw);
      if (typeof parsed?.detail === "string") message = parsed.detail;
    } catch {
      // not JSON — fall through to the raw body
    }
    throw new Error(message.slice(0, 300) || `HTTP ${res.status}`);
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

// Operator-only: the Sanity CMS export (contains a page password) is deliberately not
// included in getFullAudit's response. Requires VITE_OPERATOR_API_KEY to be configured;
// resolves to null if it isn't, so callers can treat this as "unavailable" rather than
// erroring the whole page.
export function getFullAuditSanityExport(auditId: string): Promise<Record<string, unknown> | null> {
  if (!OPERATOR_API_KEY) return Promise.resolve(null);
  return request<Record<string, unknown>>(`/full-audit/${auditId}/sanity-export`, {
    headers: { "X-Operator-Key": OPERATOR_API_KEY },
  }).catch(() => null);
}

// --- Competitor benchmark (marktvergelijking) --------------------------------------

export function createCompetitorBenchmark(payload: CompetitorBenchmarkCreatePayload): Promise<CompetitorBenchmarkCreateResponse> {
  return request<CompetitorBenchmarkCreateResponse>("/competitor-benchmark", {
    method: "POST",
    headers: { "X-Operator-Key": OPERATOR_API_KEY },
    body: JSON.stringify(payload),
  });
}

export function getCompetitorBenchmarkStatus(runId: string): Promise<CompetitorBenchmarkStatusResponse> {
  return request<CompetitorBenchmarkStatusResponse>(`/competitor-benchmark/${runId}/status`);
}

export function getCompetitorBenchmark(runId: string): Promise<CompetitorBenchmarkResponse> {
  return request<CompetitorBenchmarkResponse>(`/competitor-benchmark/${runId}`);
}

// Operator-only: the discovery audit trail (kept + rejected candidates with reasons)
// isn't shown on the prospect-facing page — resolves to null when the key isn't
// configured, same convention as getFullAuditSanityExport.
export function getCompetitorCandidates(runId: string): Promise<CompetitorCandidatesResponse | null> {
  if (!OPERATOR_API_KEY) return Promise.resolve(null);
  return request<CompetitorCandidatesResponse>(`/competitor-benchmark/${runId}/candidates`, {
    headers: { "X-Operator-Key": OPERATOR_API_KEY },
  }).catch(() => null);
}

// Deliberately does NOT swallow errors to null like the operator reads above — this
// is a write (it mutates which competitors are measured), and a silent failure on a
// write is a UX trap: the operator would believe an override took effect when it
// didn't.
export function updateCompetitorSet(runId: string, payload: CompetitorSetUpdatePayload): Promise<CompetitorSetUpdateResponse> {
  return request<CompetitorSetUpdateResponse>(`/competitor-benchmark/${runId}/competitors`, {
    method: "PATCH",
    headers: { "X-Operator-Key": OPERATOR_API_KEY },
    body: JSON.stringify(payload),
  });
}

export function remeasureCompetitors(runId: string, force: boolean): Promise<CompetitorBenchmarkCreateResponse> {
  return request<CompetitorBenchmarkCreateResponse>(`/competitor-benchmark/${runId}/remeasure`, {
    method: "POST",
    headers: { "X-Operator-Key": OPERATOR_API_KEY },
    body: JSON.stringify({ force }),
  });
}

import type {
  CompetitorBenchmarkCreatePayload,
  CompetitorBenchmarkCreateResponse,
  CompetitorBenchmarkResponse,
  CompetitorBenchmarkStatusResponse,
  CompetitorCandidatesResponse,
  CompetitorRunListResponse,
  CompetitorSetUpdatePayload,
  CompetitorSetUpdateResponse,
  FullAuditCreateResponse,
  FullAuditListResponse,
  FullAuditRequest,
  FullAuditResponse,
  FullAuditStatusResponse,
  LeadCreatePayload,
  LeadCreateResponse,
  ReportFullResponse,
  ReportStatusResponse,
  ReportSummaryResponse,
} from "./types";
import { clearOperatorKey, getOperatorKey } from "./operatorKey";

const API_URL = import.meta.env.VITE_API_URL || "";
const BASE = `${API_URL}/api/v1`;

/**
 * Carries the HTTP status alongside the message. Extends Error so the many
 * `err instanceof Error ? err.message : "..."` call sites keep working unchanged.
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit, isOperator = false): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers as Record<string, string> | undefined) },
  });
  if (!res.ok) {
    // A 403 on an operator call means the stored key is wrong or has been rotated.
    // Clearing it here — before any caller's `.catch(() => null)` can swallow the
    // error — is what makes every mounted OperatorGate fall back to the unlock form.
    // Gated on the operator flag rather than the status alone so an unrelated 403
    // can't lock the operator out.
    if (isOperator && res.status === 403) clearOperatorKey();

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
    throw new ApiError(message.slice(0, 300) || `HTTP ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

/** Same as `request`, with the operator key attached and 403 handling enabled. */
function operatorRequest<T>(path: string, options?: RequestInit): Promise<T> {
  return request<T>(
    path,
    { ...options, headers: { "X-Operator-Key": getOperatorKey(), ...(options?.headers as Record<string, string> | undefined) } },
    true,
  );
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

// Operator-only: starting an audit spends PageSpeed, Anthropic, SE Ranking and
// DataForSEO budget, so the endpoint is key-gated server-side. The /full-audit page
// already called itself "Intern gebruik"; it just wasn't enforced.
export function createFullAudit(payload: FullAuditRequest): Promise<FullAuditCreateResponse> {
  return operatorRequest<FullAuditCreateResponse>("/full-audit", {
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
// included in getFullAudit's response. Resolves to null when the operator key isn't
// set, so callers can treat this as "unavailable" rather than erroring the whole page.
export function getFullAuditSanityExport(auditId: string): Promise<Record<string, unknown> | null> {
  if (!getOperatorKey()) return Promise.resolve(null);
  return operatorRequest<Record<string, unknown>>(`/full-audit/${auditId}/sanity-export`).catch(() => null);
}

// Operator-only. Unlike the two reads above this THROWS rather than resolving to null:
// those are supplementary data that a page renders fine without, whereas this read *is*
// the scans overview. It doubles as the unlock-form validator, which needs to tell a
// 403 (wrong key) apart from a network failure.
/**
 * Checks a candidate key before it is stored.
 *
 * Takes the key explicitly rather than going through `operatorRequest`, which reads
 * sessionStorage — at unlock time nothing is stored yet, so routing this through the
 * normal path sent an empty header and rejected every key, including the correct one.
 *
 * `isOperator` stays false so a 403 here can't clear an already-valid stored key when
 * someone mistypes while re-authenticating. Throws ApiError so the caller can tell a
 * 403 (wrong key) from a network failure.
 */
export function verifyOperatorKey(key: string): Promise<FullAuditListResponse> {
  return request<FullAuditListResponse>("/full-audit?limit=1", {
    headers: { "X-Operator-Key": key },
  });
}

export function listFullAudits(params: { limit?: number; offset?: number; q?: string } = {}): Promise<FullAuditListResponse> {
  const search = new URLSearchParams();
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  if (params.q) search.set("q", params.q);
  const qs = search.toString();
  return operatorRequest<FullAuditListResponse>(`/full-audit${qs ? `?${qs}` : ""}`);
}

// --- Competitor benchmark (marktvergelijking) --------------------------------------

export function createCompetitorBenchmark(payload: CompetitorBenchmarkCreatePayload): Promise<CompetitorBenchmarkCreateResponse> {
  return operatorRequest<CompetitorBenchmarkCreateResponse>("/competitor-benchmark", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// Operator-only, and THROWS deliberately (see listFullAudits). This is the recovery
// path for a run id that only ever lived in React state: resolving a failure to null
// here would silently show the "start" form again and invite a duplicate paid run,
// which is the exact bug this endpoint exists to fix.
export function listCompetitorBenchmarkRuns(fullAuditId: string): Promise<CompetitorRunListResponse> {
  return operatorRequest<CompetitorRunListResponse>(`/competitor-benchmark?full_audit_id=${fullAuditId}`);
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
  if (!getOperatorKey()) return Promise.resolve(null);
  return operatorRequest<CompetitorCandidatesResponse>(`/competitor-benchmark/${runId}/candidates`).catch(() => null);
}

// Deliberately does NOT swallow errors to null like the operator reads above — this
// is a write (it mutates which competitors are measured), and a silent failure on a
// write is a UX trap: the operator would believe an override took effect when it
// didn't.
export function updateCompetitorSet(runId: string, payload: CompetitorSetUpdatePayload): Promise<CompetitorSetUpdateResponse> {
  return operatorRequest<CompetitorSetUpdateResponse>(`/competitor-benchmark/${runId}/competitors`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function remeasureCompetitors(runId: string, force: boolean): Promise<CompetitorBenchmarkCreateResponse> {
  return operatorRequest<CompetitorBenchmarkCreateResponse>(`/competitor-benchmark/${runId}/remeasure`, {
    method: "POST",
    body: JSON.stringify({ force }),
  });
}

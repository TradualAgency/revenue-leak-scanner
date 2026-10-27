import { type ReactNode, useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import Footer from "~/components/Footer";
import Header from "~/components/Header";
import { FixCard } from "~/components/operator/FixAgentsPanel";
import OperatorGate from "~/components/operator/OperatorGate";
import VerificationPanel from "~/components/operator/VerificationPanel";
import { AGENT_CATALOG, AGENT_INFO, agentPageUrl, isFixAgent, isRunActive } from "~/components/operator/agentCatalog";
import FunnelWalkSection from "~/components/report/FunnelWalkSection";
import ReportCard from "~/components/report/ReportCard";
import SectionLabel from "~/components/report/SectionLabel";
import { getFullAudit, listFixAgentRuns, startFixAgents } from "~/lib/api";
import type {
  AgentRun,
  AgentRunName,
  FixAgentRunsResponse,
  FindingOut,
  FixPackage,
  FullAuditResponse,
  FunnelWalk,
  VerificationReport,
} from "~/lib/types";

export function meta() {
  return [
    { title: "Agent-bevindingen — Tradual" },
    { name: "robots", content: "noindex,nofollow" },
  ];
}

const AUTO = "auto";

function nlDateTime(iso: string): string {
  return new Date(iso).toLocaleString("nl-NL", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function AgentFindingsPage() {
  return (
    <OperatorGate>
      <AgentFindings />
    </OperatorGate>
  );
}

function AgentFindings() {
  const { auditId = "", agent: agentParam = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const agent = (AGENT_CATALOG.some((a) => a.name === agentParam) ? agentParam : null) as AgentRunName | null;
  const info = agent ? AGENT_INFO[agent] : null;

  const [runs, setRuns] = useState<FixAgentRunsResponse | null>(null);
  const [audit, setAudit] = useState<FullAuditResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const refreshRuns = useCallback(
    () => listFixAgentRuns(auditId).then(setRuns).catch((err) => setError(err instanceof Error ? err.message : "Laden mislukt")),
    [auditId],
  );

  useEffect(() => {
    refreshRuns();
    // The audit gives the automatic verifier/funnel results and the finding labels.
    getFullAudit(auditId).then(setAudit).catch(() => setAudit(null));
  }, [auditId, refreshRuns]);

  const agentRuns = (runs?.runs ?? []).filter((r) => r.agent === agent);
  const anyActive = agentRuns.some(isRunActive);
  useEffect(() => {
    if (!anyActive) return;
    const timer = setInterval(refreshRuns, 3000);
    return () => clearInterval(timer);
  }, [anyActive, refreshRuns]);

  const auto = audit?.data
    ? agent === "verifier"
      ? audit.data.revenue_leak?.verification ?? null
      : agent === "funnel"
        ? audit.data.funnel_walk ?? null
        : null
    : null;

  // ?run=<id> picks a run; ?run=auto the automatic result; default: newest manual run, else the automatic one.
  const requested = searchParams.get("run");
  const selectedRun = requested && requested !== AUTO ? agentRuns.find((r) => r.id === requested) ?? null : null;
  const showAuto = !!info?.automatic && (requested === AUTO || (!requested && agentRuns.length === 0));
  const current: AgentRun | null = showAuto ? null : selectedRun ?? agentRuns[0] ?? null;

  async function start() {
    if (!agent) return;
    setStarting(true);
    setError(null);
    try {
      const res = await startFixAgents(auditId, [agent]);
      setRuns(res);
      const newest = res.runs.find((r) => r.agent === agent);
      if (newest) setSearchParams({ run: newest.id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Starten mislukt");
    } finally {
      setStarting(false);
    }
  }

  if (!agent || !info) {
    return (
      <Shell>
        <p className="text-sm text-gray-500">Onbekende agent.</p>
      </Shell>
    );
  }

  const auditReady = (runs?.audit_status ?? audit?.status) === "ready_for_review";
  const findings = audit?.data?.revenue_leak?.findings ?? [];

  return (
    <Shell>
      <p className="text-xs text-gray-500 mb-2">
        <Link to="/scans" className="text-tradual-primary hover:underline">← Scans</Link>
        {" · "}
        <Link to={`/full-audit/${auditId}`} className="text-tradual-primary hover:underline">Audit</Link>
      </p>
      <SectionLabel className="mb-3">Agent-bevindingen · intern</SectionLabel>
      <h1 className="text-3xl font-semibold text-tradual-primary mb-1" style={{ fontFamily: "var(--font-serif)" }}>
        {info.label}
      </h1>
      <p className="text-sm text-gray-500 mb-1">
        {runs?.company_name || runs?.store_url?.replace(/^https?:\/\//, "") || audit?.store_url}
      </p>
      <p className="text-sm text-gray-500 mb-6">{info.description}</p>

      <div className="flex flex-wrap items-center gap-3 mb-6">
        <button
          type="button"
          onClick={start}
          disabled={!auditReady || anyActive || starting}
          className="text-sm font-semibold px-4 py-2 bg-tradual-primary text-white hover:bg-tradual-primary-light disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {starting ? "Starten…" : anyActive ? "Bezig…" : agentRuns.length ? "Opnieuw draaien" : "Start agent"}
        </button>
        {(agentRuns.length > 0 || info.automatic) && (
        <select
          value={showAuto ? AUTO : current?.id ?? ""}
          onChange={(e) => setSearchParams({ run: e.target.value })}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
          aria-label="Kies een run"
        >
          {agentRuns.map((r) => (
            <option key={r.id} value={r.id}>
              {nlDateTime(r.created_at)} · {r.status === "done" ? "klaar" : r.status === "failed" ? "mislukt" : "bezig"}
            </option>
          ))}
          {info.automatic && <option value={AUTO}>Automatisch bij de audit</option>}
        </select>
        )}
        {!info.automatic && agentRuns.length === 0 && <span className="text-xs text-gray-400">Nog geen runs.</span>}
        {isFixAgent(agent) && !runs?.has_admin_token && (
          <span className="text-xs text-gray-500">
            Zonder Admin-token leest de agent geen theme-code.{" "}
            <Link to={`/full-audit/${auditId}`} className="text-tradual-primary hover:underline">Token instellen</Link>
          </span>
        )}
      </div>

      {error && <p className="text-sm text-[#EF4444] mb-4">{error}</p>}
      {!auditReady && runs && <p className="text-sm text-gray-500 mb-4">De audit is nog niet klaar; agents kunnen daarna starten.</p>}

      {showAuto ? (
        auto ? (
          <AgentResult agent={agent} result={auto} auditId={auditId} findings={findings} />
        ) : (
          <ReportCard className="p-5"><p className="text-sm text-gray-500">Geen automatisch resultaat bij deze audit (uitgeschakeld, of de audit is van vóór deze agent).</p></ReportCard>
        )
      ) : current ? (
        <RunView run={current} auditId={auditId} findings={findings} />
      ) : (
        <ReportCard className="p-5"><p className="text-sm text-gray-500">Nog geen bevindingen. Start de agent om ze te zien.</p></ReportCard>
      )}

      <p className="text-[11px] text-gray-400 mt-6">
        Losse runs passen het klantrapport niet aan.{" "}
        {AGENT_CATALOG.filter((a) => a.name !== agent).map((a, i) => (
          <span key={a.name}>
            {i > 0 && " · "}
            <Link to={agentPageUrl(auditId, a.name)} className="hover:underline">{a.label}</Link>
          </span>
        ))}
      </p>
    </Shell>
  );
}

function RunView({ run, auditId, findings }: { run: AgentRun; auditId: string; findings: FindingOut[] }) {
  if (isRunActive(run)) {
    return <ReportCard className="p-5"><p className="text-sm text-gray-500">De agent is bezig… deze pagina ververst vanzelf.</p></ReportCard>;
  }
  return (
    <div className="space-y-3">
      {run.status === "failed" && (
        <ReportCard className="p-5"><p className="text-sm text-red-600">Mislukt: {run.error_message}</p></ReportCard>
      )}
      {run.result && <AgentResult agent={run.agent} result={run.result} auditId={auditId} findings={findings} />}
      {/* The verifier and funnel views already show model and tokens themselves. */}
      {isFixAgent(run.agent) && (
        <p className="text-[11px] text-gray-400">
          {run.model} · {(run.input_tokens ?? 0).toLocaleString("nl-NL")} in / {(run.output_tokens ?? 0).toLocaleString("nl-NL")} uit
        </p>
      )}
    </div>
  );
}

function AgentResult({ agent, result, auditId, findings }: {
  agent: AgentRunName;
  result: FixPackage | VerificationReport | FunnelWalk;
  auditId: string;
  findings: FindingOut[];
}) {
  if (agent === "verifier") {
    const report = result as VerificationReport;
    if (report.verdicts.length === 0) {
      return <ReportCard className="p-5"><p className="text-sm text-gray-500">{report.errors[0] ?? "Geen oordelen."}</p></ReportCard>;
    }
    return <VerificationPanel report={report} findings={findings} />;
  }
  if (agent === "funnel") {
    return <FunnelWalkSection auditId={auditId} walk={result as FunnelWalk} />;
  }
  const pkg = result as FixPackage;
  return (
    <ReportCard className="p-5 space-y-3">
      <p className="text-sm text-gray-700">{pkg.summary_nl}</p>
      {pkg.warnings.map((w, i) => <p key={i} className="text-xs text-amber-700">{w}</p>)}
      {pkg.fixes.map((fix, i) => <FixCard key={i} fix={fix} />)}
      {pkg.assumptions.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Aannames</p>
          <ul className="list-disc list-inside text-xs text-gray-500">
            {pkg.assumptions.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </div>
      )}
      {pkg.used_admin_data && <p className="text-[11px] text-gray-400">Met Admin-data</p>}
    </ReportCard>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-tradual-bg flex flex-col">
      <Header />
      <main className="flex-1 py-12 px-4">
        <div className="max-w-4xl mx-auto">{children}</div>
      </main>
      <Footer />
    </div>
  );
}

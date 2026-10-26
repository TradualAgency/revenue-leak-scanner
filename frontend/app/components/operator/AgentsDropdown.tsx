import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { listFixAgentRuns, startFixAgents } from "~/lib/api";
import type { AgentRun, AgentRunName, FixAgentRunsResponse } from "~/lib/types";
import { AGENT_CATALOG, agentPageUrl, isRunActive, latestRunPerAgent } from "./agentCatalog";

const STATUS_LABEL: Record<AgentRun["status"], string> = {
  queued: "In de wachtrij",
  processing: "Bezig…",
  done: "Klaar",
  failed: "Mislukt",
};

const STATUS_TONE: Record<AgentRun["status"], string> = {
  queued: "text-gray-500",
  processing: "text-amber-700",
  done: "text-emerald-700",
  failed: "text-red-600",
};

function nlDateTime(iso: string): string {
  return new Date(iso).toLocaleString("nl-NL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** The agents of one audit, under its row on /scans: start each one separately and
 * open its findings on its own page. Loads when opened; polls while a run is active. */
export default function AgentsDropdown({ auditId, auditReady }: { auditId: string; auditReady: boolean }) {
  const [data, setData] = useState<FixAgentRunsResponse | null>(null);
  const [starting, setStarting] = useState<AgentRunName | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    () => listFixAgentRuns(auditId).then(setData).catch((err) => setError(err instanceof Error ? err.message : "Laden mislukt")),
    [auditId],
  );

  useEffect(() => { refresh(); }, [refresh]);

  const latest = latestRunPerAgent(data?.runs ?? []);
  const anyActive = Object.values(latest).some((r) => r && isRunActive(r));
  useEffect(() => {
    if (!anyActive) return;
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [anyActive, refresh]);

  async function start(agent: AgentRunName) {
    setStarting(agent);
    setError(null);
    try {
      await startFixAgents(auditId, [agent]);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Starten mislukt");
    } finally {
      setStarting(null);
    }
  }

  return (
    <div className="bg-gray-50 border-t border-gray-100 px-3 py-3">
      {!auditReady && <p className="text-xs text-gray-500 mb-2">Agents kunnen pas starten als de audit klaar is.</p>}
      {error && <p className="text-xs text-[#EF4444] mb-2">{error}</p>}
      {data && (
        <p className="text-[11px] text-gray-500 mb-2">
          Shopify Admin-token: {data.has_admin_token ? <span className="text-emerald-700">actief</span> : "niet ingesteld"}
          {" · "}
          <Link to={`/full-audit/${auditId}`} className="text-tradual-primary hover:underline">instellen op de auditpagina</Link>
          {" · "}losse runs passen het klantrapport niet aan
        </p>
      )}
      <ul className="divide-y divide-gray-100 border border-gray-100 rounded-lg bg-white">
        {AGENT_CATALOG.map((agent) => {
          const run = latest[agent.name];
          const active = run ? isRunActive(run) : false;
          return (
            <li key={agent.name} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2">
              <div className="flex-1 min-w-[220px]">
                <p className="text-xs font-semibold text-gray-800">
                  {agent.label}
                  {agent.automatic && <span className="ml-1.5 text-[10px] font-normal text-gray-400">ook automatisch bij elke audit</span>}
                </p>
                <p className="text-[11px] text-gray-500">{agent.description}</p>
              </div>
              <div className="text-[11px] whitespace-nowrap tabular-nums w-36">
                {run ? (
                  <>
                    <span className={STATUS_TONE[run.status]}>{STATUS_LABEL[run.status]}</span>
                    <span className="text-gray-400"> · {nlDateTime(run.created_at)}</span>
                  </>
                ) : (
                  <span className="text-gray-300">Nog niet gedraaid</span>
                )}
              </div>
              <div className="flex items-center gap-3 whitespace-nowrap">
                <button
                  type="button"
                  onClick={() => start(agent.name)}
                  disabled={!auditReady || active || starting !== null}
                  className="text-xs font-semibold px-3 py-1 bg-tradual-primary text-white hover:bg-tradual-primary-light disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {starting === agent.name ? "Starten…" : run ? "Opnieuw" : "Start"}
                </button>
                <Link to={agentPageUrl(auditId, agent.name)} className="text-xs text-tradual-primary hover:underline font-medium">
                  Bevindingen →
                </Link>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

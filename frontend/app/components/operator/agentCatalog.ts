import type { AgentRun, AgentRunName, FixAgentName, FixAgentRun } from "~/lib/types";

export interface AgentInfo {
  name: AgentRunName;
  label: string;
  description: string;
  /** Also runs automatically inside every full audit (its auto result lives on the audit). */
  automatic: boolean;
}

/** The one list of agents an operator can start per audit, in display order. */
export const AGENT_CATALOG: AgentInfo[] = [
  {
    name: "verifier",
    label: "Controle-agent",
    description: "Controleert elke geprijsde finding op de live store: bevestigd, weerlegd of niet te verifiëren",
    automatic: true,
  },
  {
    name: "funnel",
    label: "Funnel-agent",
    description: "Loopt met een mobiele browser van homepage tot checkout en legt obstakels vast met screenshots",
    automatic: true,
  },
  { name: "speed_bloat", label: "Snelheid & app-bloat", description: "Scripts uitstellen/verwijderen, LCP-afbeelding, overbodige apps", automatic: false },
  { name: "tracking", label: "Tracking & CAPI", description: "Consent Mode v2, Meta CAPI, GA4, dubbele pixels", automatic: false },
  { name: "cro_pdp", label: "CRO productpagina", description: "Social proof, mobiel boven de vouw, cart, e-mailcapture", automatic: false },
  { name: "checkout_schema", label: "Checkout & schema", description: "Checkout-frictie, Product-JSON-LD, Merchant Center-feed", automatic: false },
];

export const AGENT_INFO = Object.fromEntries(AGENT_CATALOG.map((a) => [a.name, a])) as Record<AgentRunName, AgentInfo>;

const FIX_AGENTS = new Set<AgentRunName>(["speed_bloat", "tracking", "cro_pdp", "checkout_schema"]);

export function isFixAgent(name: AgentRunName): name is FixAgentName {
  return FIX_AGENTS.has(name);
}

export function isFixRun(run: AgentRun): run is FixAgentRun {
  return isFixAgent(run.agent);
}

export function isRunActive(run: AgentRun): boolean {
  return run.status === "queued" || run.status === "processing";
}

/** Runs come newest-first from the API; this keeps the newest per agent. */
export function latestRunPerAgent(runs: AgentRun[]): Partial<Record<AgentRunName, AgentRun>> {
  const out: Partial<Record<AgentRunName, AgentRun>> = {};
  for (const run of runs) if (!out[run.agent]) out[run.agent] = run;
  return out;
}

export function agentPageUrl(auditId: string, agent: AgentRunName, runId?: string): string {
  return `/full-audit/${auditId}/agents/${agent}${runId ? `?run=${runId}` : ""}`;
}

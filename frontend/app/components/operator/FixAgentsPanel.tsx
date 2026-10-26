import { useEffect, useState } from "react";
import {
  deleteShopifyAdminToken,
  listFixAgentRuns,
  saveShopifyAdminToken,
  startFixAgents,
} from "~/lib/api";
import { eurRange } from "~/lib/format";
import type { FixAgentName, FixAgentRun, FixAgentRunsResponse, FixItem } from "~/lib/types";

const AGENTS: { name: FixAgentName; label: string; description: string }[] = [
  { name: "speed_bloat", label: "Snelheid & app-bloat", description: "Scripts uitstellen/verwijderen, LCP-afbeelding, overbodige apps" },
  { name: "tracking", label: "Tracking & CAPI", description: "Consent Mode v2, Meta CAPI, GA4, dubbele pixels" },
  { name: "cro_pdp", label: "CRO productpagina", description: "Social proof, mobiel boven de vouw, cart, e-mailcapture" },
  { name: "checkout_schema", label: "Checkout & schema", description: "Checkout-frictie, Product-JSON-LD, Merchant Center-feed" },
];

const AGENT_LABEL = Object.fromEntries(AGENTS.map((a) => [a.name, a.label])) as Record<FixAgentName, string>;

const RISK_TONE: Record<FixItem["risk"], string> = {
  laag: "bg-emerald-50 text-emerald-700",
  middel: "bg-yellow-50 text-yellow-700",
  hoog: "bg-red-50 text-red-700",
};

function isActive(run: FixAgentRun): boolean {
  return run.status === "queued" || run.status === "processing";
}

/** Newest run per agent — older runs stay in the database as history. */
function latestPerAgent(runs: FixAgentRun[]): FixAgentRun[] {
  const seen = new Set<FixAgentName>();
  return runs.filter((r) => (seen.has(r.agent) ? false : (seen.add(r.agent), true)));
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })}
      className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 hover:text-gray-700"
    >
      {copied ? "Gekopieerd" : "Kopieer"}
    </button>
  );
}

function FixCard({ fix }: { fix: FixItem }) {
  return (
    <div className="border border-gray-100 rounded-xl p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h4 className="text-sm font-semibold text-gray-800">{fix.title_nl}</h4>
        <div className="flex flex-wrap items-center gap-1.5">
          {fix.priced && (
            <span className="text-xs font-semibold text-[#EF4444]">{eurRange(fix.monthly_low, fix.monthly_high)}/mnd</span>
          )}
          {fix.effort && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
              {fix.effort} · {fix.effort_days_low}–{fix.effort_days_high} dagen · {fix.owner}
            </span>
          )}
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${RISK_TONE[fix.risk]}`}>risico {fix.risk}</span>
          {fix.verify_manually && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">handmatig verifiëren</span>
          )}
        </div>
      </div>

      {fix.finding_ids.length > 0 && (
        <p className="text-[11px] font-mono text-gray-400">{fix.finding_ids.join(" · ")}</p>
      )}

      <ol className="list-decimal list-inside space-y-1 text-sm text-gray-700">
        {fix.steps_nl.map((s, i) => <li key={i}>{s}</li>)}
      </ol>

      {fix.apps_to_remove.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Verwijderen</p>
          <ul className="list-disc list-inside text-sm text-gray-700">
            {fix.apps_to_remove.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </div>
      )}

      {fix.code_snippets.map((snippet, i) => (
        <div key={i} className="rounded-lg border border-gray-100 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-1.5 bg-gray-50 border-b border-gray-100">
            <span className="text-xs font-mono text-gray-600">{snippet.file_path} <span className="text-gray-400">({snippet.language})</span></span>
            <CopyButton text={snippet.after} />
          </div>
          <p className="px-3 pt-2 text-xs text-gray-500">{snippet.explanation}</p>
          {snippet.before && (
            <pre className="mx-3 mt-2 p-2 text-[11px] leading-snug bg-red-50 text-red-900 rounded overflow-x-auto whitespace-pre">{snippet.before}</pre>
          )}
          <pre className="m-3 p-2 text-[11px] leading-snug bg-emerald-50 text-emerald-900 rounded overflow-x-auto whitespace-pre">{snippet.after}</pre>
        </div>
      ))}

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Verificatie</p>
          <ul className="space-y-0.5 text-sm text-gray-700">
            {fix.verification_checklist.map((c, i) => <li key={i}>☐ {c}</li>)}
          </ul>
          {fix.remeasure_metric && (
            <p className="text-xs text-gray-500 mt-1">Hermeten: {fix.remeasure_metric} na {fix.remeasure_after_days} dagen</p>
          )}
        </div>
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Terugdraaien</p>
          <p className="text-sm text-gray-700">{fix.rollback_nl}</p>
        </div>
      </div>
    </div>
  );
}

function RunResult({ run }: { run: FixAgentRun }) {
  const [open, setOpen] = useState(false);
  const pkg = run.result;
  return (
    <div className="border-t border-gray-100 pt-4">
      <button type="button" onClick={() => setOpen((o) => !o)} className="w-full flex items-center justify-between text-left">
        <span className="text-sm font-semibold text-gray-800">{AGENT_LABEL[run.agent]}</span>
        <span className="text-xs text-gray-500">
          {isActive(run) && "Bezig…"}
          {run.status === "failed" && <span className="text-red-600">Mislukt</span>}
          {pkg && `${pkg.fixes.length} fixes ${open ? "▴" : "▾"}`}
        </span>
      </button>
      {run.status === "failed" && run.error_message && <p className="text-xs text-red-600 mt-1">{run.error_message}</p>}
      {pkg && open && (
        <div className="mt-3 space-y-3">
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
          <p className="text-[11px] text-gray-400">
            {run.model} · {run.input_tokens?.toLocaleString("nl-NL")} in / {run.output_tokens?.toLocaleString("nl-NL")} uit
            {pkg.used_admin_data && " · met Admin-data"}
          </p>
        </div>
      )}
    </div>
  );
}

function AdminTokenForm({ auditId, state, onChange }: {
  auditId: string;
  state: Pick<FixAgentRunsResponse, "has_admin_token" | "shopify_shop_domain">;
  onChange: () => void;
}) {
  const [domain, setDomain] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await saveShopifyAdminToken(auditId, domain, token);
      setToken("");
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Opslaan mislukt");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await deleteShopifyAdminToken(auditId);
      onChange();
    } finally {
      setBusy(false);
    }
  }

  if (state.has_admin_token) {
    return (
      <p className="text-xs text-gray-500 mb-4">
        Read-only Admin-token actief voor <span className="font-mono">{state.shopify_shop_domain}</span>.{" "}
        <button type="button" onClick={remove} disabled={busy} className="text-red-600 hover:underline">Verwijderen</button>
      </p>
    );
  }

  return (
    <details className="mb-4">
      <summary className="text-xs font-semibold text-gray-400 uppercase tracking-wide cursor-pointer">
        Shopify Admin-token (optioneel)
      </summary>
      <p className="text-xs text-gray-500 mt-2 mb-2">
        Laat de klant een custom app maken (Instellingen › Apps › Apps ontwikkelen) met alleen{" "}
        <span className="font-mono">read_themes</span> en <span className="font-mono">read_products</span>. Tokens met schrijfrechten worden geweigerd.
        Met token lezen de agents de echte theme-code.
      </p>
      <div className="flex flex-col sm:flex-row gap-2">
        <input
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="merk.myshopify.com"
          className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-[#c5a96f]"
        />
        <input
          value={token}
          onChange={(e) => setToken(e.target.value)}
          type="password"
          placeholder="shpat_…"
          autoComplete="off"
          className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-[#c5a96f]"
        />
        <button
          type="button"
          onClick={save}
          disabled={busy || !domain || !token}
          className="bg-tradual-primary text-white text-xs font-medium px-4 py-2 disabled:opacity-50"
        >
          {busy ? "Controleren…" : "Opslaan"}
        </button>
      </div>
      {error && <p className="text-xs text-red-600 mt-1">{error}</p>}
    </details>
  );
}

export default function FixAgentsPanel({ auditId }: { auditId: string }) {
  const [data, setData] = useState<FixAgentRunsResponse | null>(null);
  const [selected, setSelected] = useState<Set<FixAgentName>>(new Set(AGENTS.map((a) => a.name)));
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const latest = latestPerAgent(data?.runs ?? []);
  const anyActive = latest.some(isActive);

  function refresh() {
    return listFixAgentRuns(auditId).then(setData).catch((err) => setError(err instanceof Error ? err.message : "Laden mislukt"));
  }

  useEffect(() => { refresh(); }, [auditId]);

  useEffect(() => {
    if (!anyActive) return;
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [anyActive, auditId]);

  async function handleStart() {
    setStarting(true);
    setError(null);
    try {
      await startFixAgents(auditId, AGENTS.map((a) => a.name).filter((n) => selected.has(n)));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Starten mislukt");
    } finally {
      setStarting(false);
    }
  }

  function toggle(name: FixAgentName) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  return (
    <section className="rounded-2xl p-6 bg-white border border-gray-100 shadow-sm">
      <h2 className="text-lg font-semibold mb-1 text-gray-700" style={{ fontFamily: "var(--font-serif)" }}>
        Fix-agents
      </h2>
      <p className="text-sm text-gray-500 mb-4">
        Intern: per vakgebied een uitvoerbaar fix-pakket met stappen, code-snippets en een verificatie-checklist. De agents lezen alleen en wijzigen niets aan de store.
      </p>

      {data && <AdminTokenForm auditId={auditId} state={data} onChange={refresh} />}

      <div className="grid gap-2 sm:grid-cols-2 mb-4">
        {AGENTS.map((a) => (
          <label key={a.name} className="flex items-start gap-2 border border-gray-100 rounded-lg p-3 cursor-pointer">
            <input type="checkbox" checked={selected.has(a.name)} onChange={() => toggle(a.name)} className="mt-0.5 accent-[#0a2f23]" />
            <span>
              <span className="block text-sm font-medium text-gray-800">{a.label}</span>
              <span className="block text-xs text-gray-500">{a.description}</span>
            </span>
          </label>
        ))}
      </div>

      <button
        type="button"
        onClick={handleStart}
        disabled={starting || anyActive || selected.size === 0}
        className="bg-tradual-accent text-tradual-primary text-sm font-medium px-8 py-3 hover:opacity-90 transition-opacity disabled:opacity-50"
      >
        {starting ? "Starten…" : anyActive ? "Agents bezig…" : "Start fix-agents"}
      </button>
      {error && <p className="text-xs text-red-600 mt-2">{error}</p>}

      {latest.length > 0 && <div className="mt-6 space-y-4">{latest.map((run) => <RunResult key={run.id} run={run} />)}</div>}
    </section>
  );
}

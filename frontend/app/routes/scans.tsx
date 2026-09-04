import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import Footer from "~/components/Footer";
import Header from "~/components/Header";
import OperatorGate from "~/components/operator/OperatorGate";
import ReportCard from "~/components/report/ReportCard";
import SectionLabel from "~/components/report/SectionLabel";
import StatusPill from "~/components/report/StatusPill";
import type { PillTone } from "~/components/report/tone";
import { listFullAudits } from "~/lib/api";
import type { BenchmarkRunSummary, FullAuditListItem } from "~/lib/types";

export function meta() {
  return [
    { title: "Scans — Tradual" },
    { name: "robots", content: "noindex,nofollow" },
  ];
}

const PAGE_SIZE = 50;

// Statuses a run can still move out of. While any row sits in one of these the list
// refetches, so a benchmark started elsewhere shows up without a manual reload.
const NON_TERMINAL = new Set(["queued", "discovering", "measuring", "scoring"]);

function auditTone(status: string): PillTone {
  if (status === "ready_for_review") return "ok";
  if (status === "failed") return "warning";
  return "muted";
}

function benchmarkTone(status: string): PillTone {
  if (status === "ready") return "ok";
  if (status === "insufficient_data" || status === "failed") return "warning";
  return "muted";
}

const BENCHMARK_LABEL: Record<string, string> = {
  queued: "In wachtrij",
  discovering: "Opsporen",
  measuring: "Meten",
  scoring: "Berekenen",
  ready: "Klaar",
  insufficient_data: "Te weinig data",
  failed: "Mislukt",
};

function nlDate(iso: string): string {
  return new Date(iso).toLocaleDateString("nl-NL", { day: "numeric", month: "short", year: "numeric" });
}

/** A finished run is worth linking to; an in-flight one has no page to show yet. */
function isViewable(run: BenchmarkRunSummary): boolean {
  return run.status === "ready" || run.status === "insufficient_data";
}

export default function Scans() {
  return (
    <OperatorGate>
      <ScansTable />
    </OperatorGate>
  );
}

function ScansTable() {
  const [items, setItems] = useState<FullAuditListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Debounced so typing in the search box doesn't fire a request per keystroke.
  const [debouncedQuery, setDebouncedQuery] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);

  const load = useCallback(async () => {
    try {
      const res = await listFullAudits({ limit, q: debouncedQuery || undefined });
      setItems(res.items);
      setTotal(res.total);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kon scans niet laden");
    } finally {
      setLoading(false);
    }
  }, [limit, debouncedQuery]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  // Refetching the whole list beats polling per row: at this size one request is
  // cheaper than N, and the rows can't drift out of sync with each other.
  const hasRunning = items.some((a) => a.latest_benchmark && NON_TERMINAL.has(a.latest_benchmark.status));
  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    if (!hasRunning) return;
    const t = setInterval(() => loadRef.current(), 5000);
    return () => clearInterval(t);
  }, [hasRunning]);

  return (
    <div className="min-h-screen bg-tradual-bg flex flex-col">
      <Header />
      <main className="flex-1 py-12 px-4">
        <div className="max-w-6xl mx-auto">
          <SectionLabel className="mb-3">Intern gebruik</SectionLabel>
          <h1
            className="text-3xl font-semibold text-tradual-primary mb-2"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Scans
          </h1>
          <p className="text-sm text-gray-500 mb-8">
            Alle uitgevoerde audits en hun marktvergelijking.
          </p>

          <div className="flex items-center justify-between gap-4 mb-4">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Zoek op winkel of bedrijf…"
              className="w-full max-w-xs border border-gray-200 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c5a96f] focus:border-transparent"
            />
            <span className="text-xs text-gray-400 whitespace-nowrap tabular-nums">
              {items.length} van {total}
            </span>
          </div>

          {error && (
            <p className="text-sm text-[#EF4444] mb-4">{error}</p>
          )}

          <ReportCard className="overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {["Winkel", "Bedrijf", "Gescand", "Audit", "Marktvergelijking", ""].map((h) => (
                    <th
                      key={h}
                      className="text-left py-2 px-3 text-gray-400 font-medium uppercase tracking-wide text-[10px]"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map((audit) => (
                  <tr key={audit.id}>
                    <td className="py-2.5 px-3 text-gray-900 font-medium max-w-[240px] truncate">
                      {audit.latest_benchmark?.store_domain ?? audit.store_url.replace(/^https?:\/\//, "")}
                    </td>
                    <td className="py-2.5 px-3 text-gray-500 max-w-[180px] truncate">
                      {audit.company_name || "—"}
                    </td>
                    <td className="py-2.5 px-3 text-gray-400 tabular-nums whitespace-nowrap">
                      {nlDate(audit.created_at)}
                    </td>
                    <td className="py-2.5 px-3">
                      <StatusPill tone={auditTone(audit.status)}>{audit.status}</StatusPill>
                    </td>
                    <td className="py-2.5 px-3 whitespace-nowrap">
                      {audit.latest_benchmark ? (
                        <span className="inline-flex items-center gap-1.5">
                          <StatusPill tone={benchmarkTone(audit.latest_benchmark.status)}>
                            {BENCHMARK_LABEL[audit.latest_benchmark.status] ?? audit.latest_benchmark.status}
                          </StatusPill>
                          {audit.benchmark_run_count > 1 && (
                            <span
                              className="text-[10px] text-gray-400 tabular-nums"
                              title={`${audit.benchmark_run_count} runs voor deze audit`}
                            >
                              ×{audit.benchmark_run_count}
                            </span>
                          )}
                        </span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 whitespace-nowrap text-right">
                      <Link to={`/full-audit/${audit.id}`} className="text-tradual-primary hover:underline font-medium">
                        Audit →
                      </Link>
                      {audit.latest_benchmark && isViewable(audit.latest_benchmark) ? (
                        <Link
                          to={`/marktvergelijking/${audit.latest_benchmark.id}`}
                          className="ml-3 text-tradual-primary hover:underline font-medium"
                        >
                          Marktvergelijking →
                        </Link>
                      ) : (
                        !audit.latest_benchmark && (
                          // A link, not a one-click button: starting a benchmark spends
                          // DataForSEO budget, and the seed field that materially
                          // improves the result lives on the audit page.
                          <Link
                            to={`/full-audit/${audit.id}`}
                            className="ml-3 text-gray-400 hover:text-tradual-primary hover:underline"
                          >
                            Marktvergelijking starten →
                          </Link>
                        )
                      )}
                    </td>
                  </tr>
                ))}
                {!loading && items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-8 px-3 text-center text-gray-400">
                      {debouncedQuery ? "Geen scans gevonden." : "Nog geen scans."}
                    </td>
                  </tr>
                )}
                {loading && items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-8 px-3 text-center text-gray-400">
                      Laden…
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </ReportCard>

          {items.length < total && (
            <button
              onClick={() => setLimit((l) => l + PAGE_SIZE)}
              className="mt-4 text-sm text-tradual-primary hover:underline font-medium"
            >
              Meer laden ({total - items.length} resterend)
            </button>
          )}
        </div>
      </main>
      <Footer />
    </div>
  );
}

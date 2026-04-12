import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router";
import { getReportStatus, getReportSummary } from "~/lib/api";
import type { ReportStatusResponse, ReportSummaryResponse } from "~/lib/types";
import PerformanceGauge from "~/components/PerformanceGauge";
import Header from "~/components/Header";
import Footer from "~/components/Footer";

export function meta() {
  return [
    { title: "Your Audit Results — Tradual" },
    { name: "description", content: "View your store's revenue leak audit results." },
  ];
}

const POLL_INTERVAL_MS = 3000;

const statusMessages = [
  "Scanning your store...",
  "Analyzing plugins...",
  "Running PageSpeed analysis...",
  "Calculating revenue impact...",
  "Almost done...",
];

function fmt(n: number | null | undefined, prefix = "$"): string {
  if (n == null) return "—";
  return `${prefix}${Math.round(Number(n)).toLocaleString()}`;
}

function CheckIcon({ className = "w-4 h-4 text-[#c5a96f] flex-shrink-0" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const colors: Record<string, string> = {
    high: "bg-emerald-50 text-emerald-700",
    medium: "bg-yellow-50 text-yellow-700",
    low: "bg-gray-100 text-gray-500",
  };
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${colors[confidence] ?? colors.low}`}>
      {confidence}
    </span>
  );
}

export default function Results() {
  const { reportId } = useParams<{ reportId: string }>();
  const [status, setStatus] = useState<ReportStatusResponse | null>(null);
  const [summary, setSummary] = useState<ReportSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msgIndex, setMsgIndex] = useState(0);
  const [pagesExpanded, setPagesExpanded] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const msgIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isCompleted = status?.status === "completed";
  const isFailed = status?.status === "failed";
  const isPending = !isCompleted && !isFailed;

  // Cycle through status messages while scanning
  useEffect(() => {
    if (!isPending) return;
    msgIntervalRef.current = setInterval(() => {
      setMsgIndex((i) => (i + 1) % statusMessages.length);
    }, 2500);
    return () => {
      if (msgIntervalRef.current) clearInterval(msgIntervalRef.current);
    };
  }, [isPending]);

  // Poll status
  useEffect(() => {
    if (!reportId) return;

    async function poll() {
      try {
        const s = await getReportStatus(reportId!);
        setStatus(s);

        if (s.status === "completed") {
          if (intervalRef.current) clearInterval(intervalRef.current);
          const sum = await getReportSummary(reportId!);
          setSummary(sum);
        } else if (s.status === "failed") {
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch report status.");
        if (intervalRef.current) clearInterval(intervalRef.current);
      }
    }

    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [reportId]);

  if (error) {
    return (
      <div className="min-h-screen bg-[#FAFAF8] flex flex-col">
        <Header />
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="max-w-md w-full bg-white rounded-2xl shadow-sm border border-gray-100 p-10 text-center flex flex-col gap-6">
            <div className="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center mx-auto">
              <svg className="w-8 h-8 text-[#EF4444]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M12 3a9 9 0 100 18A9 9 0 0012 3z" />
              </svg>
            </div>
            <div>
              <h2 className="text-xl font-semibold text-gray-900 mb-2" style={{ fontFamily: "var(--font-serif)" }}>Something went wrong</h2>
              <p className="text-gray-500 text-sm">{error}</p>
            </div>
            <Link
              to="/"
              className="bg-[#0a2f23] hover:bg-[#1a4a3a] text-white font-medium px-6 py-3 rounded-lg transition-colors"
            >
              Try Again
            </Link>
          </div>
        </div>
        <Footer />
      </div>
    );
  }

  if (isFailed) {
    return (
      <div className="min-h-screen bg-[#FAFAF8] flex flex-col">
        <Header />
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="max-w-md w-full bg-white rounded-2xl shadow-sm border border-gray-100 p-10 text-center flex flex-col gap-6">
            <div className="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center mx-auto">
              <svg className="w-8 h-8 text-[#EF4444]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <div>
              <h2 className="text-xl font-semibold text-gray-900 mb-2" style={{ fontFamily: "var(--font-serif)" }}>Scan Failed</h2>
              <p className="text-gray-500 text-sm">
                We couldn't complete the scan for your store. This may be due to the site being
                unreachable or having restrictions. Please try again with a different URL.
              </p>
            </div>
            <Link
              to="/"
              className="bg-[#0a2f23] hover:bg-[#1a4a3a] text-white font-medium px-6 py-3 rounded-lg transition-colors"
            >
              Try Again
            </Link>
          </div>
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAFAF8] flex flex-col">
      <Header />

      <main className="flex-1 py-16 px-4">
        <div className="max-w-3xl mx-auto flex flex-col gap-10">

          {/* Scanning state */}
          {isPending && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-10 flex flex-col items-center gap-8">
              <div className="w-20 h-20 rounded-full bg-[#FAFAF8] border border-gray-100 flex items-center justify-center">
                <svg
                  className="w-10 h-10 text-[#c5a96f] animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
              </div>
              <div className="text-center">
                <h2 className="text-2xl font-semibold text-gray-900 mb-2" style={{ fontFamily: "var(--font-serif)" }}>Scanning Your Store</h2>
                <p className="text-[#c5a96f] font-medium text-sm animate-pulse">
                  {statusMessages[msgIndex]}
                </p>
              </div>

              {/* Live data if available */}
              {status && (status.pages_discovered != null || status.avg_load_time_ms != null) && (
                <div className="w-full grid grid-cols-2 gap-4">
                  {status.pages_discovered != null && (
                    <div className="bg-[#FAFAF8] rounded-xl p-4 text-center border border-gray-100">
                      <div className="text-2xl font-semibold text-[#0a2f23]">{status.pages_discovered}</div>
                      <div className="text-xs text-gray-500 mt-1">Pages Discovered</div>
                    </div>
                  )}
                  {status.avg_load_time_ms != null && (
                    <div className="bg-[#FAFAF8] rounded-xl p-4 text-center border border-gray-100">
                      <div className="text-2xl font-semibold text-[#0a2f23]">
                        {(status.avg_load_time_ms / 1000).toFixed(1)}s
                      </div>
                      <div className="text-xs text-gray-500 mt-1">Avg Load Time</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Completed results */}
          {isCompleted && summary && (
            <>
              <div className="text-center">
                <h1
                  className="text-3xl font-semibold text-gray-900"
                  style={{ fontFamily: "var(--font-serif)" }}
                >
                  Your Audit Results
                </h1>
                <p className="text-gray-500 mt-2 text-sm">
                  Here's what we found. The numbers may surprise you.
                </p>
              </div>

              {/* Section 1: Performance score */}
              {summary.performance_score != null && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 flex flex-col items-center gap-4">
                  <h2 className="text-lg font-semibold text-gray-700">Performance Score</h2>
                  <PerformanceGauge score={summary.performance_score} size={180} />
                  <p className="text-sm text-gray-500 text-center max-w-sm">
                    {summary.performance_score >= 70
                      ? "Your store is performing well. There's still room for improvement."
                      : summary.performance_score >= 40
                      ? "Your store has significant performance issues that are costing you sales."
                      : "Critical performance issues detected. Your store is losing a substantial portion of potential revenue."}
                  </p>
                </div>
              )}

              {/* Hero metrics */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 text-center">
                  <div className="text-3xl font-semibold text-[#EF4444]">
                    {summary.estimated_monthly_loss_min != null && summary.estimated_monthly_loss_max != null
                      ? `${fmt(summary.estimated_monthly_loss_min)} – ${fmt(summary.estimated_monthly_loss_max)}`
                      : "—"}
                  </div>
                  <div className="text-xs text-gray-500 mt-2 font-medium uppercase tracking-wider">
                    Est. Monthly Revenue Loss
                  </div>
                </div>

                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 text-center">
                  <div className="text-3xl font-semibold text-[#0a2f23]">
                    {summary.plugin_count ?? "—"}
                  </div>
                  <div className="text-xs text-gray-500 mt-2 font-medium uppercase tracking-wider">
                    Plugins Detected
                  </div>
                </div>

                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 text-center">
                  <div className="text-3xl font-semibold text-[#c5a96f]">
                    {fmt(summary.total_plugin_cost_monthly)}
                    <span className="text-sm font-medium text-gray-400">/mo</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-2 font-medium uppercase tracking-wider">
                    Plugin Subscription Costs
                  </div>
                </div>
              </div>

              {/* Section 2: Speed & Revenue Impact */}
              {(summary.avg_load_time_ms != null || summary.blended_loss_rate != null) && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
                  <h2 className="text-lg font-semibold text-gray-700 mb-5">Speed &amp; Revenue Impact</h2>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                    {summary.avg_load_time_ms != null && (
                      <div>
                        <div className="text-3xl font-semibold text-[#0a2f23]">
                          {(summary.avg_load_time_ms / 1000).toFixed(2)}
                          <span className="text-lg font-medium text-gray-400 ml-1">s</span>
                        </div>
                        <div className="text-sm text-gray-500 mt-1">Average Load Time</div>
                        {summary.excess_load_time != null && summary.excess_load_time > 0 && (
                          <div className="text-xs text-[#EF4444] mt-1 font-medium">
                            +{summary.excess_load_time.toFixed(1)}s above benchmark
                          </div>
                        )}
                      </div>
                    )}
                    {summary.blended_loss_rate != null && (
                      <div>
                        <div className="text-3xl font-semibold text-[#EF4444]">
                          {(summary.blended_loss_rate * 100).toFixed(1)}
                          <span className="text-lg font-medium text-gray-400 ml-0.5">%</span>
                        </div>
                        <div className="text-sm text-gray-500 mt-1">Conversion Loss from Load Time</div>
                        <div className="text-xs text-gray-400 mt-1">
                          of visitors drop off before converting
                        </div>
                      </div>
                    )}
                  </div>
                  {summary.avg_load_time_ms != null && (
                    <p className="mt-5 text-sm text-gray-500 border-t border-gray-100 pt-4">
                      Every second above 0.5s costs ~7% in conversions. Your store loads in{" "}
                      <span className="font-semibold text-gray-700">
                        {(summary.avg_load_time_ms / 1000).toFixed(1)}s
                      </span>
                      {summary.excess_load_time != null && summary.excess_load_time > 0
                        ? ` — that's ${summary.excess_load_time.toFixed(1)}s too slow.`
                        : "."}
                    </p>
                  )}
                </div>
              )}

              {/* Section 3: Detected Plugins */}
              {summary.plugins && summary.plugins.length > 0 && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
                  <h2 className="text-lg font-semibold text-gray-700 mb-5">
                    Detected Plugins ({summary.plugins.length})
                  </h2>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-100">
                          <th className="text-left py-2 pr-4 text-xs font-semibold text-gray-400 uppercase tracking-wide">Plugin</th>
                          <th className="text-left py-2 pr-4 text-xs font-semibold text-gray-400 uppercase tracking-wide">Platform</th>
                          <th className="text-right py-2 pr-4 text-xs font-semibold text-gray-400 uppercase tracking-wide">Cost/mo</th>
                          <th className="text-right py-2 text-xs font-semibold text-gray-400 uppercase tracking-wide">Confidence</th>
                        </tr>
                      </thead>
                      <tbody>
                        {summary.plugins.map((p) => (
                          <tr key={p.slug} className="border-b border-gray-50 last:border-0">
                            <td className="py-3 pr-4 font-medium text-gray-800">{p.name}</td>
                            <td className="py-3 pr-4 text-gray-500 capitalize">{p.platform}</td>
                            <td className="py-3 pr-4 text-right text-gray-700">
                              {p.estimated_monthly_cost != null && Number(p.estimated_monthly_cost) > 0
                                ? fmt(p.estimated_monthly_cost)
                                : <span className="text-gray-400">free</span>}
                            </td>
                            <td className="py-3 text-right">
                              <ConfidenceBadge confidence={p.confidence} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                      {summary.total_plugin_cost_monthly != null && Number(summary.total_plugin_cost_monthly) > 0 && (
                        <tfoot>
                          <tr className="border-t-2 border-gray-200">
                            <td className="pt-3 pr-4 font-semibold text-gray-700" colSpan={2}>Total</td>
                            <td className="pt-3 pr-4 text-right font-bold text-[#c5a96f]" colSpan={2}>
                              {fmt(summary.total_plugin_cost_monthly)}/mo
                            </td>
                          </tr>
                        </tfoot>
                      )}
                    </table>
                  </div>
                </div>
              )}

              {/* Section 4: Scanned Pages */}
              {summary.pages_scanned && summary.pages_scanned.length > 0 && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
                  <h2 className="text-lg font-semibold text-gray-700 mb-4">
                    Scanned Pages ({summary.pages_scanned.length})
                  </h2>
                  <ul className="flex flex-col gap-1.5">
                    {(pagesExpanded ? summary.pages_scanned : summary.pages_scanned.slice(0, 5)).map((url) => (
                      <li key={url} className="text-sm text-gray-600 font-mono truncate bg-[#FAFAF8] rounded-lg px-3 py-1.5 border border-gray-100">
                        {url}
                      </li>
                    ))}
                  </ul>
                  {summary.pages_scanned.length > 5 && (
                    <button
                      onClick={() => setPagesExpanded((v) => !v)}
                      className="mt-3 text-sm text-[#c5a96f] hover:underline font-medium"
                    >
                      {pagesExpanded
                        ? "Show less"
                        : `+${summary.pages_scanned.length - 5} more`}
                    </button>
                  )}
                </div>
              )}

              {/* Section 5: Quick Wins */}
              {summary.quick_wins && summary.quick_wins.length > 0 && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
                  <h2 className="text-lg font-semibold text-gray-700 mb-4">Quick Wins</h2>
                  <ul className="flex flex-col gap-3">
                    {summary.quick_wins.map((win) => (
                      <li key={win} className="flex items-start gap-3 text-sm text-gray-700">
                        <CheckIcon />
                        <span>{win}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Section 6: CTA */}
              <div className="relative overflow-hidden rounded-2xl bg-[#0a2f23] text-white p-8 ring-1 ring-[#c5a96f]/30">
                <div className="relative z-10 flex flex-col gap-6">
                  <div>
                    <span className="inline-block bg-[#c5a96f]/20 text-[#c5a96f] text-xs font-medium uppercase tracking-widest px-3 py-1 rounded-full mb-3">
                      Technical Optimization
                    </span>
                    <h2 className="text-2xl font-semibold" style={{ fontFamily: "var(--font-serif)" }}>We Build the Engine. You Bring the Driver.</h2>
                    <p className="text-gray-400 text-sm mt-2 max-w-lg leading-relaxed">
                      Tradual is not a CRO agency. We fix the technical foundation — speed, infrastructure, and the right plugin stack. Think of it as building the fastest car on the grid.
                    </p>
                    <p className="text-gray-400 text-sm mt-3 max-w-lg leading-relaxed">
                      Your CRO specialist optimizes how visitors convert once they arrive. We work together: Tradual builds the foundation, your CRO specialist drives the results.
                    </p>
                  </div>

                  <div className="bg-white/5 rounded-xl p-5 flex flex-col gap-3 select-none border border-white/10">
                    <div className="text-xs font-medium text-[#c5a96f] uppercase tracking-wider mb-1">
                      What You Get
                    </div>
                    <div className="flex flex-col gap-2">
                      {[
                        "Plugin-by-plugin audit: which tools belong in your stack and which don't",
                        "Infrastructure roadmap: build the fastest version of your store",
                        "Clear breakdown: what Tradual fixes vs. where a CRO specialist takes over",
                        "1-on-1 strategy call with Tradual",
                      ].map((item) => (
                        <div key={item} className="flex items-center gap-2 text-sm">
                          <CheckIcon />
                          <span className="text-gray-300">{item}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <a
                    href="mailto:info@tradual.com"
                    className="inline-block text-center bg-[#c5a96f] hover:bg-[#b8975e] text-white font-medium px-8 py-4 rounded-xl transition-colors shadow-lg w-full sm:w-auto tracking-wide"
                  >
                    Book Your Free Strategy Call →
                  </a>
                </div>

                <div className="absolute -top-10 -right-10 w-48 h-48 rounded-full bg-white/3 pointer-events-none" />
                <div className="absolute -bottom-16 -left-10 w-64 h-64 rounded-full bg-white/3 pointer-events-none" />
              </div>
            </>
          )}
        </div>
      </main>

      <Footer />
    </div>
  );
}

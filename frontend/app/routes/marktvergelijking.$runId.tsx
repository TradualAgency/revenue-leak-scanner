import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { getCompetitorBenchmark, getCompetitorBenchmarkStatus } from "~/lib/api";
import { eur, eurRange, eurRangeParts } from "~/lib/format";
import type {
  CompetitorBenchmarkData,
  CompetitorBenchmarkStatusResponse,
  CompetitorRosterEntry,
  GapFinding,
  LayerScore,
  MetricComparison,
} from "~/lib/types";

const POLL_INTERVAL = 3000;

const PHASE_LABELS_NL: Record<string, string> = {
  queued: "In wachtrij",
  discovering: "Concurrenten opsporen",
  measuring: "Concurrenten meten",
  scoring: "Resultaten berekenen",
};

function formatMetricValue(value: number | null, unit: MetricComparison["unit"]): string {
  if (value == null) return "—";
  switch (unit) {
    case "ms":
      return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${Math.round(value)}ms`;
    case "s":
      return `${value.toFixed(1)}s`;
    case "pct":
      return `${Math.round(value)}%`;
    case "score":
      return `${Math.round(value)}/100`;
    case "eur":
      return eur(value);
    case "count":
    default:
      return Number.isInteger(value) ? `${value}` : value.toFixed(1);
  }
}

function classificationLabel(c: string | null): string {
  switch (c) {
    case "direct": return "Directe concurrent";
    case "category": return "Categorie-concurrent";
    case "operator": return "Handmatig toegevoegd";
    default: return "";
  }
}

function statusPill(status: CompetitorRosterEntry["measure_status"]) {
  const map: Record<string, { label: string; cls: string }> = {
    ok: { label: "gemeten", cls: "bg-emerald-900/40 border-emerald-700/50 text-emerald-400" },
    partial: { label: "deels gemeten", cls: "bg-amber-900/30 border-amber-700/40 text-amber-400" },
    unreachable: { label: "niet bereikbaar", cls: "bg-white/5 border-white/10 text-white/30" },
    timeout: { label: "timeout", cls: "bg-white/5 border-white/10 text-white/30" },
  };
  const m = map[status] ?? map.unreachable;
  return <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${m.cls}`}>{m.label}</span>;
}

function CoverageNotice({ data }: { data: CompetitorBenchmarkData }) {
  const total = data.roster.length;
  const measured = data.roster.filter((r) => r.measure_status === "ok" || r.measure_status === "partial").length;
  return (
    <div className="border border-white/10 rounded-xl p-4 bg-white/[0.02]">
      <p className="text-xs text-white/50 leading-relaxed">
        Gebaseerd op <span className="text-white/80 font-medium">{measured} van de {total}</span> geselecteerde concurrenten die succesvol gemeten konden worden.
        {data.manually_curated && (
          <span className="text-[#c5a96f]/80"> Deze selectie is handmatig samengesteld door Tradual — geen automatisch marktgemiddelde.</span>
        )}
      </p>
    </div>
  );
}

function CompetitorRoster({ roster }: { roster: CompetitorRosterEntry[] }) {
  return (
    <div className="border border-white/10 rounded-xl overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-white/10 bg-white/[0.02]">
            {["Domein", "Type", "Reden", "Status", "Gemeten op"].map((h) => (
              <th key={h} className="text-left py-2 px-3 text-white/30 font-medium uppercase tracking-wide text-[10px]">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {roster.map((r) => (
            <tr key={r.domain} className="border-b border-white/5 last:border-0">
              <td className="py-2 px-3 text-white/80 font-medium">{r.domain}</td>
              <td className="py-2 px-3 text-white/40">{classificationLabel(r.classification)}</td>
              <td className="py-2 px-3 text-white/40 max-w-[280px]">{r.reason_nl}</td>
              <td className="py-2 px-3">{statusPill(r.measure_status)}</td>
              <td className="py-2 px-3 text-white/25 tabular-nums whitespace-nowrap">
                {r.measured_at ? new Date(r.measured_at).toLocaleDateString("nl-NL") : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MetricComparisonRow({ m }: { m: MetricComparison }) {
  const betterIsLower = m.direction === "lower_is_better";
  const storeIsBest = m.best != null && m.store_value != null && m.store_value === m.best;
  const storeBeatsMedian =
    m.store_value != null && m.median != null
      ? betterIsLower
        ? m.store_value <= m.median
        : m.store_value >= m.median
      : null;

  return (
    <div className="py-2.5 border-b border-white/5 last:border-0">
      <div className="flex items-start justify-between gap-4">
        <p className="text-xs font-medium text-white/75 flex-shrink-0">{m.label_nl}</p>
        <div className="flex items-center gap-4 text-right flex-shrink-0">
          <div className="w-16">
            <p className={`text-sm font-bold tabular-nums ${storeBeatsMedian === false ? "text-red-400" : storeBeatsMedian === true ? "text-emerald-400" : "text-white/60"}`}>
              {m.store_measured ? formatMetricValue(m.store_value, m.unit) : "—"}
            </p>
            <p className="text-[9px] text-white/25 uppercase tracking-wide">jij</p>
          </div>
          <div className="w-16">
            <p className="text-sm text-white/50 tabular-nums">{formatMetricValue(m.median, m.unit)}</p>
            <p className="text-[9px] text-white/25 uppercase tracking-wide">mediaan</p>
          </div>
          <div className="w-20">
            <p className="text-sm text-white/40 tabular-nums">
              {formatMetricValue(m.best, m.unit)}
              {m.best_domain && <span className="text-[9px] text-white/20 ml-1">({m.best_domain})</span>}
            </p>
            <p className="text-[9px] text-white/25 uppercase tracking-wide">beste</p>
          </div>
          <div className="w-14">
            <p className="text-sm font-semibold text-[#c5a96f] tabular-nums">
              {storeIsBest ? "1e" : m.store_rank && m.domains_ranked ? `${m.store_rank}e/${m.domains_ranked}` : "—"}
            </p>
            <p className="text-[9px] text-white/25 uppercase tracking-wide">positie</p>
          </div>
        </div>
      </div>
      <p className="text-[10px] text-white/20 mt-1">{m.coverage_label_nl}</p>
    </div>
  );
}

const LAYER_NAMES: Record<number, string> = {
  1: "Snelheid",
  2: "Stack & bloat",
  3: "Checkout-frictie",
  4: "Tracking & DNS",
  5: "Toekomstgereedheid",
};

function ComparisonTable({ comparisons }: { comparisons: MetricComparison[] }) {
  const byLayer = new Map<number, MetricComparison[]>();
  for (const c of comparisons) {
    if (!byLayer.has(c.layer)) byLayer.set(c.layer, []);
    byLayer.get(c.layer)!.push(c);
  }
  return (
    <div className="space-y-4">
      {[1, 2, 3, 4, 5].map((layer) => {
        const metrics = byLayer.get(layer) ?? [];
        if (metrics.length === 0) return null;
        return (
          <div key={layer} className="border border-white/10 rounded-xl px-5 py-4">
            <p className="text-xs font-semibold text-white/40 uppercase tracking-widest mb-2">{LAYER_NAMES[layer]}</p>
            {metrics.map((m) => (
              <MetricComparisonRow key={m.key} m={m} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

function LayerScoreCards({ layerScores }: { layerScores: LayerScore[] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
      {layerScores.map((ls) => (
        <div key={ls.layer} className="border border-white/10 rounded-xl p-4 text-center">
          <p className="text-2xl font-bold text-[#c5a96f] tabular-nums">
            {ls.relative_score != null ? Math.round(ls.relative_score) : "—"}
          </p>
          <p className="text-[10px] text-white/30 mt-1 leading-tight">{ls.name_nl}</p>
        </div>
      ))}
    </div>
  );
}

function GapMetricRow({ g }: { g: GapFinding }) {
  const hasEur = g.gap_to_median_eur_low != null && g.gap_to_median_eur_high != null;
  return (
    <div className="flex gap-3 py-2.5 border-b border-white/5 last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-white/75">{g.label_nl}</p>
        {g.note_nl && <p className="text-[11px] text-white/35 mt-0.5">{g.note_nl}</p>}
        {g.market_is_also_below_benchmark && (
          <p className="text-[10px] text-amber-400/70 mt-0.5">Ook je markt zit onder de algemene norm — dit is het gat tot wat er al aantoonbaar haalbaar is.</p>
        )}
      </div>
      <div className="text-right flex-shrink-0">
        {hasEur ? (
          <p className="text-sm font-bold tabular-nums text-red-400">{eurRange(g.gap_to_median_eur_low, g.gap_to_median_eur_high)}</p>
        ) : (
          <p className="text-[10px] text-white/20 italic">diagnose</p>
        )}
      </div>
    </div>
  );
}

function MarketBelowBenchmarkNotice() {
  return (
    <div className="border border-amber-500/20 bg-amber-500/5 rounded-xl p-4">
      <p className="text-xs text-amber-400/80 leading-relaxed">
        Je hele markt zit onder de algemene snelheidsnorm van 2,5s. Het bedrag hieronder is bewust het gat tot wat je markt al haalt — niet tot een abstracte norm die niemand in jouw markt haalt.
      </p>
    </div>
  );
}

function HeroGap({ data }: { data: CompetitorBenchmarkData }) {
  const hasGap = data.gap_to_median_monthly_eur_low != null && data.gap_to_median_monthly_eur_high != null;
  const parts = eurRangeParts(data.gap_to_median_monthly_eur_low, data.gap_to_median_monthly_eur_high);
  const bestParts = eurRangeParts(data.gap_to_best_monthly_eur_low, data.gap_to_best_monthly_eur_high);

  if (!hasGap) {
    return (
      <p className="text-white/40 mt-4 text-sm">
        Onvoldoende gemeten concurrenten om een marktgat in euro's te berekenen — zie de vergelijkingstabel hieronder voor de ruwe cijfers.
      </p>
    );
  }

  return (
    <div className="mt-6 flex flex-wrap gap-6">
      <div>
        <p className="text-5xl font-black text-red-400 tabular-nums leading-none">
          {parts.lead}
          {parts.tail && <span className="text-2xl font-bold text-red-400/60 ml-2">{parts.tail}</span>}
        </p>
        <p className="text-sm text-white/40 mt-2">gat tot marktmediaan, per maand</p>
      </div>
      {data.gap_to_best_monthly_eur_high != null && (
        <div>
          <p className="text-3xl font-bold text-red-300/60 tabular-nums leading-none">
            {bestParts.lead}
            {bestParts.tail && <span className="text-lg font-bold text-red-300/40 ml-2">{bestParts.tail}</span>}
          </p>
          <p className="text-sm text-white/40 mt-2">gat tot de snelste in je markt</p>
        </div>
      )}
    </div>
  );
}

function LoadingState({ status }: { status: CompetitorBenchmarkStatusResponse | null }) {
  const label = status ? PHASE_LABELS_NL[status.status] ?? "Bezig" : "Marktvergelijking wordt gestart…";
  return (
    <div className="min-h-screen bg-[#0e1017] flex items-center justify-center">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-[#c5a96f]/30 border-t-[#c5a96f] rounded-full animate-spin mx-auto mb-4" />
        <p className="text-sm text-white/40">{label}…</p>
        {status && status.total_count > 0 && (
          <p className="text-xs text-white/25 mt-2">{status.measured_count} / {status.total_count} concurrenten gemeten</p>
        )}
      </div>
    </div>
  );
}

export default function MarktvergelijkingPage() {
  const { runId } = useParams<{ runId: string }>();
  const [status, setStatus] = useState<CompetitorBenchmarkStatusResponse | null>(null);
  const [data, setData] = useState<CompetitorBenchmarkData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!runId) return;
    let stopped = false;

    async function poll() {
      try {
        const s = await getCompetitorBenchmarkStatus(runId!);
        if (stopped) return;
        setStatus(s);

        if (s.status === "ready" || s.status === "insufficient_data") {
          const full = await getCompetitorBenchmark(runId!);
          if (stopped) return;
          setData(full.data ?? null);
          setLoading(false);
        } else if (s.status === "failed") {
          setError("De marktvergelijking is mislukt. Probeer het opnieuw.");
          setLoading(false);
        } else {
          setTimeout(poll, POLL_INTERVAL);
        }
      } catch {
        if (!stopped) setError("Kan de marktvergelijking niet laden.");
        setLoading(false);
      }
    }

    poll();
    return () => { stopped = true; };
  }, [runId]);

  if (loading) return <LoadingState status={status} />;
  if (error) {
    return (
      <div className="min-h-screen bg-[#0e1017] flex items-center justify-center">
        <p className="text-red-400 text-sm">{error}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="min-h-screen bg-[#0e1017] flex items-center justify-center">
        <p className="text-white/40 text-sm">Geen marktvergelijking beschikbaar.</p>
      </div>
    );
  }

  const priceableGaps = data.gaps.filter((g) => g.kind === "revenue");
  const diagnosticGaps = data.gaps.filter((g) => g.kind === "diagnostic");
  const lcpGap = data.gaps.find((g) => g.finding_id === "gap.lcp_mobile");
  const marketBelowBenchmark = data.market_is_also_below_benchmark || (lcpGap?.market_is_also_below_benchmark ?? false);

  return (
    <div className="min-h-screen bg-[#0e1017] text-white">
      <div className="border-b border-white/8 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-serif text-lg text-[#c5a96f]" style={{ fontFamily: "var(--font-serif)" }}>Tradual</span>
          <span className="text-white/20 text-xs">Marktvergelijking</span>
        </div>
        <p className="text-xs text-white/30 truncate max-w-[240px]">{data.store_domain}</p>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-12 space-y-10">

        <div>
          <p className="text-xs text-white/30 uppercase tracking-widest mb-3">Hoe sta jij ervoor t.o.v. je markt?</p>
          <h1 className="text-3xl font-bold text-white mb-1" style={{ fontFamily: "var(--font-serif)" }}>
            {data.store_domain}
          </h1>
          <HeroGap data={data} />
        </div>

        {marketBelowBenchmark && <MarketBelowBenchmarkNotice />}

        <CoverageNotice data={data} />

        {data.overall_relative_score != null && (
          <div>
            <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-3">
              Score t.o.v. je markt — {Math.round(data.overall_relative_score)}/100
            </p>
            <LayerScoreCards layerScores={data.layer_scores} />
          </div>
        )}

        {priceableGaps.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-3">Geprijsde gaten t.o.v. je markt</p>
            <div className="border border-white/10 rounded-xl px-5 py-2">
              {priceableGaps.map((g) => (
                <GapMetricRow key={g.finding_id} g={g} />
              ))}
            </div>
          </div>
        )}

        {diagnosticGaps.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-3">Te verifiëren signalen</p>
            <div className="border border-white/10 rounded-xl px-5 py-2">
              {diagnosticGaps.map((g) => (
                <GapMetricRow key={g.finding_id} g={g} />
              ))}
            </div>
          </div>
        )}

        <div>
          <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-3">Concurrenten in deze vergelijking</p>
          <CompetitorRoster roster={data.roster} />
        </div>

        <div>
          <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-3">Volledige vergelijking per laag</p>
          <ComparisonTable comparisons={data.comparisons} />
        </div>

        {data.methodology_note_nl && (
          <p className="text-[11px] text-white/20 italic leading-relaxed">{data.methodology_note_nl}</p>
        )}

        <div className="border border-[#c5a96f]/20 rounded-2xl p-6 text-center bg-[#c5a96f]/5">
          <p className="text-sm font-semibold text-white mb-1" style={{ fontFamily: "var(--font-serif)" }}>
            Je markt haalt dit al — jij kunt het ook
          </p>
          <p className="text-xs text-white/40 mb-4">
            Dit gat is niet abstract: het is wat concurrenten in jouw eigen markt vandaag al leveren.
          </p>
          <a
            href="https://tradual.com/contact"
            className="inline-block px-6 py-2.5 bg-[#c5a96f] text-[#1a1f2e] text-sm font-semibold rounded-lg hover:bg-[#d4b87e] transition-colors"
          >
            Plan een strategiegesprek
          </a>
        </div>
      </div>
    </div>
  );
}

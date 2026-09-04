import { useEffect, useState } from "react";
import { useParams } from "react-router";
import {
  NextStepsSection,
  relevantStepsFromBenchmark,
} from "~/components/NextSteps";
import HeroFigure from "~/components/report/HeroFigure";
import KpiTile from "~/components/report/KpiTile";
import Notice from "~/components/report/Notice";
import ReportCard from "~/components/report/ReportCard";
import ReportShell from "~/components/report/ReportShell";
import ReportSpinner from "~/components/report/ReportSpinner";
import SectionLabel from "~/components/report/SectionLabel";
import StatusPill from "~/components/report/StatusPill";
import type { PillTone } from "~/components/report/tone";
import { getCompetitorBenchmark, getCompetitorBenchmarkStatus } from "~/lib/api";
import { eurRange, eurRangeParts, formatMetricValue } from "~/lib/format";
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

function classificationLabel(c: string | null): string {
  switch (c) {
    case "direct": return "Directe concurrent";
    case "category": return "Categorie-concurrent";
    case "operator": return "Handmatig toegevoegd";
    default: return "";
  }
}

const MEASURE_STATUS: Record<string, { label: string; tone: PillTone }> = {
  ok: { label: "gemeten", tone: "ok" },
  partial: { label: "deels gemeten", tone: "warning" },
  unreachable: { label: "niet bereikbaar", tone: "muted" },
  timeout: { label: "timeout", tone: "muted" },
};

function MeasureStatusPill({ status }: { status: CompetitorRosterEntry["measure_status"] }) {
  const m = MEASURE_STATUS[status] ?? MEASURE_STATUS.unreachable;
  return <StatusPill tone={m.tone}>{m.label}</StatusPill>;
}

function CoverageNotice({ data }: { data: CompetitorBenchmarkData }) {
  const total = data.roster.length;
  const measured = data.roster.filter((r) => r.measure_status === "ok" || r.measure_status === "partial").length;
  // The server phrases the disclosure now (added / removed / both). Runs from before
  // that field existed fall back to the single generic sentence they shipped with.
  const curationNote =
    data.curation_note_nl ??
    (data.manually_curated
      ? "Deze selectie is handmatig samengesteld door Tradual — geen automatisch marktgemiddelde."
      : null);
  return (
    <ReportCard className="p-4">
      <p className="text-xs text-gray-500 leading-relaxed">
        Gebaseerd op <span className="text-gray-900 font-medium">{measured} van de {total}</span> geselecteerde concurrenten die succesvol gemeten konden worden.
        {curationNote && <span className="text-gray-700"> {curationNote}</span>}
      </p>
    </ReportCard>
  );
}

function CompetitorRoster({ roster }: { roster: CompetitorRosterEntry[] }) {
  return (
    <ReportCard className="overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50">
            {["Domein", "Type", "Reden", "Status", "Gemeten op"].map((h) => (
              <th key={h} className="text-left py-2 px-3 text-gray-400 font-medium uppercase tracking-wide text-[10px]">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {roster.map((r) => (
            <tr key={r.domain}>
              <td className="py-2 px-3 text-gray-900 font-medium">{r.domain}</td>
              <td className="py-2 px-3 text-gray-500">{classificationLabel(r.classification)}</td>
              <td className="py-2 px-3 text-gray-500 max-w-[280px]">{r.reason_nl}</td>
              <td className="py-2 px-3"><MeasureStatusPill status={r.measure_status} /></td>
              <td className="py-2 px-3 text-gray-400 tabular-nums whitespace-nowrap">
                {r.measured_at ? new Date(r.measured_at).toLocaleDateString("nl-NL") : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </ReportCard>
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
    <div className="py-2.5 border-b border-gray-100 last:border-0">
      <div className="flex items-start justify-between gap-4">
        <p className="text-xs font-medium text-gray-700 flex-shrink-0">{m.label_nl}</p>
        <div className="flex items-center gap-4 text-right flex-shrink-0">
          <div className="w-16">
            <p className={`text-sm font-bold tabular-nums ${storeBeatsMedian === false ? "text-[#EF4444]" : storeBeatsMedian === true ? "text-[#0a2f23]" : "text-gray-500"}`}>
              {m.store_measured ? formatMetricValue(m.store_value, m.unit) : "—"}
            </p>
            <p className="text-[9px] text-gray-400 uppercase tracking-wide">jij</p>
          </div>
          <div className="w-16">
            <p className="text-sm text-gray-700 tabular-nums">{formatMetricValue(m.median, m.unit)}</p>
            <p className="text-[9px] text-gray-400 uppercase tracking-wide">mediaan</p>
          </div>
          <div className="w-20">
            <p className="text-sm text-gray-500 tabular-nums">
              {formatMetricValue(m.best, m.unit)}
              {m.best_domain && <span className="text-[9px] text-gray-400 ml-1">({m.best_domain})</span>}
            </p>
            <p className="text-[9px] text-gray-400 uppercase tracking-wide">beste</p>
          </div>
          <div className="w-14">
            {/* Rank was gold. At 14px gold sits at ~2:1 on #FAFAF8, so it can't stay. */}
            <p className="text-sm font-semibold text-gray-900 tabular-nums">
              {storeIsBest ? "1e" : m.store_rank && m.domains_ranked ? `${m.store_rank}e/${m.domains_ranked}` : "—"}
            </p>
            <p className="text-[9px] text-gray-400 uppercase tracking-wide">positie</p>
          </div>
        </div>
      </div>
      <p className="text-[10px] text-gray-500 mt-1">{m.coverage_label_nl}</p>
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
          <ReportCard key={layer} className="px-5 py-4">
            <SectionLabel className="mb-2">{LAYER_NAMES[layer]}</SectionLabel>
            {metrics.map((m) => (
              <MetricComparisonRow key={m.key} m={m} />
            ))}
          </ReportCard>
        );
      })}
    </div>
  );
}

function LayerScoreCards({ layerScores }: { layerScores: LayerScore[] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
      {layerScores.map((ls) => (
        <ReportCard key={ls.layer} className="p-4">
          <KpiTile
            tone="accent"
            align="center"
            value={ls.relative_score != null ? Math.round(ls.relative_score) : "—"}
            label={ls.name_nl}
          />
        </ReportCard>
      ))}
    </div>
  );
}

function GapMetricRow({ g }: { g: GapFinding }) {
  const hasEur = g.gap_to_median_eur_low != null && g.gap_to_median_eur_high != null;
  return (
    <div className="flex gap-3 py-2.5 border-b border-gray-100 last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-gray-700">{g.label_nl}</p>
        {g.note_nl && <p className="text-[11px] text-gray-500 mt-0.5">{g.note_nl}</p>}
        {g.market_is_also_below_benchmark && (
          <p className="text-[10px] text-amber-600 mt-0.5">Ook je markt zit onder de algemene norm — dit is het gat tot wat er al aantoonbaar haalbaar is.</p>
        )}
      </div>
      <div className="text-right flex-shrink-0">
        {hasEur ? (
          <p className="text-sm font-bold tabular-nums text-[#EF4444]">{eurRange(g.gap_to_median_eur_low, g.gap_to_median_eur_high)}</p>
        ) : (
          <p className="text-[10px] text-gray-400 italic">diagnose</p>
        )}
      </div>
    </div>
  );
}

function MarketBelowBenchmarkNotice() {
  return (
    <Notice tone="warning">
      Je hele markt zit onder de algemene snelheidsnorm van 2,5s. Het bedrag hieronder is bewust het gat tot wat je markt al haalt — niet tot een abstracte norm die niemand in jouw markt haalt.
    </Notice>
  );
}

function HeroGap({ data }: { data: CompetitorBenchmarkData }) {
  const hasGap = data.gap_to_median_monthly_eur_low != null && data.gap_to_median_monthly_eur_high != null;
  const parts = eurRangeParts(data.gap_to_median_monthly_eur_low, data.gap_to_median_monthly_eur_high);
  const bestParts = eurRangeParts(data.gap_to_best_monthly_eur_low, data.gap_to_best_monthly_eur_high);

  if (!hasGap) {
    return (
      <p className="text-gray-500 mt-4 text-sm">
        Onvoldoende gemeten concurrenten om een marktgat in euro's te berekenen — zie de vergelijkingstabel hieronder voor de ruwe cijfers.
      </p>
    );
  }

  return (
    <div className="mt-6 flex flex-wrap gap-6">
      <HeroFigure parts={parts} size="xl" label="gat tot marktmediaan, per maand" />
      {data.gap_to_best_monthly_eur_high != null && (
        <HeroFigure parts={bestParts} size="md" label="gat tot de snelste in je markt" />
      )}
    </div>
  );
}

function Cta() {
  return (
    <div className="print-exact bg-[#0a2f23] text-white rounded-2xl p-8 text-center">
      <p className="text-lg font-semibold mb-2" style={{ fontFamily: "var(--font-serif)" }}>
        Je markt haalt dit al — jij kunt het ook
      </p>
      <p className="text-sm text-white/70 mb-6">
        Dit gat is niet abstract: het is wat concurrenten in jouw eigen markt vandaag al leveren.
      </p>
      <a
        href="https://tradual.com/contact"
        className="inline-block bg-tradual-accent text-tradual-primary px-8 py-3 font-medium hover:opacity-90 transition"
      >
        Plan een strategiegesprek
      </a>
    </div>
  );
}

function LoadingState({ status }: { status: CompetitorBenchmarkStatusResponse | null }) {
  const label = status ? PHASE_LABELS_NL[status.status] ?? "Bezig" : "Marktvergelijking wordt gestart…";
  return (
    <ReportShell>
      <ReportSpinner
        label={`${label}…`}
        sublabel={
          status && status.total_count > 0
            ? `${status.measured_count} / ${status.total_count} concurrenten gemeten`
            : undefined
        }
      />
    </ReportShell>
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
      <ReportShell>
        <div className="max-w-3xl mx-auto">
          <Notice tone="danger">{error}</Notice>
        </div>
      </ReportShell>
    );
  }
  if (!data) {
    return (
      <ReportShell>
        <div className="max-w-3xl mx-auto">
          <Notice>Geen marktvergelijking beschikbaar.</Notice>
        </div>
      </ReportShell>
    );
  }

  const priceableGaps = data.gaps.filter((g) => g.kind === "revenue");
  const diagnosticGaps = data.gaps.filter((g) => g.kind === "diagnostic");
  const lcpGap = data.gaps.find((g) => g.finding_id === "gap.lcp_mobile");
  const marketBelowBenchmark = data.market_is_also_below_benchmark || (lcpGap?.market_is_also_below_benchmark ?? false);

  return (
    <ReportShell>
      <div className="max-w-3xl mx-auto space-y-10">

        {/* Hero — the store domain and the report type used to live in a custom top bar */}
        <div>
          <SectionLabel>Hoe sta jij ervoor t.o.v. je markt?</SectionLabel>
          <h1 className="text-3xl font-bold text-gray-900 mb-1" style={{ fontFamily: "var(--font-serif)" }}>
            {data.store_domain}
          </h1>
          <p className="text-sm text-gray-500">Marktvergelijking</p>
          <HeroGap data={data} />
        </div>

        {marketBelowBenchmark && <MarketBelowBenchmarkNotice />}

        <CoverageNotice data={data} />

        {data.overall_relative_score != null && (
          <div>
            <SectionLabel>
              Score t.o.v. je markt — {Math.round(data.overall_relative_score)}/100
            </SectionLabel>
            <LayerScoreCards layerScores={data.layer_scores} />
          </div>
        )}

        {priceableGaps.length > 0 && (
          <div>
            <SectionLabel>Geprijsde gaten t.o.v. je markt</SectionLabel>
            <ReportCard className="px-5 py-2">
              {priceableGaps.map((g) => (
                <GapMetricRow key={g.finding_id} g={g} />
              ))}
            </ReportCard>
          </div>
        )}

        {diagnosticGaps.length > 0 && (
          <div>
            <SectionLabel>Te verifiëren signalen</SectionLabel>
            <ReportCard className="px-5 py-2">
              {diagnosticGaps.map((g) => (
                <GapMetricRow key={g.finding_id} g={g} />
              ))}
            </ReportCard>
          </div>
        )}

        <div>
          <SectionLabel>Concurrenten in deze vergelijking</SectionLabel>
          <CompetitorRoster roster={data.roster} />
        </div>

        <div>
          <SectionLabel>Volledige vergelijking per laag</SectionLabel>
          <ComparisonTable comparisons={data.comparisons} />
        </div>

        <NextStepsSection relevant={relevantStepsFromBenchmark(data)} doneKey="audit" />

        {data.methodology_note_nl && (
          <p className="text-[11px] text-gray-500 italic leading-relaxed">{data.methodology_note_nl}</p>
        )}

        <Cta />
      </div>
    </ReportShell>
  );
}

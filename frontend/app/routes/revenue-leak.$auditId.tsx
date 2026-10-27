import { useEffect, useState } from "react";
import { useParams } from "react-router";
import ActionList from "~/components/report/ActionList";
import AdTrafficImpact from "~/components/report/AdTrafficImpact";
import AssumptionsSection from "~/components/report/AssumptionsSection";
import FunnelWalkSection from "~/components/report/FunnelWalkSection";
import GoodSignals from "~/components/report/GoodSignals";
import HeroFigure from "~/components/report/HeroFigure";
import Notice from "~/components/report/Notice";
import ReportCard from "~/components/report/ReportCard";
import ReportShell from "~/components/report/ReportShell";
import ReportSpinner from "~/components/report/ReportSpinner";
import RoadmapSection from "~/components/report/RoadmapSection";
import SectionLabel from "~/components/report/SectionLabel";
import StatusPill from "~/components/report/StatusPill";
import TopLeaks from "~/components/report/TopLeaks";
import { getClientAuditReport, getFullAuditStatus } from "~/lib/api";
import { conflictTitle, eur, eurRange, eurRangeParts, severityByShare } from "~/lib/format";
import type {
  ClientAuditReport,
  ClientCitation,
  ClientRevenueLeakReport,
  DataConflict,
  FullAuditStatusResponse,
  ModelWarning,
  RevenueLeakLayer,
  RevenueLeakMetric,
} from "~/lib/types";
import { BOOK_A_CALL_URL } from "~/lib/links";

const POLL_INTERVAL = 3000;

// --- v1/v2 compatibility helpers ---------------------------------------------------
// Reports computed before the funnel-model rewrite (no `model_version`) only carry a
// single `*_loss_eur` value. Reports computed after it carry a real low/high range.
// These helpers return a range either way — for a v1 report, low === high, and
// `eurRange`/`eurRangeParts` collapse that to a single displayed value automatically.
function metricRange(m: RevenueLeakMetric): { low: number | null; high: number | null } {
  if (m.monthly_loss_eur_low != null && m.monthly_loss_eur_high != null) {
    return { low: m.monthly_loss_eur_low, high: m.monthly_loss_eur_high };
  }
  return { low: m.monthly_loss_eur ?? null, high: m.monthly_loss_eur ?? null };
}
function metricAnnualRange(m: RevenueLeakMetric): { low: number | null; high: number | null } {
  if (m.annual_loss_eur_low != null && m.annual_loss_eur_high != null) {
    return { low: m.annual_loss_eur_low, high: m.annual_loss_eur_high };
  }
  return { low: m.annual_loss_eur ?? null, high: m.annual_loss_eur ?? null };
}
function layerRange(l: RevenueLeakLayer): { low: number | null; high: number | null } {
  if (l.est_monthly_loss_eur_low != null && l.est_monthly_loss_eur_high != null) {
    return { low: l.est_monthly_loss_eur_low, high: l.est_monthly_loss_eur_high };
  }
  return { low: l.est_monthly_loss_eur ?? null, high: l.est_monthly_loss_eur ?? null };
}
function layerAnnualRange(l: RevenueLeakLayer): { low: number | null; high: number | null } {
  if (l.est_annual_loss_eur_low != null && l.est_annual_loss_eur_high != null) {
    return { low: l.est_annual_loss_eur_low, high: l.est_annual_loss_eur_high };
  }
  return { low: l.est_annual_loss_eur ?? null, high: l.est_annual_loss_eur ?? null };
}
function reportMonthlyRange(data: ClientRevenueLeakReport): { low: number; high: number } {
  if (data.total_monthly_loss_eur_low != null && data.total_monthly_loss_eur_high != null) {
    return { low: data.total_monthly_loss_eur_low, high: data.total_monthly_loss_eur_high };
  }
  const v = data.total_monthly_loss_eur || 0;
  return { low: v, high: v };
}
function reportAnnualRange(data: ClientRevenueLeakReport): { low: number; high: number } {
  if (data.total_annual_loss_eur_low != null && data.total_annual_loss_eur_high != null) {
    return { low: data.total_annual_loss_eur_low, high: data.total_annual_loss_eur_high };
  }
  const v = data.total_annual_loss_eur || 0;
  return { low: v, high: v };
}
function PriorityDot({ priority }: { priority: RevenueLeakMetric["priority"] }) {
  // Bumped a step darker than the dark theme used: a 6px dot in `orange-400` /
  // `yellow-400` all but disappears on #FAFAF8.
  const colors: Record<RevenueLeakMetric["priority"], string> = {
    critical: "bg-[#EF4444]",
    high: "bg-orange-500",
    medium: "bg-amber-500",
    low: "bg-gray-300",
  };
  return <span className={`inline-block w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${colors[priority]}`} />;
}

function DataConflictBanner({ conflicts }: { conflicts: DataConflict[] }) {
  if (conflicts.length === 0) return null;
  return (
    <div className="space-y-2">
      {conflicts.map((c, i) => (
        <Notice
          key={i}
          tone={c.severity === "critical" ? "danger" : "warning"}
          title={conflictTitle(c)}
        >
          {c.message_nl}
        </Notice>
      ))}
    </div>
  );
}

function ModelWarnings({ warnings }: { warnings: ModelWarning[] }) {
  if (warnings.length === 0) return null;
  return (
    <Notice tone="warning">
      <div className="space-y-1.5">
        {warnings.map((w, i) => (
          <p key={i} className="text-[11px] leading-relaxed">⚠ {w.detail}</p>
        ))}
      </div>
    </Notice>
  );
}

const CONFIDENCE_NL = { high: "hoog", medium: "redelijk", low: "laag" } as const;

function pctRange(low: number | null | undefined, high: number | null | undefined): string | null {
  if (low == null || high == null) return null;
  const f = (n: number) => `${(n * 100).toLocaleString("nl-NL", { maximumFractionDigits: 1 })}%`;
  return low === high ? f(low) : `${f(low)}–${f(high)}`;
}

/** "How was this number built?" — only for metrics that carry the funnel-model
 * bookkeeping (v2 reports); v1 rows have nothing to show here. */
function MetricBasis({ m, citations }: { m: RevenueLeakMetric; citations: Record<string, ClientCitation> }) {
  const uplift = pctRange(m.uplift_low, m.uplift_high);
  const citation = m.citation ? citations[m.citation] : undefined;
  const rows: [string, string][] = [];
  if (m.exposure_share != null) rows.push(["Deel van de omzet dat dit raakt", pctRange(m.exposure_share, m.exposure_share)!]);
  if (uplift) rows.push(["Geschat effect op conversie", uplift]);
  if (m.confidence) rows.push(["Zekerheid", CONFIDENCE_NL[m.confidence]]);
  if (citation) rows.push(["Bron", citation.verified ? citation.source : `${citation.source} (nog niet onafhankelijk geverifieerd)`]);
  if (m.pages_affected && m.pages_affected.length > 0) rows.push(["Pagina's", m.pages_affected.join(", ")]);
  if (rows.length === 0) return null;
  return (
    <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[10px] text-gray-500">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt>{k}</dt>
          <dd className="text-gray-700">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function MetricRow({
  m,
  funnelRevenue,
  citations,
}: {
  m: RevenueLeakMetric;
  funnelRevenue: number | null;
  citations: Record<string, ClientCitation>;
}) {
  const [showBasis, setShowBasis] = useState(false);
  const hasBasis = m.exposure_share != null || m.uplift_high != null || m.citation != null;
  const { low, high } = metricRange(m);
  const { low: annualLow, high: annualHigh } = metricAnnualRange(m);
  const share = high != null && funnelRevenue ? high / funnelRevenue : null;
  const severity = severityByShare(share, 0.01, 0.03);

  return (
    <div className="flex gap-3 py-2.5 border-b border-gray-100 last:border-0">
      <PriorityDot priority={m.priority} />
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium text-gray-700">{m.metric}</p>
            {m.signal && <p className="text-[11px] text-gray-500 mt-0.5">{m.signal}</p>}
          </div>
          <div className="text-right flex-shrink-0">
            {m.verify_manually ? (
              <p className="text-[10px] text-gray-500 italic border border-gray-200 rounded px-1.5 py-0.5 inline-block">nog te bevestigen</p>
            ) : low != null && high != null ? (
              <>
                <p className={`text-sm font-bold tabular-nums ${severity === "critical" ? "text-[#EF4444]" : severity === "warning" ? "text-amber-600" : "text-gray-400"}`}>
                  {high === 0 ? "—" : eurRange(low, high)}
                </p>
                {high > 0 && annualLow != null && annualHigh != null && (
                  <p className="text-[10px] text-gray-500 tabular-nums">{eurRange(annualLow, annualHigh)}/jr</p>
                )}
              </>
            ) : (
              <p className="text-[10px] text-gray-400 italic">{m.kind === "diagnostic" ? "diagnose" : m.kind === "restatement" ? "herformulering" : "strategisch"}</p>
            )}
          </div>
        </div>
        <p className="text-[10px] text-gray-500 mt-1 leading-snug">{m.basis || m.calculation_note}</p>
        {hasBasis && (
          <button
            onClick={() => setShowBasis((o) => !o)}
            className="mt-1 text-[10px] font-medium text-[#0a2f23] underline underline-offset-2"
          >
            {showBasis ? "Onderbouwing verbergen" : "Onderbouwing"}
          </button>
        )}
        {showBasis && <MetricBasis m={m} citations={citations} />}
      </div>
    </div>
  );
}

function LayerCard({
  layer,
  funnelRevenue,
  citations,
}: {
  layer: RevenueLeakLayer;
  funnelRevenue: number | null;
  citations: Record<string, ClientCitation>;
}) {
  const [open, setOpen] = useState(false);
  const { low, high } = layerRange(layer);
  const isNa = low == null || high == null;
  const kind = layer.kind ?? "revenue";

  return (
    <ReportCard className="overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full text-left px-5 py-4 flex items-center gap-4 hover:bg-gray-50 transition-colors"
      >
        <span className="text-xs font-mono text-gray-400 w-4">{layer.layer}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold text-gray-900">{layer.name}</span>
            {!isNa && high! > 0 && (
              <span className={`text-xs font-bold tabular-nums ${kind === "cost" ? "text-amber-600" : high! > 3000 ? "text-[#EF4444]" : "text-orange-600"}`}>
                {eurRange(low, high)}/mnd
              </span>
            )}
            {(isNa || kind === "diagnostic" || kind === "restatement" || kind === "readiness") && (
              <span className="text-xs text-gray-500 font-medium">
                {kind === "restatement" ? "Herformulering" : kind === "diagnostic" ? "Diagnose" : "Strategisch"}
              </span>
            )}
            {layer.unpriced_finding_count != null && layer.unpriced_finding_count > 0 && (
              <span className="text-[10px] text-gray-500">+{layer.unpriced_finding_count} nog te bevestigen</span>
            )}
          </div>
          <p className="text-xs text-gray-500 mt-0.5 leading-snug">{layer.core_question}</p>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-xs text-gray-500 hidden sm:block">{layer.leads_to}</span>
          <span className="text-gray-400 text-xs">{open ? "▲" : "▼"}</span>
        </div>
      </button>
      {open && layer.metrics.length > 0 && (
        <div className="border-t border-gray-100 px-5 py-1 bg-gray-50">
          {layer.metrics.map((m) => (
            <MetricRow key={m.metric} m={m} funnelRevenue={funnelRevenue} citations={citations} />
          ))}
        </div>
      )}
    </ReportCard>
  );
}

function TotalsTable({ data }: { data: ClientRevenueLeakReport }) {
  const isV2 = data.model_version != null;
  const direct = reportMonthlyRange(data);
  const directAnnual = reportAnnualRange(data);

  // Legacy (v1) fallback: no low/high on the report, so recompute a plain sum from
  // the layers the way the original component did.
  const legacyDirectLayers = data.layers.filter((l) => [1, 2, 3].includes(l.layer));
  const legacyDirectMonthly = isV2 ? direct.low : legacyDirectLayers.reduce((s, l) => s + (l.est_monthly_loss_eur || 0), 0);
  const legacyDirectAnnual = isV2 ? directAnnual.low : legacyDirectLayers.reduce((s, l) => s + (l.est_annual_loss_eur || 0), 0);
  const legacyAllMonetary = data.layers.filter((l) => l.est_monthly_loss_eur != null);
  const legacyTotalMonthly = legacyAllMonetary.reduce((s, l) => s + (l.est_monthly_loss_eur || 0), 0);
  const legacyTotalAnnual = legacyAllMonetary.reduce((s, l) => s + (l.est_annual_loss_eur || 0), 0);

  return (
    <ReportCard className="overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50">
            {["Laag", "Naam", "/mnd", "/jaar"].map((h) => (
              <th key={h} className="text-left py-2 px-3 text-gray-400 font-medium uppercase tracking-wide text-[10px]">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {data.layers.map((l) => {
            const { low, high } = layerRange(l);
            const { low: aLow, high: aHigh } = layerAnnualRange(l);
            const hasData = low != null && high != null;
            return (
              <tr key={l.layer}>
                <td className="py-2 px-3 text-gray-400 font-mono">{l.layer}</td>
                <td className="py-2 px-3 text-gray-700">{l.name}</td>
                <td className="py-2 px-3 tabular-nums font-semibold whitespace-nowrap">
                  {hasData
                    ? <span className={high! > 0 ? (l.kind === "cost" ? "text-amber-600" : "text-orange-600") : "text-gray-400"}>{high! > 0 ? eurRange(low, high) : "—"}</span>
                    : <span className="text-gray-400 italic text-[10px]">n.v.t.</span>
                  }
                </td>
                <td className="py-2 px-3 tabular-nums text-gray-500 whitespace-nowrap">
                  {aLow != null && aHigh != null && aHigh > 0 ? eurRange(aLow, aHigh) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot className="border-t border-gray-200">
          <tr className="bg-gray-50">
            <td colSpan={2} className="py-2.5 px-3 text-xs text-gray-500">{isV2 ? "Totaal geschat verlies" : "Directe lekkage (L1+L2+L3)"}</td>
            <td className="py-2.5 px-3 font-bold text-[#EF4444] tabular-nums whitespace-nowrap">
              {isV2 ? eurRange(direct.low, direct.high) : eur(legacyDirectMonthly)}
            </td>
            <td className="py-2.5 px-3 text-gray-700 tabular-nums whitespace-nowrap">
              {isV2 ? eurRange(directAnnual.low, directAnnual.high) : eur(legacyDirectAnnual)}
            </td>
          </tr>
          {!isV2 && (
            <tr className="bg-gray-100">
              <td colSpan={2} className="py-2.5 px-3 text-xs text-gray-700 font-semibold">Totaal incl. efficiëntie (L1–L4)</td>
              <td className="py-2.5 px-3 font-bold text-[#EF4444] tabular-nums">{eur(legacyTotalMonthly)}</td>
              <td className="py-2.5 px-3 text-gray-700 tabular-nums">{eur(legacyTotalAnnual)}</td>
            </tr>
          )}
        </tfoot>
      </table>
    </ReportCard>
  );
}

function Cta() {
  return (
    <div className="print-exact bg-[#0a2f23] text-white rounded-2xl p-8 text-center">
      <p className="text-lg font-semibold mb-2" style={{ fontFamily: "var(--font-serif)" }}>
        Klaar voor de volgende stap?
      </p>
      <p className="text-sm text-white/70 mb-6">
        Stap 1 heb je net gehad. Laten we bespreken wat voor jouw situatie het meest oplevert.
      </p>
      <a
        href={BOOK_A_CALL_URL}
        className="inline-block bg-tradual-accent text-tradual-primary px-8 py-3 font-medium hover:opacity-90 transition"
      >
        Plan een strategiegesprek
      </a>
    </div>
  );
}

function LoadingState() {
  return (
    <ReportShell>
      <ReportSpinner label="Audit wordt uitgevoerd…" />
    </ReportShell>
  );
}

export default function RevenueLeakAuditPage() {
  const { auditId } = useParams<{ auditId: string }>();
  const [status, setStatus] = useState<FullAuditStatusResponse | null>(null);
  const [report, setReport] = useState<ClientAuditReport | null>(null);
  const [storeUrl, setStoreUrl] = useState<string>("");
  const [companyName, setCompanyName] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!auditId) return;
    let stopped = false;

    async function poll() {
      try {
        const s = await getFullAuditStatus(auditId!);
        if (stopped) return;
        setStatus(s);
        setStoreUrl(s.store_url);

        if (s.status === "ready_for_review") {
          const report = await getClientAuditReport(auditId!);
          if (stopped) return;
          setReport(report);
          setCompanyName(report.company_name ?? s.store_url);
          setLoading(false);
        } else if (s.status === "failed" || s.status === "cancelled") {
          setError(s.status === "failed" ? "De audit is mislukt. Probeer het opnieuw." : "Deze audit is gestopt; er is geen rapport.");
          setLoading(false);
        } else {
          setTimeout(poll, POLL_INTERVAL);
        }
      } catch {
        if (!stopped) setError("Kan de audit niet laden.");
        setLoading(false);
      }
    }

    poll();
    return () => { stopped = true; };
  }, [auditId]);

  if (loading) return <LoadingState />;
  if (error) {
    return (
      <ReportShell>
        <div className="max-w-3xl mx-auto">
          <Notice tone="danger">{error}</Notice>
        </div>
      </ReportShell>
    );
  }
  const data = report?.revenue_leak ?? null;
  if (!report || !data) {
    return (
      <ReportShell>
        <div className="max-w-3xl mx-auto">
          <Notice>Geen revenue leak data beschikbaar.</Notice>
        </div>
      </ReportShell>
    );
  }

  const { low: totalLow, high: totalHigh } = reportMonthlyRange(data);
  const { low: totalAnnualLow, high: totalAnnualHigh } = reportAnnualRange(data);
  const heroParts = eurRangeParts(totalLow, totalHigh);
  const heroAnnualParts = eurRangeParts(totalAnnualLow, totalAnnualHigh);
  const funnelRevenue = data.funnel?.monthly_revenue_eur ?? null;
  const conflicts = data.data_conflicts ?? [];
  const warnings = data.model_warnings ?? [];
  const serankingTraffic = report.seranking_traffic;
  const roadmap = report.roadmap;
  const citations = Object.fromEntries(report.citations.map((c) => [c.key, c]));
  const scannedOn = report.completed_at
    ? new Date(report.completed_at).toLocaleDateString("nl-NL", { day: "numeric", month: "long", year: "numeric" })
    : null;

  // Story first (cost → top leaks → what goes well → plan), every number's working in
  // the appendix. The CEO-trigger framework stays out: it's sales framing, not findings.
  return (
    <ReportShell>
      <div className="max-w-3xl mx-auto space-y-10">

        {/* 1. What it costs */}
        <div>
          <SectionLabel>Rapport voor</SectionLabel>
          <h1 className="text-3xl font-bold text-gray-900 mb-1" style={{ fontFamily: "var(--font-serif)" }}>
            {companyName || storeUrl}
          </h1>
          <p className="text-sm text-gray-500 truncate">Revenue Leak Audit · {storeUrl}</p>
          {totalHigh > 0 ? (
            <div className="mt-6 flex flex-wrap gap-6">
              <HeroFigure parts={heroParts} size="xl" label="geschat verlies per maand" />
              <HeroFigure parts={heroAnnualParts} size="lg" label="per jaar" />
            </div>
          ) : (
            <p className="text-gray-500 mt-4 text-sm">Geen direct meetbaar verlies gevonden.</p>
          )}
          <div className="flex flex-wrap items-center gap-2 mt-5">
            {scannedOn && <StatusPill tone="muted" size="md">Gemeten op {scannedOn}</StatusPill>}
            {serankingTraffic ? (
              <StatusPill tone="ok" size="md">
                Bezoekersdata via SE Ranking — {(serankingTraffic.monthly_organic_sessions + serankingTraffic.monthly_paid_sessions).toLocaleString("nl-NL")}/mnd
              </StatusPill>
            ) : (
              <StatusPill tone="warning" size="md">Bezoekersaantal geschat</StatusPill>
            )}
            {report.funnel_walk && <StatusPill tone="ok" size="md">Checkout zelf doorlopen</StatusPill>}
          </div>
        </div>

        {roadmap?.executive_summary && (
          <ReportCard className="p-5">
            <SectionLabel className="mb-2">In het kort</SectionLabel>
            <p className="text-sm text-gray-800 leading-relaxed">{roadmap.executive_summary}</p>
            {roadmap.north_star_metric && (
              <p className="text-xs text-gray-500 mt-3">
                Het cijfer om op te sturen: <span className="text-gray-800 font-medium">{roadmap.north_star_metric}</span>
              </p>
            )}
          </ReportCard>
        )}

        {/* 2. Top leaks, with evidence */}
        <TopLeaks auditId={report.id} actions={data.actions ?? []} findings={data.findings ?? []} />

        {/* 3. What goes well */}
        <GoodSignals layers={data.layers} />

        {/* 4. How we fix it */}
        {roadmap && <RoadmapSection roadmap={roadmap} />}

        <Cta />

        {/* 5. Appendix — everything behind the numbers, closed by default (open in print) */}
        <details className="report-appendix group">
          <summary className="cursor-pointer list-none flex items-center justify-between border-t border-gray-200 pt-6">
            <span className="text-lg font-semibold text-gray-900" style={{ fontFamily: "var(--font-serif)" }}>
              Bijlage: volledige onderbouwing
            </span>
            <span className="text-xs text-gray-500 group-open:hidden">Openen ▼</span>
            <span className="text-xs text-gray-500 hidden group-open:inline">Sluiten ▲</span>
          </summary>
          <div className="space-y-10 mt-6">
            <DataConflictBanner conflicts={conflicts} />

            <ActionList actions={data.actions ?? []} />

            {report.funnel_walk && <FunnelWalkSection auditId={report.id} walk={report.funnel_walk} />}

            {report.ad_traffic_impact && <AdTrafficImpact data={report.ad_traffic_impact} />}

            <div>
              <SectionLabel>Alle metingen per meetlaag</SectionLabel>
              <div className="space-y-2">
                {data.layers.map((layer) => (
                  <LayerCard key={layer.layer} layer={layer} funnelRevenue={funnelRevenue} citations={citations} />
                ))}
              </div>
            </div>

            <div>
              <SectionLabel>Totaal per meetlaag</SectionLabel>
              <TotalsTable data={data} />
            </div>

            <ModelWarnings warnings={warnings} />

            {report.assumptions.length > 0 && (
              <AssumptionsSection
                assumptions={report.assumptions}
                citations={report.citations}
                methodologyNote={report.methodology_note}
              />
            )}

            {/* Legacy (pre-funnel) reports have no assumptions table — keep their notes */}
            {report.assumptions.length === 0 && data.methodology_note && (
              <p className="text-[11px] text-gray-500 italic leading-relaxed">{data.methodology_note}</p>
            )}
          </div>
        </details>
      </div>
    </ReportShell>
  );
}

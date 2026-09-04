import { useEffect, useState } from "react";
import { useParams } from "react-router";
import {
  NextStepsSection,
  relevantStepsFromRevenueLeak,
} from "~/components/NextSteps";
import HeroFigure from "~/components/report/HeroFigure";
import KpiTile from "~/components/report/KpiTile";
import Notice from "~/components/report/Notice";
import ReportCard from "~/components/report/ReportCard";
import ReportShell from "~/components/report/ReportShell";
import ReportSpinner from "~/components/report/ReportSpinner";
import SectionLabel from "~/components/report/SectionLabel";
import StatusPill from "~/components/report/StatusPill";
import { getFullAudit, getFullAuditStatus } from "~/lib/api";
import { eur, eurRange, eurRangeParts, severityByShare } from "~/lib/format";
import type {
  CeoTriggerKpi,
  DataConflict,
  FullAuditStatusResponse,
  ModelWarning,
  RevenueLeakLayer,
  RevenueLeakMetric,
  RevenueLeakReport,
  RoiCalculation,
  SeRankingTraffic,
} from "~/lib/types";

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
function reportMonthlyRange(data: RevenueLeakReport): { low: number; high: number } {
  if (data.total_monthly_loss_eur_low != null && data.total_monthly_loss_eur_high != null) {
    return { low: data.total_monthly_loss_eur_low, high: data.total_monthly_loss_eur_high };
  }
  const v = data.total_monthly_loss_eur || 0;
  return { low: v, high: v };
}
function reportAnnualRange(data: RevenueLeakReport): { low: number; high: number } {
  if (data.total_annual_loss_eur_low != null && data.total_annual_loss_eur_high != null) {
    return { low: data.total_annual_loss_eur_low, high: data.total_annual_loss_eur_high };
  }
  const v = data.total_annual_loss_eur || 0;
  return { low: v, high: v };
}
function roiPaybackRange(roi: RoiCalculation): { best: number | null; worst: number | null } {
  if (roi.payback_months_best != null && roi.payback_months_worst != null) {
    return { best: roi.payback_months_best, worst: roi.payback_months_worst };
  }
  return { best: roi.payback_months ?? null, worst: roi.payback_months ?? null };
}
function roiYearOneRange(roi: RoiCalculation): { low: number; high: number } {
  if (roi.year_one_net_return_eur_low != null && roi.year_one_net_return_eur_high != null) {
    return { low: roi.year_one_net_return_eur_low, high: roi.year_one_net_return_eur_high };
  }
  return { low: roi.year_one_net_return_eur, high: roi.year_one_net_return_eur };
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
          title={`Tegenstrijdige invoer — ${c.ratio.toFixed(1)}x verschil`}
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

function MetricRow({ m, funnelRevenue }: { m: RevenueLeakMetric; funnelRevenue: number | null }) {
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
              <p className="text-[10px] text-gray-500 italic border border-gray-200 rounded px-1.5 py-0.5 inline-block">handmatig verifiëren</p>
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
      </div>
    </div>
  );
}

function LayerCard({ layer, funnelRevenue }: { layer: RevenueLeakLayer; funnelRevenue: number | null }) {
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
              <span className="text-[10px] text-gray-500">+{layer.unpriced_finding_count} te verifiëren</span>
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
            <MetricRow key={m.metric} m={m} funnelRevenue={funnelRevenue} />
          ))}
        </div>
      )}
    </ReportCard>
  );
}

function TriggerCard({ t }: { t: CeoTriggerKpi }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`border rounded-2xl shadow-sm overflow-hidden transition-colors ${t.triggered ? "border-red-200 bg-red-50" : "border-gray-100 bg-white"}`}>
      <button onClick={() => setOpen((o) => !o)} className="w-full text-left px-4 py-3 flex items-start gap-3">
        <span className={`mt-0.5 flex-shrink-0 w-2 h-2 rounded-full ${t.triggered ? "bg-[#EF4444]" : "bg-gray-300"}`} />
        <div className="flex-1 min-w-0">
          <p className={`text-xs font-semibold ${t.triggered ? "text-gray-900" : "text-gray-500"}`}>{t.kpi}</p>
          {t.triggered && <p className="text-[11px] text-gray-600 mt-0.5">{t.what_ceo_sees}</p>}
        </div>
        <span className="text-gray-400 text-xs flex-shrink-0">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className={`border-t px-4 py-3 space-y-2 ${t.triggered ? "border-red-200" : "border-gray-100"}`}>
          <p className="text-xs text-gray-700 leading-relaxed">{t.real_meaning}</p>
          <blockquote className="border-l-2 border-[#c5a96f] pl-3 text-xs text-gray-700 italic leading-relaxed">
            "{t.tradual_pitch}"
          </blockquote>
          <p className="text-[11px] text-gray-500">Oplossing: {t.tradual_solution}</p>
          <p className="text-[10px] text-gray-500">Alarm: {t.alarm_signal}</p>
        </div>
      )}
    </div>
  );
}

function RoiBlock({ roi }: { roi: RoiCalculation }) {
  const leakRange = { low: roi.monthly_leak_eur_low ?? roi.monthly_leak_eur, high: roi.monthly_leak_eur_high ?? roi.monthly_leak_eur };
  const annualRange = { low: roi.annual_leak_eur_low ?? roi.annual_leak_eur, high: roi.annual_leak_eur_high ?? roi.annual_leak_eur };
  const payback = roiPaybackRange(roi);
  const yearOne = roiYearOneRange(roi);
  const leakParts = eurRangeParts(leakRange.low, leakRange.high);
  const annualParts = eurRangeParts(annualRange.low, annualRange.high);
  const yearOneParts = eurRangeParts(yearOne.low, yearOne.high);
  const negativeAtLowBound = yearOne.low < 0;

  return (
    <ReportCard className="p-6 space-y-4">
      <SectionLabel className="">ROI — Terugverdientijd Stack Rebuild™</SectionLabel>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiTile
          tone="loss"
          value={leakParts.lead}
          tail={leakParts.tail}
          label={<>directe lekkage/mnd<br />(laag 1+3)</>}
        />
        <KpiTile
          tone="loss"
          value={annualParts.lead}
          tail={annualParts.tail}
          label="per jaar"
        />
        <KpiTile
          tone="accent"
          value={
            <>
              {payback.best != null && payback.worst != null
                ? payback.best === payback.worst ? `${payback.best}` : `${payback.best}–${payback.worst}`
                : "—"}
              <span className="text-base font-normal text-gray-500 ml-1">mnd</span>
            </>
          }
          label={<>terugverdientijd<br />({eur(roi.stack_rebuild_cost_eur)} investering)</>}
        />
        <KpiTile
          tone={negativeAtLowBound ? "warning" : "good"}
          value={yearOneParts.lead}
          tail={yearOneParts.tail}
          label={
            <>
              netto rendement jaar 1
              {negativeAtLowBound && <><br /><span className="text-amber-600">bij ondergrens niet terugverdiend in jaar 1</span></>}
            </>
          }
        />
      </div>
    </ReportCard>
  );
}

function TotalsTable({ data }: { data: RevenueLeakReport }) {
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
            <td colSpan={2} className="py-2.5 px-3 text-xs text-gray-500">Directe lekkage ({isV2 ? "L1+L3" : "L1+L2+L3"})</td>
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
        href="https://tradual.com/contact"
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
  const [data, setData] = useState<RevenueLeakReport | null>(null);
  const [serankingTraffic, setSerankingTraffic] = useState<SeRankingTraffic | null>(null);
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
          const full = await getFullAudit(auditId!);
          if (stopped) return;
          setData(full.data?.revenue_leak ?? null);
          setSerankingTraffic(full.data?.seranking_traffic ?? null);
          setCompanyName(full.company_name ?? s.store_url);
          setLoading(false);
        } else if (s.status === "failed") {
          setError("De audit is mislukt. Probeer het opnieuw.");
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
  if (!data) {
    return (
      <ReportShell>
        <div className="max-w-3xl mx-auto">
          <Notice>Geen revenue leak data beschikbaar.</Notice>
        </div>
      </ReportShell>
    );
  }

  const triggeredKpis = data.ceo_triggers.filter((t) => t.triggered);
  const allKpis = data.ceo_triggers;
  const { low: totalLow, high: totalHigh } = reportMonthlyRange(data);
  const { low: totalAnnualLow, high: totalAnnualHigh } = reportAnnualRange(data);
  const heroParts = eurRangeParts(totalLow, totalHigh);
  const heroAnnualParts = eurRangeParts(totalAnnualLow, totalAnnualHigh);
  const funnelRevenue = data.funnel?.monthly_revenue_eur ?? null;
  const conflicts = data.data_conflicts ?? [];
  const warnings = data.model_warnings ?? [];

  return (
    <ReportShell>
      <div className="max-w-3xl mx-auto space-y-10">

        {/* Hero — the report type and store URL used to live in a custom top bar */}
        <div>
          <SectionLabel>Rapport voor</SectionLabel>
          <h1 className="text-3xl font-bold text-gray-900 mb-1" style={{ fontFamily: "var(--font-serif)" }}>
            {companyName || storeUrl}
          </h1>
          <p className="text-sm text-gray-500 truncate">Revenue Leak Audit™ · {storeUrl}</p>
          {totalHigh > 0 ? (
            <div className="mt-6 flex flex-wrap gap-6">
              <HeroFigure parts={heroParts} size="xl" label="geschat verlies per maand" />
              <HeroFigure parts={heroAnnualParts} size="lg" label="per jaar" />
            </div>
          ) : (
            <p className="text-gray-500 mt-4 text-sm">Geen direct meetbaar verlies gedetecteerd — zie strategische signalen in Laag 5.</p>
          )}
        </div>

        {/* Data conflicts — surfaced before the euros so they're read first */}
        <DataConflictBanner conflicts={conflicts} />

        {/* CEO Triggers */}
        {allKpis.length > 0 && (
          <div>
            <SectionLabel>
              {triggeredKpis.length > 0 ? `${triggeredKpis.length} CEO-signalen herkend` : "CEO Trigger KPI's"}
            </SectionLabel>
            <div className="space-y-2">
              {allKpis.map((t) => (
                <TriggerCard key={t.kpi} t={t} />
              ))}
            </div>
          </div>
        )}

        {/* De 5 Lagen */}
        <div>
          <SectionLabel>De 5 Meetlagen</SectionLabel>
          <div className="space-y-2">
            {data.layers.map((layer) => (
              <LayerCard key={layer.layer} layer={layer} funnelRevenue={funnelRevenue} />
            ))}
          </div>
        </div>

        {/* Revenue Leak Score Totaaloverzicht */}
        <div>
          <SectionLabel>Revenue Leak Score™ — Totaaloverzicht</SectionLabel>
          <TotalsTable data={data} />
        </div>

        {/* ROI */}
        {data.roi && <RoiBlock roi={data.roi} />}

        <ModelWarnings warnings={warnings} />

        {/* Data source badge */}
        {serankingTraffic ? (
          <div className="flex items-center gap-2">
            <StatusPill tone="ok" size="md">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd"/></svg>
              Gemeten via SE Ranking — {(serankingTraffic.monthly_organic_sessions + serankingTraffic.monthly_paid_sessions).toLocaleString("nl-NL")} bezoekers/mnd
            </StatusPill>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <StatusPill tone="warning" size="md">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd"/></svg>
              Schatting — traffic niet beschikbaar via SE Ranking
            </StatusPill>
          </div>
        )}

        {/* Next steps */}
        <NextStepsSection relevant={relevantStepsFromRevenueLeak(data)} />

        {/* Methodology */}
        {data.methodology_note && (
          <p className="text-[11px] text-gray-500 italic leading-relaxed">{data.methodology_note}</p>
        )}
        {data.funnel?.methodology_note && (
          <p className="text-[11px] text-gray-500 italic leading-relaxed">{data.funnel.methodology_note}</p>
        )}

        <Cta />
      </div>
    </ReportShell>
  );
}

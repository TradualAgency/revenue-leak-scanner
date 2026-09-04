import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { NextStepsSection } from "~/components/NextSteps";
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
  const colors: Record<RevenueLeakMetric["priority"], string> = {
    critical: "bg-red-500",
    high: "bg-orange-400",
    medium: "bg-yellow-400",
    low: "bg-white/20",
  };
  return <span className={`inline-block w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${colors[priority]}`} />;
}

function DataConflictBanner({ conflicts }: { conflicts: DataConflict[] }) {
  if (conflicts.length === 0) return null;
  return (
    <div className="space-y-2">
      {conflicts.map((c, i) => (
        <div
          key={i}
          className={`border rounded-xl p-4 ${
            c.severity === "critical" ? "border-red-500/30 bg-red-500/5" : "border-amber-500/30 bg-amber-500/5"
          }`}
        >
          <p className={`text-xs font-semibold uppercase tracking-wide mb-1 ${c.severity === "critical" ? "text-red-400" : "text-amber-400"}`}>
            Tegenstrijdige invoer — {c.ratio.toFixed(1)}x verschil
          </p>
          <p className="text-xs text-white/60 leading-relaxed">{c.message_nl}</p>
        </div>
      ))}
    </div>
  );
}

function ModelWarnings({ warnings }: { warnings: ModelWarning[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="space-y-1.5">
      {warnings.map((w, i) => (
        <p key={i} className="text-[11px] text-amber-400/70 leading-relaxed">⚠ {w.detail}</p>
      ))}
    </div>
  );
}

function MetricRow({ m, funnelRevenue }: { m: RevenueLeakMetric; funnelRevenue: number | null }) {
  const { low, high } = metricRange(m);
  const { low: annualLow, high: annualHigh } = metricAnnualRange(m);
  const share = high != null && funnelRevenue ? high / funnelRevenue : null;
  const severity = severityByShare(share, 0.01, 0.03);

  return (
    <div className="flex gap-3 py-2.5 border-b border-white/5 last:border-0">
      <PriorityDot priority={m.priority} />
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium text-white/75">{m.metric}</p>
            {m.signal && <p className="text-[11px] text-white/35 mt-0.5">{m.signal}</p>}
          </div>
          <div className="text-right flex-shrink-0">
            {m.verify_manually ? (
              <p className="text-[10px] text-slate-400 italic border border-slate-500/30 rounded px-1.5 py-0.5 inline-block">handmatig verifiëren</p>
            ) : low != null && high != null ? (
              <>
                <p className={`text-sm font-bold tabular-nums ${severity === "critical" ? "text-red-400" : severity === "warning" ? "text-orange-400" : "text-white/25"}`}>
                  {high === 0 ? "—" : eurRange(low, high)}
                </p>
                {high > 0 && annualLow != null && annualHigh != null && (
                  <p className="text-[10px] text-white/25 tabular-nums">{eurRange(annualLow, annualHigh)}/jr</p>
                )}
              </>
            ) : (
              <p className="text-[10px] text-white/20 italic">{m.kind === "diagnostic" ? "diagnose" : m.kind === "restatement" ? "herformulering" : "strategisch"}</p>
            )}
          </div>
        </div>
        <p className="text-[10px] text-white/20 mt-1 leading-snug">{m.basis || m.calculation_note}</p>
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
    <div className="border border-white/10 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full text-left px-5 py-4 flex items-center gap-4 hover:bg-white/[0.02] transition-colors"
      >
        <span className="text-xs font-mono text-white/20 w-4">{layer.layer}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold text-white">{layer.name}</span>
            {!isNa && high! > 0 && (
              <span className={`text-xs font-bold tabular-nums ${kind === "cost" ? "text-amber-400" : high! > 3000 ? "text-red-400" : "text-orange-400"}`}>
                {eurRange(low, high)}/mnd
              </span>
            )}
            {(isNa || kind === "diagnostic" || kind === "restatement" || kind === "readiness") && (
              <span className="text-xs text-[#c5a96f]/60 font-medium">
                {kind === "restatement" ? "Herformulering" : kind === "diagnostic" ? "Diagnose" : "Strategisch"}
              </span>
            )}
            {layer.unpriced_finding_count != null && layer.unpriced_finding_count > 0 && (
              <span className="text-[10px] text-slate-400">+{layer.unpriced_finding_count} te verifiëren</span>
            )}
          </div>
          <p className="text-xs text-white/35 mt-0.5 leading-snug">{layer.core_question}</p>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-xs text-[#c5a96f]/50 hidden sm:block">{layer.leads_to}</span>
          <span className="text-white/20 text-xs">{open ? "▲" : "▼"}</span>
        </div>
      </button>
      {open && layer.metrics.length > 0 && (
        <div className="border-t border-white/10 px-5 py-1 bg-white/[0.015]">
          {layer.metrics.map((m) => (
            <MetricRow key={m.metric} m={m} funnelRevenue={funnelRevenue} />
          ))}
        </div>
      )}
    </div>
  );
}

function TriggerCard({ t }: { t: CeoTriggerKpi }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`border rounded-xl overflow-hidden transition-colors ${t.triggered ? "border-red-500/30 bg-red-500/5" : "border-white/8 bg-white/[0.02]"}`}>
      <button onClick={() => setOpen((o) => !o)} className="w-full text-left px-4 py-3 flex items-start gap-3">
        <span className={`mt-0.5 flex-shrink-0 w-2 h-2 rounded-full ${t.triggered ? "bg-red-500" : "bg-white/15"}`} />
        <div className="flex-1 min-w-0">
          <p className={`text-xs font-semibold ${t.triggered ? "text-white" : "text-white/40"}`}>{t.kpi}</p>
          {t.triggered && <p className="text-[11px] text-white/40 mt-0.5">{t.what_ceo_sees}</p>}
        </div>
        <span className="text-white/20 text-xs flex-shrink-0">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-white/10 px-4 py-3 space-y-2">
          <p className="text-xs text-white/50 leading-relaxed">{t.real_meaning}</p>
          <blockquote className="border-l-2 border-[#c5a96f]/40 pl-3 text-xs text-white/60 italic leading-relaxed">
            "{t.tradual_pitch}"
          </blockquote>
          <p className="text-[11px] text-[#c5a96f]/60">Oplossing: {t.tradual_solution}</p>
          <p className="text-[10px] text-white/25">Alarm: {t.alarm_signal}</p>
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
    <div className="border border-white/10 rounded-2xl p-6 space-y-4">
      <p className="text-xs font-semibold text-white/40 uppercase tracking-widest">ROI — Terugverdientijd Stack Rebuild™</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div>
          <p className="text-xl font-bold text-red-400 tabular-nums">
            {leakParts.lead}{leakParts.tail && <span className="text-sm font-normal text-red-400/50 ml-1">{leakParts.tail}</span>}
          </p>
          <p className="text-[11px] text-white/35 mt-1">directe lekkage/mnd<br />(laag 1+3)</p>
        </div>
        <div>
          <p className="text-xl font-bold text-red-300/70 tabular-nums">
            {annualParts.lead}{annualParts.tail && <span className="text-sm font-normal text-red-300/40 ml-1">{annualParts.tail}</span>}
          </p>
          <p className="text-[11px] text-white/35 mt-1">per jaar</p>
        </div>
        <div>
          <p className="text-xl font-bold text-[#c5a96f] tabular-nums">
            {payback.best != null && payback.worst != null
              ? payback.best === payback.worst ? `${payback.best}` : `${payback.best}–${payback.worst}`
              : "—"}
            <span className="text-base font-normal text-white/40 ml-1">mnd</span>
          </p>
          <p className="text-[11px] text-white/35 mt-1">terugverdientijd<br />({eur(roi.stack_rebuild_cost_eur)} investering)</p>
        </div>
        <div>
          <p className={`text-xl font-bold tabular-nums ${negativeAtLowBound ? "text-amber-400" : "text-emerald-400"}`}>
            {yearOneParts.lead}{yearOneParts.tail && <span className="text-sm font-normal opacity-50 ml-1">{yearOneParts.tail}</span>}
          </p>
          <p className="text-[11px] text-white/35 mt-1">
            netto rendement jaar 1
            {negativeAtLowBound && <><br /><span className="text-amber-400/70">bij ondergrens niet terugverdiend in jaar 1</span></>}
          </p>
        </div>
      </div>
    </div>
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
    <div className="border border-white/10 rounded-xl overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-white/10 bg-white/[0.02]">
            {["Laag", "Naam", "/mnd", "/jaar"].map((h) => (
              <th key={h} className="text-left py-2 px-3 text-white/30 font-medium uppercase tracking-wide text-[10px]">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.layers.map((l) => {
            const { low, high } = layerRange(l);
            const { low: aLow, high: aHigh } = layerAnnualRange(l);
            const hasData = low != null && high != null;
            return (
              <tr key={l.layer} className="border-b border-white/5 last:border-0">
                <td className="py-2 px-3 text-white/20 font-mono">{l.layer}</td>
                <td className="py-2 px-3 text-white/60">{l.name}</td>
                <td className="py-2 px-3 tabular-nums font-semibold whitespace-nowrap">
                  {hasData
                    ? <span className={high! > 0 ? (l.kind === "cost" ? "text-amber-400" : "text-orange-400") : "text-white/25"}>{high! > 0 ? eurRange(low, high) : "—"}</span>
                    : <span className="text-white/20 italic text-[10px]">n.v.t.</span>
                  }
                </td>
                <td className="py-2 px-3 tabular-nums text-white/35 whitespace-nowrap">
                  {aLow != null && aHigh != null && aHigh > 0 ? eurRange(aLow, aHigh) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot className="border-t border-white/15">
          <tr className="bg-white/[0.03]">
            <td colSpan={2} className="py-2.5 px-3 text-xs text-white/40">Directe lekkage ({isV2 ? "L1+L3" : "L1+L2+L3"})</td>
            <td className="py-2.5 px-3 font-bold text-red-400 tabular-nums whitespace-nowrap">
              {isV2 ? eurRange(direct.low, direct.high) : eur(legacyDirectMonthly)}
            </td>
            <td className="py-2.5 px-3 text-red-300/60 tabular-nums whitespace-nowrap">
              {isV2 ? eurRange(directAnnual.low, directAnnual.high) : eur(legacyDirectAnnual)}
            </td>
          </tr>
          {!isV2 && (
            <tr className="bg-white/[0.05]">
              <td colSpan={2} className="py-2.5 px-3 text-xs text-white/50 font-semibold">Totaal incl. efficiëntie (L1–L4)</td>
              <td className="py-2.5 px-3 font-bold text-red-300 tabular-nums">{eur(legacyTotalMonthly)}</td>
              <td className="py-2.5 px-3 text-red-300/50 tabular-nums">{eur(legacyTotalAnnual)}</td>
            </tr>
          )}
        </tfoot>
      </table>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="min-h-screen bg-[#0e1017] flex items-center justify-center">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-[#c5a96f]/30 border-t-[#c5a96f] rounded-full animate-spin mx-auto mb-4" />
        <p className="text-sm text-white/40">Audit wordt uitgevoerd…</p>
      </div>
    </div>
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
      <div className="min-h-screen bg-[#0e1017] flex items-center justify-center">
        <p className="text-red-400 text-sm">{error}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="min-h-screen bg-[#0e1017] flex items-center justify-center">
        <p className="text-white/40 text-sm">Geen revenue leak data beschikbaar.</p>
      </div>
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
    <div className="min-h-screen bg-[#0e1017] text-white">
      {/* Header */}
      <div className="border-b border-white/8 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-serif text-lg text-[#c5a96f]" style={{ fontFamily: "var(--font-serif)" }}>Tradual</span>
          <span className="text-white/20 text-xs">Revenue Leak Audit™</span>
        </div>
        <p className="text-xs text-white/30 truncate max-w-[240px]">{storeUrl}</p>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-12 space-y-10">

        {/* Hero */}
        <div>
          <p className="text-xs text-white/30 uppercase tracking-widest mb-3">Rapport voor</p>
          <h1 className="text-3xl font-bold text-white mb-1" style={{ fontFamily: "var(--font-serif)" }}>
            {companyName || storeUrl}
          </h1>
          {totalHigh > 0 ? (
            <div className="mt-6 flex flex-wrap gap-6">
              <div>
                <p className="text-5xl font-black text-red-400 tabular-nums leading-none">
                  {heroParts.lead}
                  {heroParts.tail && <span className="text-2xl font-bold text-red-400/60 ml-2">{heroParts.tail}</span>}
                </p>
                <p className="text-sm text-white/40 mt-2">geschat verlies per maand</p>
              </div>
              <div>
                <p className="text-4xl font-bold text-red-300/70 tabular-nums leading-none">
                  {heroAnnualParts.lead}
                  {heroAnnualParts.tail && <span className="text-xl font-bold text-red-300/40 ml-2">{heroAnnualParts.tail}</span>}
                </p>
                <p className="text-sm text-white/40 mt-2">per jaar</p>
              </div>
            </div>
          ) : (
            <p className="text-white/40 mt-4 text-sm">Geen direct meetbaar verlies gedetecteerd — zie strategische signalen in Laag 5.</p>
          )}
        </div>

        {/* Data conflicts — surfaced before the euros so they're read first */}
        <DataConflictBanner conflicts={conflicts} />

        {/* CEO Triggers */}
        {allKpis.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-3">
              {triggeredKpis.length > 0 ? `${triggeredKpis.length} CEO-signalen herkend` : "CEO Trigger KPI's"}
            </p>
            <div className="space-y-2">
              {allKpis.map((t) => (
                <TriggerCard key={t.kpi} t={t} />
              ))}
            </div>
          </div>
        )}

        {/* De 5 Lagen */}
        <div>
          <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-3">De 5 Meetlagen</p>
          <div className="space-y-2">
            {data.layers.map((layer) => (
              <LayerCard key={layer.layer} layer={layer} funnelRevenue={funnelRevenue} />
            ))}
          </div>
        </div>

        {/* Revenue Leak Score Totaaloverzicht */}
        <div>
          <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-3">Revenue Leak Score™ — Totaaloverzicht</p>
          <TotalsTable data={data} />
        </div>

        {/* ROI */}
        {data.roi && <RoiBlock roi={data.roi} />}

        <ModelWarnings warnings={warnings} />

        {/* Data source badge */}
        {serankingTraffic ? (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-900/40 border border-emerald-700/50 px-3 py-1 text-xs font-medium text-emerald-400">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd"/></svg>
              Gemeten via SE Ranking — {(serankingTraffic.monthly_organic_sessions + serankingTraffic.monthly_paid_sessions).toLocaleString("nl-NL")} bezoekers/mnd
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-900/30 border border-amber-700/40 px-3 py-1 text-xs font-medium text-amber-400">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd"/></svg>
              Schatting — traffic niet beschikbaar via SE Ranking
            </span>
          </div>
        )}

        {/* Next steps */}
        <NextStepsSection data={data} />

        {/* Methodology */}
        {data.methodology_note && (
          <p className="text-[11px] text-white/20 italic leading-relaxed">{data.methodology_note}</p>
        )}
        {data.funnel?.methodology_note && (
          <p className="text-[11px] text-white/20 italic leading-relaxed">{data.funnel.methodology_note}</p>
        )}

        {/* CTA */}
        <div className="border border-[#c5a96f]/20 rounded-2xl p-6 text-center bg-[#c5a96f]/5">
          <p className="text-sm font-semibold text-white mb-1" style={{ fontFamily: "var(--font-serif)" }}>
            Klaar voor de volgende stap?
          </p>
          <p className="text-xs text-white/40 mb-4">
            Stap 1 heb je net gehad. Laten we bespreken wat voor jouw situatie het meest oplevert.
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

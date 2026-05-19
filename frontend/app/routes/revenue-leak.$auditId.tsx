import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { getFullAudit, getFullAuditStatus } from "~/lib/api";
import type {
  CeoTriggerKpi,
  FullAuditStatusResponse,
  RevenueLeakLayer,
  RevenueLeakMetric,
  RevenueLeakReport,
  RoiCalculation,
  SeRankingTraffic,
} from "~/lib/types";

const POLL_INTERVAL = 3000;

function fmt(eur: number) {
  return `€${eur.toLocaleString("nl-NL")}`;
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

function MetricRow({ m }: { m: RevenueLeakMetric }) {
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
            {m.monthly_loss_eur != null ? (
              <>
                <p className={`text-sm font-bold tabular-nums ${m.monthly_loss_eur > 500 ? "text-red-400" : m.monthly_loss_eur > 0 ? "text-orange-400" : "text-white/25"}`}>
                  {m.monthly_loss_eur === 0 ? "—" : fmt(m.monthly_loss_eur)}
                </p>
                {m.monthly_loss_eur > 0 && (
                  <p className="text-[10px] text-white/25 tabular-nums">{fmt(m.monthly_loss_eur * 12)}/jr</p>
                )}
              </>
            ) : (
              <p className="text-[10px] text-white/20 italic">strategisch</p>
            )}
          </div>
        </div>
        <p className="text-[10px] text-white/20 mt-1 leading-snug">{m.calculation_note}</p>
      </div>
    </div>
  );
}

function LayerCard({ layer }: { layer: RevenueLeakLayer }) {
  const [open, setOpen] = useState(false);
  const isNa = layer.est_monthly_loss_eur == null;
  const loss = layer.est_monthly_loss_eur || 0;

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
            {!isNa && loss > 0 && (
              <span className={`text-xs font-bold tabular-nums ${loss > 3000 ? "text-red-400" : "text-orange-400"}`}>
                {fmt(loss)}/mnd
              </span>
            )}
            {isNa && <span className="text-xs text-[#c5a96f]/60 font-medium">Strategisch</span>}
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
            <MetricRow key={m.metric} m={m} />
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

function RoiBlock({ roi, totalMonthly, totalAnnual }: { roi: RoiCalculation; totalMonthly: number; totalAnnual: number }) {
  const directLeak = totalMonthly;
  const directLeakAnnual = totalAnnual;

  return (
    <div className="border border-white/10 rounded-2xl p-6 space-y-4">
      <p className="text-xs font-semibold text-white/40 uppercase tracking-widest">ROI — Terugverdientijd Stack Rebuild™</p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div>
          <p className="text-2xl font-bold text-red-400 tabular-nums">{fmt(directLeak)}</p>
          <p className="text-[11px] text-white/35 mt-1">directe lekkage/mnd<br />(laag 1+2+3)</p>
        </div>
        <div>
          <p className="text-2xl font-bold text-red-300/70 tabular-nums">{fmt(directLeakAnnual)}</p>
          <p className="text-[11px] text-white/35 mt-1">per jaar</p>
        </div>
        <div>
          <p className="text-2xl font-bold text-[#c5a96f] tabular-nums">
            {roi.payback_months != null ? `${roi.payback_months}` : "—"}
            <span className="text-base font-normal text-white/40 ml-1">mnd</span>
          </p>
          <p className="text-[11px] text-white/35 mt-1">terugverdientijd<br />({fmt(roi.stack_rebuild_cost_eur)} investering)</p>
        </div>
        <div>
          <p className="text-2xl font-bold text-emerald-400 tabular-nums">{fmt(roi.year_one_net_return_eur)}</p>
          <p className="text-[11px] text-white/35 mt-1">netto rendement<br />jaar 1</p>
        </div>
      </div>
    </div>
  );
}

function TotalsTable({ data }: { data: RevenueLeakReport }) {
  const directLayers = data.layers.filter((l) => [1, 2, 3].includes(l.layer));
  const directMonthly = directLayers.reduce((s, l) => s + (l.est_monthly_loss_eur || 0), 0);
  const directAnnual = directLayers.reduce((s, l) => s + (l.est_annual_loss_eur || 0), 0);
  const allMonetary = data.layers.filter((l) => l.est_monthly_loss_eur != null);
  const totalMonthly = allMonetary.reduce((s, l) => s + (l.est_monthly_loss_eur || 0), 0);
  const totalAnnual = allMonetary.reduce((s, l) => s + (l.est_annual_loss_eur || 0), 0);

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
          {data.layers.map((l) => (
            <tr key={l.layer} className="border-b border-white/5 last:border-0">
              <td className="py-2 px-3 text-white/20 font-mono">{l.layer}</td>
              <td className="py-2 px-3 text-white/60">{l.name}</td>
              <td className="py-2 px-3 tabular-nums font-semibold">
                {l.est_monthly_loss_eur != null
                  ? <span className={l.est_monthly_loss_eur > 0 ? "text-orange-400" : "text-white/25"}>{l.est_monthly_loss_eur > 0 ? fmt(l.est_monthly_loss_eur) : "—"}</span>
                  : <span className="text-white/20 italic text-[10px]">n.v.t.</span>
                }
              </td>
              <td className="py-2 px-3 tabular-nums text-white/35">
                {l.est_annual_loss_eur != null && l.est_annual_loss_eur > 0 ? fmt(l.est_annual_loss_eur) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot className="border-t border-white/15">
          <tr className="bg-white/[0.03]">
            <td colSpan={2} className="py-2.5 px-3 text-xs text-white/40">Directe lekkage (L1+L2+L3)</td>
            <td className="py-2.5 px-3 font-bold text-red-400 tabular-nums">{fmt(directMonthly)}</td>
            <td className="py-2.5 px-3 text-red-300/60 tabular-nums">{fmt(directAnnual)}</td>
          </tr>
          <tr className="bg-white/[0.05]">
            <td colSpan={2} className="py-2.5 px-3 text-xs text-white/50 font-semibold">Totaal incl. efficiëntie (L1–L4)</td>
            <td className="py-2.5 px-3 font-bold text-red-300 tabular-nums">{fmt(totalMonthly)}</td>
            <td className="py-2.5 px-3 text-red-300/50 tabular-nums">{fmt(totalAnnual)}</td>
          </tr>
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
  const total = data.total_monthly_loss_eur || 0;
  const totalAnnual = data.total_annual_loss_eur || 0;

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
          {total > 0 ? (
            <div className="mt-6 flex flex-wrap gap-6">
              <div>
                <p className="text-5xl font-black text-red-400 tabular-nums leading-none">{fmt(total)}</p>
                <p className="text-sm text-white/40 mt-2">geschat verlies per maand</p>
              </div>
              <div>
                <p className="text-4xl font-bold text-red-300/70 tabular-nums leading-none">{fmt(totalAnnual)}</p>
                <p className="text-sm text-white/40 mt-2">per jaar</p>
              </div>
            </div>
          ) : (
            <p className="text-white/40 mt-4 text-sm">Geen direct meetbaar verlies gedetecteerd — zie strategische signalen in Laag 5.</p>
          )}
        </div>

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
              <LayerCard key={layer.layer} layer={layer} />
            ))}
          </div>
        </div>

        {/* Revenue Leak Score Totaaloverzicht */}
        <div>
          <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-3">Revenue Leak Score™ — Totaaloverzicht</p>
          <TotalsTable data={data} />
        </div>

        {/* ROI */}
        {data.roi && (
          <RoiBlock roi={data.roi} totalMonthly={total} totalAnnual={totalAnnual} />
        )}

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

        {/* Methodology */}
        {data.methodology_note && (
          <p className="text-[11px] text-white/20 italic leading-relaxed">{data.methodology_note}</p>
        )}

        {/* CTA */}
        <div className="border border-[#c5a96f]/20 rounded-2xl p-6 text-center bg-[#c5a96f]/5">
          <p className="text-sm font-semibold text-white mb-1" style={{ fontFamily: "var(--font-serif)" }}>
            Klaar om de lekkage te dichten?
          </p>
          <p className="text-xs text-white/40 mb-4">
            Tradual Stack Rebuild™ — terugverdiend in {data.roi?.payback_months ? `${data.roi.payback_months} maanden` : "korte tijd"}.
          </p>
          <a
            href="https://tradual.com/contact"
            className="inline-block px-6 py-2.5 bg-[#c5a96f] text-[#1a1f2e] text-sm font-semibold rounded-lg hover:bg-[#d4b87e] transition-colors"
          >
            Plan Stack Rebuild gesprek
          </a>
        </div>
      </div>
    </div>
  );
}

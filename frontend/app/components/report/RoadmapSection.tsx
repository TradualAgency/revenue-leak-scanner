import { eurRange } from "~/lib/format";
import type { StrategicRoadmap } from "~/lib/types";
import ReportCard from "./ReportCard";
import SectionLabel from "./SectionLabel";

/** The phased plan. Text comes from the AI roadmap skill; the euro range per phase is
 * summed server-side from the measured findings that phase resolves — never written by
 * the model. Phases without priced findings simply show no amount. */
export default function RoadmapSection({ roadmap }: { roadmap: StrategicRoadmap }) {
  if (roadmap.phases.length === 0) return null;
  return (
    <div>
      <SectionLabel>Stappenplan{roadmap.total_timeline ? ` · ${roadmap.total_timeline}` : ""}</SectionLabel>
      <div className="space-y-3">
        {roadmap.phases.map((p) => (
          <ReportCard key={p.phase} className="p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <p className="text-sm font-semibold text-gray-900">
                <span className="text-gray-400 font-normal mr-2">Fase {p.phase}</span>
                {p.name}
              </p>
              <p className="text-xs text-gray-500">{p.timeframe}</p>
            </div>
            <p className="text-xs text-gray-600 mt-1 leading-relaxed">{p.objective}</p>
            {p.actions.length > 0 && (
              <ul className="mt-3 space-y-1">
                {p.actions.map((a, i) => (
                  <li key={i} className="flex gap-2 text-xs text-gray-700 leading-relaxed">
                    <span className="text-gray-400 flex-shrink-0">—</span>
                    {a}
                  </li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 mt-3 pt-3 border-t border-gray-100">
              <p className="text-[11px] text-gray-500">Resultaat: {p.expected_outcome}</p>
              {p.est_monthly_impact_eur_high ? (
                <p className="text-xs font-bold tabular-nums text-gray-900">
                  lost {eurRange(p.est_monthly_impact_eur_low, p.est_monthly_impact_eur_high)}/mnd op
                </p>
              ) : null}
            </div>
          </ReportCard>
        ))}
      </div>
    </div>
  );
}

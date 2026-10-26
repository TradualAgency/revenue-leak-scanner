import { eurRange } from "~/lib/format";
import type { ActionItem } from "~/lib/types";
import ReportCard from "./ReportCard";
import SectionLabel from "./SectionLabel";
import StatusPill from "./StatusPill";

const EFFORT_LABEL: Record<ActionItem["effort"], string> = {
  S: "Klein",
  M: "Middel",
  L: "Groot",
};

const CONFIDENCE_LABEL: Record<ActionItem["confidence"], string> = {
  high: "hoge zekerheid",
  medium: "redelijke zekerheid",
  low: "lage zekerheid",
};

function days(low: number, high: number): string {
  const fmt = (n: number) => (Number.isInteger(n) ? `${n}` : n.toFixed(1).replace(".", ","));
  return low === high ? `${fmt(low)} werkdag${low === 1 ? "" : "en"}` : `${fmt(low)}–${fmt(high)} werkdagen`;
}

/** The ranked "what to do first" list. Order comes from the backend: most euros per
 * day of work first, then the findings we could not put a number on. */
export default function ActionList({ actions }: { actions: ActionItem[] }) {
  if (actions.length === 0) return null;
  return (
    <div>
      <SectionLabel>Wat levert het meeste op — in volgorde</SectionLabel>
      <ReportCard className="divide-y divide-gray-100">
        {actions.map((a, i) => (
          <div key={a.action_key} className="px-5 py-4 flex gap-4">
            <span className="text-sm font-semibold text-gray-400 tabular-nums w-5 flex-shrink-0">{i + 1}</span>
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
                <p className="text-sm font-semibold text-gray-900">{a.title_nl}</p>
                {a.priced && a.monthly_high ? (
                  <p className="text-sm font-bold tabular-nums text-[#EF4444]">
                    {eurRange(a.monthly_low, a.monthly_high)}/mnd
                  </p>
                ) : (
                  <p className="text-[11px] text-gray-500 italic">
                    {a.verify_manually ? "eerst handmatig verifiëren" : "niet in euro's uit te drukken"}
                  </p>
                )}
              </div>
              <p className="text-xs text-gray-600 leading-relaxed mt-1">{a.what_to_do_nl}</p>
              <div className="flex flex-wrap items-center gap-2 mt-2">
                <StatusPill tone="muted">
                  {EFFORT_LABEL[a.effort]} · {days(a.effort_days_low, a.effort_days_high)}
                </StatusPill>
                <StatusPill tone="muted">{a.owner}</StatusPill>
                {a.priced && (
                  <StatusPill tone={a.confidence === "low" ? "warning" : "muted"}>
                    {CONFIDENCE_LABEL[a.confidence]}
                  </StatusPill>
                )}
              </div>
              <p className="text-[11px] text-gray-500 mt-2">
                Hermeten na {a.remeasure_after_days} dagen: {a.remeasure_metric}
              </p>
            </div>
          </div>
        ))}
      </ReportCard>
    </div>
  );
}

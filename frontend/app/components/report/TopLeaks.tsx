import { screenshotUrl } from "~/lib/api";
import { eurRange } from "~/lib/format";
import type { ActionItem, FindingOut } from "~/lib/types";
import ReportCard from "./ReportCard";
import SectionLabel from "./SectionLabel";

/** The three priced actions that open the client report. Each one carries its own
 * evidence: the measured `signal` sentences and funnel-walk screenshots of the findings
 * it fixes — that proof is what a generic AI answer can't give. Order comes from the
 * backend (most euros per day of work first). */
export default function TopLeaks({
  auditId,
  actions,
  findings,
}: {
  auditId: string;
  actions: ActionItem[];
  findings: FindingOut[];
}) {
  const top = actions.filter((a) => a.priced && !a.verify_manually && a.monthly_high).slice(0, 3);
  if (top.length === 0) return null;
  const byId = new Map(findings.map((f) => [f.finding_id, f]));

  return (
    <div>
      <SectionLabel>Je {top.length === 1 ? "grootste lek" : `${top.length} grootste lekken`}</SectionLabel>
      <div className="space-y-3">
        {top.map((a, i) => {
          const linked = a.finding_ids.map((id) => byId.get(id)).filter((f): f is FindingOut => f != null);
          const signals = [...new Set(linked.map((f) => f.signal).filter((s): s is string => !!s))];
          const shots = [...new Set(linked.flatMap((f) => f.screenshot_ids ?? []))].slice(0, 3);
          return (
            <ReportCard key={a.action_key} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
                <p className="text-base font-semibold text-gray-900" style={{ fontFamily: "var(--font-serif)" }}>
                  <span className="text-gray-400 tabular-nums mr-2">{i + 1}.</span>
                  {a.title_nl}
                </p>
                <p className="text-base font-bold tabular-nums text-[#EF4444]">
                  {eurRange(a.monthly_low, a.monthly_high)}/mnd
                </p>
              </div>
              {signals.length > 0 && (
                <div className="mt-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 mb-1">Wat we gemeten hebben</p>
                  <ul className="space-y-1">
                    {signals.map((s) => (
                      <li key={s} className="text-sm text-gray-700 leading-relaxed">{s}</li>
                    ))}
                  </ul>
                </div>
              )}
              {shots.length > 0 && (
                <div className="flex flex-wrap gap-3 mt-3">
                  {shots.map((sid) => (
                    <a key={sid} href={screenshotUrl(auditId, sid)} target="_blank" rel="noreferrer">
                      <img
                        src={screenshotUrl(auditId, sid)}
                        alt={a.title_nl}
                        loading="lazy"
                        className="w-32 rounded-lg border border-gray-200"
                      />
                    </a>
                  ))}
                </div>
              )}
              <p className="text-xs text-gray-600 leading-relaxed mt-3">
                <span className="font-medium text-gray-800">Oplossing: </span>
                {a.what_to_do_nl}
              </p>
            </ReportCard>
          );
        })}
      </div>
    </div>
  );
}

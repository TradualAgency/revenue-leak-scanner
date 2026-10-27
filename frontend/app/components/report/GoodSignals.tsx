import type { RevenueLeakLayer } from "~/lib/types";
import ReportCard from "./ReportCard";
import SectionLabel from "./SectionLabel";

const MAX_SIGNALS = 5;

/** What the store already does well. A report that only lists problems reads as a
 * sales pitch; a few honest positives make the leaks above more credible. */
export default function GoodSignals({ layers }: { layers: RevenueLeakLayer[] }) {
  const signals = [...new Set(layers.flatMap((l) => l.good_signals ?? []))].slice(0, MAX_SIGNALS);
  if (signals.length === 0) return null;
  return (
    <div>
      <SectionLabel>Wat goed gaat</SectionLabel>
      <ReportCard className="p-5">
        <ul className="space-y-2">
          {signals.map((s) => (
            <li key={s} className="flex items-start gap-2 text-sm text-gray-700 leading-relaxed">
              <span className="text-emerald-600 flex-shrink-0">✓</span>
              {s}
            </li>
          ))}
        </ul>
      </ReportCard>
    </div>
  );
}

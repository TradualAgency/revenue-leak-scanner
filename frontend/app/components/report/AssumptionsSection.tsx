import { eur } from "~/lib/format";
import type { ClientAssumption, ClientCitation } from "~/lib/types";
import ReportCard from "./ReportCard";
import SectionLabel from "./SectionLabel";
import StatusPill from "./StatusPill";

const SOURCE_LABEL: Record<ClientAssumption["source"], string> = {
  operator: "jullie cijfer",
  seranking: "gemeten (SE Ranking)",
  derived: "berekend",
  benchmark: "branchegemiddelde",
};

function formatValue(a: ClientAssumption): string {
  if (a.unit === "eur") return eur(a.value);
  if (a.unit === "pct") return `${a.value.toLocaleString("nl-NL", { maximumFractionDigits: 2 })}%`;
  return Math.round(a.value).toLocaleString("nl-NL");
}

/** "How did you get to these numbers?" — every input the euros are scaled by, with
 * where it came from, then the sources behind the conversion-impact percentages. */
export default function AssumptionsSection({
  assumptions,
  citations,
  methodologyNote,
}: {
  assumptions: ClientAssumption[];
  citations: ClientCitation[];
  methodologyNote: string | null;
}) {
  if (assumptions.length === 0 && citations.length === 0 && !methodologyNote) return null;
  return (
    <div>
      <SectionLabel>Hoe we tot deze bedragen komen</SectionLabel>
      <ReportCard className="p-5 space-y-5">
        {assumptions.length > 0 && (
          <table className="w-full text-xs">
            <tbody className="divide-y divide-gray-100">
              {assumptions.map((a) => (
                <tr key={a.key} className="align-top">
                  <td className="py-2 pr-3 text-gray-700">
                    {a.label_nl}
                    <p className="text-[11px] text-gray-500 mt-0.5">{a.explanation_nl}</p>
                  </td>
                  <td className="py-2 pr-3 text-right font-semibold tabular-nums text-gray-900 whitespace-nowrap">
                    {formatValue(a)}
                  </td>
                  <td className="py-2 text-right whitespace-nowrap">
                    <StatusPill tone={a.source === "benchmark" ? "warning" : "ok"}>{SOURCE_LABEL[a.source]}</StatusPill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {citations.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-700 mb-2">Bronnen voor de conversie-impact</p>
            <ul className="space-y-3">
              {citations.map((c) => (
                <li key={c.key} className="text-[11px] text-gray-600 leading-relaxed">
                  <p className="text-gray-800 font-medium">
                    {c.source}
                    {!c.verified && <span className="text-gray-500 font-normal"> · nog niet onafhankelijk geverifieerd</span>}
                  </p>
                  <p>{c.figure_nl}</p>
                  <p className="text-gray-500">{c.note_nl}</p>
                </li>
              ))}
            </ul>
          </div>
        )}

        {methodologyNote && <p className="text-[11px] text-gray-500 leading-relaxed">{methodologyNote}</p>}
      </ReportCard>
    </div>
  );
}

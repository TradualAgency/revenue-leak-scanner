import type { FindingOut, FindingVerdictKind, VerificationReport } from "~/lib/types";

const VERDICT: Record<FindingVerdictKind, { label: string; tone: string; effect: string }> = {
  refuted: { label: "Weerlegd", tone: "bg-red-50 text-red-700", effect: "Uit het rapport gehaald" },
  unverifiable: { label: "Niet te verifiëren", tone: "bg-yellow-50 text-yellow-700", effect: "Getoond zonder bedrag" },
  confirmed: { label: "Bevestigd", tone: "bg-emerald-50 text-emerald-700", effect: "Telt mee" },
};

const ORDER: FindingVerdictKind[] = ["refuted", "unverifiable", "confirmed"];

/** Operator-only: what the finding-verifier checked on the live store before the
 * euros were final. Refuted findings no longer exist in `findings`, so the label
 * falls back to the finding id. */
export default function VerificationPanel({ report, findings }: { report: VerificationReport; findings: FindingOut[] }) {
  const metric = Object.fromEntries(findings.map((f) => [f.finding_id, f.metric]));
  const verdicts = [...report.verdicts].sort((a, b) => ORDER.indexOf(a.verdict) - ORDER.indexOf(b.verdict));
  const count = (k: FindingVerdictKind) => report.verdicts.filter((v) => v.verdict === k).length;

  return (
    <section className="rounded-2xl p-6 bg-white border border-gray-100 shadow-sm">
      <h2 className="text-lg font-semibold mb-1 text-gray-700" style={{ fontFamily: "var(--font-serif)" }}>
        Controle-agent
      </h2>
      <p className="text-sm text-gray-500 mb-4">
        Intern: elke geprijsde finding is op de live store nagekeken voordat de bedragen vastlagen.{" "}
        {count("refuted")} weerlegd, {count("unverifiable")} niet te verifiëren, {count("confirmed")} bevestigd.
      </p>

      {report.errors.map((e, i) => (
        <p key={i} className="text-xs text-amber-700 mb-2">Groep niet gecontroleerd (bedragen ongewijzigd): {e}</p>
      ))}

      <div className="space-y-2">
        {verdicts.map((v) => (
          <div key={v.finding_id} className="border border-gray-100 rounded-xl p-4">
            <div className="flex flex-wrap items-start justify-between gap-2 mb-1">
              <h4 className="text-sm font-semibold text-gray-800">
                {metric[v.finding_id] ?? v.finding_id}{" "}
                <span className="font-mono text-[11px] font-normal text-gray-400">{v.finding_id}</span>
              </h4>
              <span className={`text-xs px-2 py-0.5 rounded-full ${VERDICT[v.verdict].tone}`}>
                {VERDICT[v.verdict].label} · {VERDICT[v.verdict].effect}
              </span>
            </div>
            <p className="text-sm text-gray-700">{v.reason_nl}</p>
            {v.evidence_nl && <p className="text-xs text-gray-500 mt-1">Bewijs: {v.evidence_nl}</p>}
          </div>
        ))}
      </div>

      <p className="text-[11px] text-gray-400 mt-4">
        {report.model} · {report.input_tokens.toLocaleString("nl-NL")} in / {report.output_tokens.toLocaleString("nl-NL")} uit
        {report.used_admin_data && " · met Admin-data"}
      </p>
    </section>
  );
}

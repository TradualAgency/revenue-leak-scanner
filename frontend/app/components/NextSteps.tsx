import type { RevenueLeakReport } from "~/lib/types";

// Shared between the revenue-leak report and the marktvergelijking (competitor
// benchmark) page — both are prospect-facing sales artifacts that end on the same
// pitch. Extracted so the price ladder can't drift between the two.

type StepKey = "audit" | "rebuild" | "performance" | "agentic";

const NEXT_STEPS: { key: StepKey; step: number; name: string; description: string; price: string }[] = [
  {
    key: "audit",
    step: 1,
    name: "Revenue Leak Audit™",
    description: "We meten waar je omzet lekt, over alle vijf lagen, en vertalen dat naar euro's per maand en per jaar.",
    price: "€2.500 – €7.500",
  },
  {
    key: "rebuild",
    step: 2,
    name: "Stack Rebuild™",
    description: "Wanneer optimaliseren binnen je huidige stack niet meer genoeg is. Gericht op structureel herstel van performance en conversie.",
    price: "vanaf €25.000",
  },
  {
    key: "performance",
    step: 3,
    name: "Performance Layer™",
    description: "Doorlopende optimalisatielaag na audit of rebuild: meten, prioriteren, bouwen, testen en verbeteren.",
    price: "€3.000 – €10.000 / mnd",
  },
  {
    key: "agentic",
    step: 4,
    name: "Agentic Readiness™",
    description: "Commerce-infrastructuur voorbereiden op AI-agents en nieuwe koopinterfaces: productdata, structured data, feeds, API's en transactionele gereedheid.",
    price: "€5.000 – €15.000 (analyse; implementatie apart)",
  },
];

// Every layer's `leads_to` already points at one of these products (see backend
// revenue_leak.py) — this just decides which of steps 2-4 to visually emphasize based
// on where this specific audit found the most signal.
function relevantSteps(data: RevenueLeakReport): Set<StepKey> {
  const relevant = new Set<StepKey>();
  const directHigh = data.total_monthly_loss_eur_high ?? data.total_monthly_loss_eur ?? 0;
  if (directHigh > 0) relevant.add("rebuild");

  const layer2 = data.layers.find((l) => l.layer === 2);
  if (layer2 && (layer2.est_monthly_loss_eur || 0) > 0) relevant.add("performance");

  const layer5 = data.layers.find((l) => l.layer === 5);
  if (layer5 && layer5.readiness_score != null && layer5.readiness_score < 60) relevant.add("agentic");

  return relevant;
}

export function NextStepsSection({ data, doneKey = "audit" }: { data: RevenueLeakReport; doneKey?: StepKey }) {
  const relevant = relevantSteps(data);
  return (
    <div>
      <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-3">Het pad na deze audit</p>
      <div className="space-y-2">
        {NEXT_STEPS.map((s) => {
          const isDone = s.key === doneKey;
          const isRelevant = relevant.has(s.key);
          return (
            <div
              key={s.key}
              className={`border rounded-xl p-4 flex items-start gap-4 ${
                isDone
                  ? "border-white/10 bg-white/[0.02]"
                  : isRelevant
                  ? "border-[#c5a96f]/40 bg-[#c5a96f]/5"
                  : "border-white/8 bg-white/[0.01]"
              }`}
            >
              <div
                className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                  isDone
                    ? "bg-emerald-500/20 text-emerald-400"
                    : isRelevant
                    ? "bg-[#c5a96f]/20 text-[#c5a96f]"
                    : "bg-white/5 text-white/30"
                }`}
              >
                {isDone ? "✓" : s.step}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-white">{s.name}</span>
                  {isDone && (
                    <span className="text-[10px] text-emerald-400 font-medium uppercase tracking-wide">Dit rapport</span>
                  )}
                  {!isDone && isRelevant && (
                    <span className="text-[10px] text-[#c5a96f] font-medium uppercase tracking-wide">Relevant voor jou</span>
                  )}
                </div>
                <p className="text-xs text-white/40 mt-1 leading-relaxed">{s.description}</p>
                <p className="text-xs text-white/60 mt-1.5 font-medium">{s.price}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

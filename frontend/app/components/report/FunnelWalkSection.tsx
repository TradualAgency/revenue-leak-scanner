import { screenshotUrl } from "~/lib/api";
import type { ClientFunnelWalk, FunnelStepName, FunnelWalk } from "~/lib/types";
import ReportCard from "./ReportCard";
import SectionLabel from "./SectionLabel";
import StatusPill from "./StatusPill";

const STEP_LABEL: Record<FunnelStepName, string> = {
  home: "Homepage",
  search: "Zoeken",
  collection: "Collectie",
  product: "Productpagina",
  variant: "Variant kiezen",
  add_to_cart: "In winkelwagen",
  cart: "Winkelwagen",
  checkout: "Checkout",
};

const STATUS_LABEL: Record<FunnelWalk["status"], string> = {
  ok: "Afgerond",
  blocked: "Geblokkeerd door de winkel",
  failed: "Mislukt",
  skipped: "Overgeslagen",
};

function isOperatorWalk(walk: ClientFunnelWalk | FunnelWalk): walk is FunnelWalk {
  return "status" in walk;
}

/** The funnel agent's mobile walk: which steps a visitor got through, and what got in
 * the way, each with the screenshot the agent took. The client report gets the
 * projection (no evidence or cost); the operator view also shows status, the agent's
 * evidence and warnings. Euros for these issues live in the findings, not here. */
export default function FunnelWalkSection({ auditId, walk }: { auditId: string; walk: ClientFunnelWalk | FunnelWalk }) {
  const operator = isOperatorWalk(walk);
  if (operator && walk.status !== "ok") {
    return (
      <div>
        <SectionLabel>Funnel-test op mobiel</SectionLabel>
        <ReportCard className="p-5 space-y-1">
          <StatusPill tone="muted">{STATUS_LABEL[walk.status]}</StatusPill>
          {walk.warnings.map((w, i) => <p key={i} className="text-xs text-gray-500">{w}</p>)}
        </ReportCard>
      </div>
    );
  }

  return (
    <div>
      <SectionLabel>Funnel-test op mobiel</SectionLabel>
      <ReportCard className="p-5">
        {walk.summary_nl && <p className="text-sm text-gray-700 leading-relaxed mb-4">{walk.summary_nl}</p>}

        <ol className="flex flex-wrap gap-x-1 gap-y-2 text-[11px]">
          {walk.steps.map((s, i) => (
            <li key={`${s.step}-${i}`} className="flex items-center gap-1">
              <span
                className={`px-2 py-0.5 rounded-full border ${
                  s.reached ? "border-emerald-100 bg-emerald-50 text-emerald-700" : "border-red-100 bg-red-50 text-red-700"
                }`}
                title={s.note_nl ?? undefined}
              >
                {s.reached ? "✓" : "✕"} {STEP_LABEL[s.step]}
                {s.duration_ms != null && <span className="text-gray-500 tabular-nums"> · {(s.duration_ms / 1000).toFixed(1)}s</span>}
              </span>
              {i < walk.steps.length - 1 && <span className="text-gray-300">→</span>}
            </li>
          ))}
        </ol>

        {walk.issues.length === 0 ? (
          <p className="text-xs text-gray-500 mt-4">Geen obstakels gevonden tijdens de test.</p>
        ) : (
          <div className="mt-5 space-y-4">
            {walk.issues.map((issue, i) => (
              <div key={i} className="flex flex-col sm:flex-row gap-4 pt-4 border-t border-gray-100">
                {issue.screenshot_id && (
                  <a
                    href={screenshotUrl(auditId, issue.screenshot_id)}
                    target="_blank"
                    rel="noreferrer"
                    className="flex-shrink-0 self-start"
                  >
                    <img
                      src={screenshotUrl(auditId, issue.screenshot_id)}
                      alt={issue.description_nl}
                      loading="lazy"
                      className="w-40 rounded-lg border border-gray-200"
                    />
                  </a>
                )}
                <div className="min-w-0">
                  <p className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">{STEP_LABEL[issue.step]}</p>
                  <p className="text-sm font-medium text-gray-900 leading-relaxed">{issue.description_nl}</p>
                  {operator && "evidence_nl" in issue && (
                    <p className="text-xs text-gray-500 mt-1">
                      Bewijs: {issue.evidence_nl} <span className="font-mono text-gray-400">({issue.issue_key})</span>
                      {"machine_confirmed" in issue && issue.machine_confirmed && (
                        <span className="ml-1 text-emerald-700">· door de browser bevestigd</span>
                      )}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {operator && (
          <div className="mt-4 pt-3 border-t border-gray-100 space-y-1">
            {walk.warnings.map((w, i) => <p key={i} className="text-[11px] text-gray-500">{w}</p>)}
            <p className="text-[11px] text-gray-400">
              {walk.model} · {walk.input_tokens.toLocaleString("nl-NL")} in / {walk.output_tokens.toLocaleString("nl-NL")} uit
            </p>
          </div>
        )}
      </ReportCard>
    </div>
  );
}

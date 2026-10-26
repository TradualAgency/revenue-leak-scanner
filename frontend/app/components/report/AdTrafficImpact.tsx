import { eurRange } from "~/lib/format";
import type { AdTrafficImpact as AdTrafficImpactData } from "~/lib/types";
import ReportCard from "./ReportCard";
import SectionLabel from "./SectionLabel";

/** What slowness does to paid clicks: the bounce the model attributes to load time,
 * the revenue those clicks would have brought, and what drives it. Used on the client
 * report and the internal dashboard. */
export default function AdTrafficImpact({ data }: { data: AdTrafficImpactData }) {
  const bounce = data.est_post_click_bounce_pct;
  const excess = bounce != null ? Math.max(0, bounce - data.bounce_baseline_pct) : null;
  if (bounce == null && data.bounce_drivers.length === 0) return null;

  return (
    <div>
      <SectionLabel>Betaalde bezoekers die afhaken door traagheid</SectionLabel>
      <ReportCard className="p-5 space-y-4">
        <div className="flex flex-wrap gap-8">
          {bounce != null && (
            <div>
              <p className="text-2xl font-bold tabular-nums text-gray-900">{bounce.toFixed(0)}%</p>
              <p className="text-[11px] text-gray-500">
                haakt direct af (gezond is ~{data.bounce_baseline_pct.toFixed(0)}%)
              </p>
            </div>
          )}
          {excess != null && excess > 0 && data.est_drop_off_per_1000_clicks != null && (
            <div>
              <p className="text-2xl font-bold tabular-nums text-gray-900">{data.est_drop_off_per_1000_clicks}</p>
              <p className="text-[11px] text-gray-500">extra afhakers per 1.000 betaalde klikken</p>
            </div>
          )}
          {data.est_monthly_lost_revenue_eur_high ? (
            <div>
              <p className="text-2xl font-bold tabular-nums text-[#EF4444]">
                {eurRange(data.est_monthly_lost_revenue_eur_low, data.est_monthly_lost_revenue_eur_high)}
              </p>
              <p className="text-[11px] text-gray-500">misgelopen omzet per maand</p>
            </div>
          ) : null}
        </div>
        {excess === 0 && (
          <p className="text-xs text-gray-700">
            Betaalde bezoekers haken niet vaker af dan bij een gezonde winkel: de laadtijd kost hier geen advertentieklikken.
          </p>
        )}
        {data.bounce_drivers.length > 0 && (
          <ul className="space-y-1">
            {data.bounce_drivers.map((d, i) => (
              <li key={i} className="flex gap-2 text-xs text-gray-600">
                <span className="text-gray-400 flex-shrink-0">↑</span>
                {d}
              </li>
            ))}
          </ul>
        )}
        {data.methodology_note && (
          <p className="text-[11px] text-gray-500 leading-relaxed">{data.methodology_note}</p>
        )}
      </ReportCard>
    </div>
  );
}

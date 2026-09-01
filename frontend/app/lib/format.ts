// Shared euro/range formatting for the revenue-leak report. Before this module,
// `full-audit.$auditId.tsx` inlined `€${x.toLocaleString("nl-NL")}` at every call
// site and `revenue-leak.$auditId.tsx` had its own local `fmt()` — the two routes
// disagreed on how to render a zero-loss metric ("✓ geen verlies" vs "—"). This is
// the one place euro formatting happens now.
//
// Range collapsing: a low/high pair that's within noise of each other (< €50 or
// < 5% of the low bound, whichever is larger) renders as a single midpoint value
// instead of a pointless "€1.200 – €1.210".

export function eur(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `€${Math.round(n).toLocaleString("nl-NL")}`;
}

function isNegligibleRange(low: number, high: number): boolean {
  return Math.abs(high - low) < Math.max(50, Math.abs(low) * 0.05);
}

export function eurRange(low: number | null | undefined, high: number | null | undefined): string {
  if (low == null || high == null || Number.isNaN(low) || Number.isNaN(high)) return "—";
  if (isNegligibleRange(low, high)) return eur((low + high) / 2);
  return `${eur(low)} – ${eur(high)}`;
}

export interface EurRangeParts {
  /** The primary figure to render large (the low bound, or the midpoint when the
   * range has collapsed). */
  lead: string;
  /** "– €high", to render smaller/muted beneath or beside `lead`. Null when the
   * range collapsed to a single value — nothing to show. */
  tail: string | null;
}

/** For layouts where a single-line "€low – €high" string doesn't fit (hero
 * numbers, fixed-width KPI tiles) — render `lead` big and `tail` small. */
export function eurRangeParts(low: number | null | undefined, high: number | null | undefined): EurRangeParts {
  if (low == null || high == null || Number.isNaN(low) || Number.isNaN(high)) {
    return { lead: "—", tail: null };
  }
  if (isNegligibleRange(low, high)) {
    return { lead: eur((low + high) / 2), tail: null };
  }
  return { lead: eur(low), tail: `– ${eur(high)}` };
}

export function pct(n: number | null | undefined, digits = 0): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

export type SeverityLevel = "good" | "warning" | "critical" | "not-measured";

/** Maps a share of revenue (e.g. a loss / funnel.monthly_revenue_eur) to a status
 * keyword using caller-supplied thresholds, instead of the hard-coded absolute-euro
 * thresholds (`> 500`, `> 3000`, ...) the old components used — those don't mean
 * anything comparable across a €2k/mo store and a €200k/mo store. */
export function severityByShare(
  share: number | null | undefined,
  warnAt: number,
  critAt: number,
): SeverityLevel {
  if (share == null || Number.isNaN(share)) return "not-measured";
  if (share >= critAt) return "critical";
  if (share >= warnAt) return "warning";
  return "good";
}

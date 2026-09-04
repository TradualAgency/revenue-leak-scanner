import type { ReactNode } from "react";
import { TONE_TEXT, type Tone } from "./tone";

/** A single figure with a caption. Deliberately unboxed — the caller decides whether
 * it sits in its own `ReportCard` (the layer-score grid) or shares one with three
 * siblings (the ROI block).
 *
 * The figure is always `text-2xl`. That is not just consistency: it is the reason
 * `tone="accent"` is safe here and nowhere else, since tradual gold only clears the
 * large-text contrast bar from 24px up. */
export default function KpiTile({
  value,
  tail,
  label,
  tone = "neutral",
  align = "left",
}: {
  value: ReactNode;
  /** The "– €high" half of a collapsed range, rendered smaller beside the figure. */
  tail?: ReactNode;
  label: ReactNode;
  tone?: Tone;
  align?: "left" | "center";
}) {
  return (
    <div className={align === "center" ? "text-center" : ""}>
      <p className={`text-2xl font-bold tabular-nums leading-none ${TONE_TEXT[tone]}`}>
        {value}
        {tail && <span className="text-base font-semibold ml-1">{tail}</span>}
      </p>
      <p className="text-[11px] text-gray-500 mt-2 leading-snug">{label}</p>
    </div>
  );
}

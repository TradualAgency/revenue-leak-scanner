import type { ReactNode } from "react";
import type { EurRangeParts } from "~/lib/format";
import { TONE_TEXT, type Tone } from "./tone";

const SIZES = {
  xl: { lead: "text-5xl font-black", tail: "text-2xl font-bold ml-2" },
  lg: { lead: "text-4xl font-bold", tail: "text-xl font-bold ml-2" },
  md: { lead: "text-3xl font-bold", tail: "text-lg font-bold ml-2" },
} as const;

/** The big euro figure at the top of a report: `lead` large, `tail` ("– €high")
 * smaller beside it. Both pages had their own copy of this `eurRangeParts` split.
 *
 * Hierarchy between a primary and a secondary figure comes from `size`, not from
 * opacity — the dark pages faded the secondary to `/70`, which on `#FAFAF8` drops
 * red below the large-text contrast bar. */
export default function HeroFigure({
  parts,
  label,
  tone = "loss",
  size = "xl",
}: {
  parts: EurRangeParts;
  label: ReactNode;
  tone?: Tone;
  size?: keyof typeof SIZES;
}) {
  const s = SIZES[size];
  return (
    <div>
      <p className={`${s.lead} tabular-nums leading-none ${TONE_TEXT[tone]}`}>
        {parts.lead}
        {parts.tail && <span className={s.tail}>{parts.tail}</span>}
      </p>
      <p className="text-sm text-gray-500 mt-2">{label}</p>
    </div>
  );
}

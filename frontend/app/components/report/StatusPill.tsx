import type { ReactNode } from "react";
import { PILL_TONE, type PillTone } from "./tone";

const SIZES = {
  sm: "px-2 py-0.5 text-[10px] gap-1",
  md: "px-3 py-1 text-xs gap-1.5",
} as const;

/** Rounded status chip. Used for competitor measurement outcomes (`sm`) and for the
 * data-source badge on the revenue-leak report (`md`, with a leading icon). */
export default function StatusPill({
  tone,
  size = "sm",
  children,
}: {
  tone: PillTone;
  size?: keyof typeof SIZES;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full border font-medium ${SIZES[size]} ${PILL_TONE[tone]}`}
    >
      {children}
    </span>
  );
}

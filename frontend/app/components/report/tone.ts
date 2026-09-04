// The one place the light-theme semantic colours for the two prospect-facing report
// pages are defined. Both pages used to hard-code dark-theme `-400` colours inline,
// which is how they drifted apart in the first place.
//
// Contrast note: `#c5a96f` (tradual gold) on `#FAFAF8` is ~2.1:1. It fails AA for
// body text and only clears the 3:1 large-text bar from 24px up, so `accent` is only
// ever applied by `KpiTile`, which renders its figure at `text-2xl` (24px). Anywhere
// gold used to sit on a 9–12px caption, use `muted` instead.

/** Semantic role of a figure or label on a report page. */
export type Tone = "neutral" | "muted" | "loss" | "warning" | "good" | "accent";

export const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-gray-900",
  muted: "text-gray-500",
  /** A euro amount the store is losing. */
  loss: "text-[#EF4444]",
  warning: "text-amber-600",
  /** Beating the market. Brand green, matching how `results.tsx` renders positive KPIs. */
  good: "text-[#0a2f23]",
  /** Gold. Only legible at >=24px — see the contrast note above. */
  accent: "text-[#c5a96f]",
};

/** Status-pill colouring. Measurement outcomes, data-source badges. */
export type PillTone = "ok" | "warning" | "muted";

export const PILL_TONE: Record<PillTone, string> = {
  ok: "bg-emerald-50 text-emerald-700 border-emerald-100",
  warning: "bg-amber-50 text-amber-700 border-amber-100",
  muted: "bg-gray-100 text-gray-500 border-gray-200",
};

/** Full-width banner colouring. */
export type NoticeTone = "neutral" | "warning" | "danger";

export const NOTICE_TONE: Record<NoticeTone, string> = {
  neutral: "border-gray-200 bg-gray-50 text-gray-700",
  warning: "border-amber-200 bg-amber-50 text-amber-800",
  danger: "border-red-200 bg-red-50 text-red-700",
};

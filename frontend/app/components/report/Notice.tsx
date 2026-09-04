import type { ReactNode } from "react";
import { NOTICE_TONE, type NoticeTone } from "./tone";

/** Full-width banner for caveats: contradicting inputs, model warnings, a market that
 * sits below the general benchmark. */
export default function Notice({
  tone = "neutral",
  title,
  children,
}: {
  tone?: NoticeTone;
  title?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={`border rounded-2xl p-4 ${NOTICE_TONE[tone]}`}>
      {title && (
        <p className="text-xs font-semibold uppercase tracking-wide mb-1">{title}</p>
      )}
      <div className="text-xs leading-relaxed">{children}</div>
    </div>
  );
}

import type { ReactNode } from "react";

/** The small uppercase eyebrow above every report section. Was copy-pasted about a
 * dozen times across the two report pages. */
export default function SectionLabel({
  className = "mb-3",
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <p className={`text-xs font-semibold text-gray-400 uppercase tracking-widest ${className}`}>
      {children}
    </p>
  );
}

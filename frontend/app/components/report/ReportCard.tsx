import type { ReactNode } from "react";

/** The flat bordered surface every report section sits on. Padding is left to the
 * caller because sections legitimately differ (a table wants `overflow-hidden` and no
 * padding, a notice wants `p-4`). */
export default function ReportCard({
  className = "",
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`bg-white rounded-2xl shadow-sm border border-gray-100 ${className}`}>
      {children}
    </div>
  );
}

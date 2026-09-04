import type { ReactNode } from "react";

/** The while-we-measure state. Both report pages poll for minutes, so this is the
 * screen a prospect sees longest. */
export default function ReportSpinner({
  label,
  sublabel,
}: {
  label: string;
  sublabel?: ReactNode;
}) {
  return (
    <div className="max-w-3xl mx-auto py-24 text-center">
      <div className="w-8 h-8 border-2 border-[#c5a96f]/30 border-t-[#c5a96f] rounded-full animate-spin mx-auto mb-4" />
      <p className="text-sm text-gray-700">{label}</p>
      {sublabel && <p className="text-xs text-gray-500 mt-2">{sublabel}</p>}
    </div>
  );
}

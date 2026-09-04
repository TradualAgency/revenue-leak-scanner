import type { ReactNode } from "react";
import Footer from "~/components/Footer";
import Header from "~/components/Header";

// Page frame for the two prospect-facing report pages. Replaces the hand-rolled top
// bar each of them carried (a gold "Tradual" wordmark + report type + store URL) with
// the site header and footer, so a report no longer looks like a different product
// than the page the prospect arrived from. The store URL is report metadata, not
// chrome — it moved into each page's hero.
export default function ReportShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-tradual-bg text-gray-900">
      <Header />
      <main className="flex-1 py-16 px-4">{children}</main>
      <Footer />
    </div>
  );
}

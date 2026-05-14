import { useState } from "react";
import { useNavigate } from "react-router";
import { createFullAudit } from "~/lib/api";
import type { ScanLevel } from "~/lib/types";
import Header from "~/components/Header";
import Footer from "~/components/Footer";

export function meta() {
  return [
    { title: "Full Audit — Tradual Internal" },
    { name: "robots", content: "noindex,nofollow" },
  ];
}

const SCAN_LEVELS: { value: ScanLevel; label: string; desc: string }[] = [
  {
    value: "outside-only",
    label: "Outside-only",
    desc: "Automated — alleen publiek toegankelijke signalen (headers, DOM, PageSpeed, scripts)",
  },
  {
    value: "semi",
    label: "Semi",
    desc: "Automated + handmatig aangevulde velden (bijv. inbox-review, admin inzage)",
  },
  {
    value: "full-access",
    label: "Full-access",
    desc: "Volledige admin-toegang — diepste scan inclusief backend data",
  },
];

export default function FullAuditIntake() {
  const navigate = useNavigate();
  const [storeUrl, setStoreUrl] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [scanLevel, setScanLevel] = useState<ScanLevel>("outside-only");
  const [industry, setIndustry] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!storeUrl.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await createFullAudit({
        store_url: storeUrl.trim(),
        company_name: companyName.trim() || undefined,
        scan_level: scanLevel,
        industry: industry.trim() || undefined,
        contact_email: contactEmail.trim() || undefined,
      });
      navigate(`/full-audit/${res.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start audit");
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#FAFAF8] flex flex-col">
      <Header />

      <main className="flex-1 py-16 px-4">
        <div className="max-w-xl mx-auto">
          <div className="mb-8">
            <span className="inline-block text-xs font-semibold uppercase tracking-widest text-[#c5a96f] mb-3">
              Intern gebruik
            </span>
            <h1
              className="text-3xl font-semibold text-[#1a1f2e]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Prospect Full Audit
            </h1>
            <p className="text-gray-500 mt-2 text-sm">
              Tech-zwaar. Diagnose-first. Evidence bij elk signaal.
            </p>
          </div>

          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 flex flex-col gap-5">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-gray-700">
                Store URL <span className="text-red-500">*</span>
              </label>
              <input
                type="url"
                required
                value={storeUrl}
                onChange={(e) => setStoreUrl(e.target.value)}
                placeholder="https://www.example.com"
                className="border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c5a96f]/40 focus:border-[#c5a96f]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-gray-700">Bedrijfsnaam</label>
              <input
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="Allbirds"
                className="border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c5a96f]/40 focus:border-[#c5a96f]"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium text-gray-700">Scan level</label>
              <div className="flex flex-col gap-2">
                {SCAN_LEVELS.map(({ value, label, desc }) => (
                  <label
                    key={value}
                    className={`flex items-start gap-3 border rounded-xl p-3.5 cursor-pointer transition-colors ${
                      scanLevel === value
                        ? "border-[#c5a96f] bg-[#c5a96f]/5"
                        : "border-gray-200 hover:border-gray-300"
                    }`}
                  >
                    <input
                      type="radio"
                      name="scan_level"
                      value={value}
                      checked={scanLevel === value}
                      onChange={() => setScanLevel(value)}
                      className="mt-0.5 accent-[#c5a96f]"
                    />
                    <div>
                      <span className="text-sm font-medium text-gray-800">{label}</span>
                      <p className="text-xs text-gray-500 mt-0.5">{desc}</p>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-gray-700">Industrie</label>
              <input
                type="text"
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                placeholder="Fashion DTC, Education, ..."
                className="border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c5a96f]/40 focus:border-[#c5a96f]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-gray-700">Contact e-mail</label>
              <input
                type="email"
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
                placeholder="naam@bedrijf.com"
                className="border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c5a96f]/40 focus:border-[#c5a96f]"
              />
            </div>

            <button
              type="submit"
              disabled={loading || !storeUrl.trim()}
              className="bg-[#1a1f2e] hover:bg-[#2d3550] disabled:opacity-50 text-white font-medium px-6 py-3 rounded-xl transition-colors text-sm mt-2"
            >
              {loading ? "Audit starten..." : "Start Full Audit →"}
            </button>
          </form>
        </div>
      </main>

      <Footer />
    </div>
  );
}

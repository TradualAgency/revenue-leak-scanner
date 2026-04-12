import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { createLead } from "~/lib/api";
import type { LeadCreatePayload } from "~/lib/types";

export default function LeadCaptureForm() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState<LeadCreatePayload>({
    email: "",
    store_url: "",
    platform: "shopify",
    monthly_revenue: 0,
    monthly_traffic: 0,
  });

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: name === "monthly_revenue" || name === "monthly_traffic" ? Number(value) : value,
    }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await createLead(form);
      sessionStorage.setItem(`tradual_email_${result.report_id}`, form.email);
      navigate(`/results/${result.report_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="email" className="text-sm font-medium text-gray-600">
            Email address
          </label>
          <input
            id="email"
            type="email"
            name="email"
            required
            placeholder="you@example.com"
            value={form.email}
            onChange={handleChange}
            className="border border-gray-200 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#c5a96f] focus:border-transparent"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="store_url" className="text-sm font-medium text-gray-600">
            Store URL
          </label>
          <input
            id="store_url"
            type="url"
            name="store_url"
            required
            placeholder="https://yourstore.com"
            value={form.store_url}
            onChange={handleChange}
            className="border border-gray-200 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#c5a96f] focus:border-transparent"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="platform" className="text-sm font-medium text-gray-600">
            Platform
          </label>
          <select
            id="platform"
            name="platform"
            value={form.platform}
            onChange={handleChange}
            className="border border-gray-200 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#c5a96f] focus:border-transparent bg-white"
          >
            <option value="shopify">Shopify</option>
            <option value="woocommerce">WooCommerce</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="monthly_revenue" className="text-sm font-medium text-gray-600">
            Monthly Revenue (USD)
          </label>
          <input
            id="monthly_revenue"
            type="number"
            name="monthly_revenue"
            required
            min={0}
            placeholder="e.g. 25000"
            value={form.monthly_revenue || ""}
            onChange={handleChange}
            className="border border-gray-200 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#c5a96f] focus:border-transparent"
          />
        </div>

        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <label htmlFor="monthly_traffic" className="text-sm font-medium text-gray-600">
            Monthly Visitors
          </label>
          <input
            id="monthly_traffic"
            type="number"
            name="monthly_traffic"
            required
            min={0}
            placeholder="e.g. 10000"
            value={form.monthly_traffic || ""}
            onChange={handleChange}
            className="border border-gray-200 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#c5a96f] focus:border-transparent"
          />
        </div>
      </div>

      {error && (
        <p className="text-sm text-[#EF4444] bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={loading}
        className="bg-[#c5a96f] hover:bg-[#b8975e] disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium py-4 rounded-lg text-base transition-colors tracking-wide"
      >
        {loading ? "Starting scan..." : "Show Me My Revenue Leaks"}
      </button>

      <p className="text-center text-xs text-gray-400">
        Free. No credit card required. Results in ~60 seconds.
      </p>
    </form>
  );
}

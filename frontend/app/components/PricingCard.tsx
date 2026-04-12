interface PricingFeature {
  text: string;
}

interface PricingCardProps {
  tier: "free" | "premium";
  title: string;
  subtitle: string;
  features: PricingFeature[];
  ctaLabel: string;
  ctaHref: string;
  ctaExternal?: boolean;
}

export default function PricingCard({
  tier,
  title,
  subtitle,
  features,
  ctaLabel,
  ctaHref,
  ctaExternal,
}: PricingCardProps) {
  const isPremium = tier === "premium";

  return (
    <div
      className={`rounded-2xl p-8 flex flex-col gap-6 ${
        isPremium
          ? "bg-[#0a2f23] text-white shadow-xl ring-1 ring-[#c5a96f]/40"
          : "bg-white text-gray-900 shadow-md border border-gray-200"
      }`}
    >
      <div>
        {isPremium && (
          <span className="inline-block bg-[#c5a96f] text-white text-xs font-medium uppercase tracking-wider px-3 py-1 rounded-full mb-3">
            Recommended
          </span>
        )}
        <h3 className="text-2xl font-semibold" style={{ fontFamily: "var(--font-serif)" }}>{title}</h3>
        <p className={`mt-1 text-sm ${isPremium ? "text-gray-400" : "text-gray-500"}`}>
          {subtitle}
        </p>
      </div>

      <ul className="flex flex-col gap-3">
        {features.map((f, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <svg
              className="w-5 h-5 mt-0.5 flex-shrink-0 text-[#c5a96f]"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            <span className={isPremium ? "text-gray-300" : "text-gray-700"}>{f.text}</span>
          </li>
        ))}
      </ul>

      <div className="mt-auto">
        <a
          href={ctaHref}
          className={`block text-center font-medium px-6 py-3 rounded-lg transition-colors tracking-wide ${
            isPremium
              ? "bg-[#c5a96f] hover:bg-[#b8975e] text-white"
              : "bg-[#0a2f23] hover:bg-[#1a4a3a] text-white"
          }`}
        >
          {ctaLabel}
        </a>
      </div>
    </div>
  );
}

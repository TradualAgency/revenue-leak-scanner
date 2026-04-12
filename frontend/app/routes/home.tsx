import Header from "~/components/Header";
import Footer from "~/components/Footer";
import LeadCaptureForm from "~/components/LeadCaptureForm";
import PricingCard from "~/components/PricingCard";
import TestimonialCard from "~/components/TestimonialCard";
import FaqItem from "~/components/FaqItem";

export function meta() {
  return [
    { title: "Tradual — Free Revenue Leak Audit for Your Store" },
    {
      name: "description",
      content:
        "Find out how much revenue your store is losing to slow load times and bloated plugins. Free scan in 60 seconds.",
    },
  ];
}

const painPoints = [
  {
    icon: (
      <svg className="w-8 h-8 text-[#0a2f23]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    title: "Slow Load Times",
    description:
      "Every extra second of load time costs you up to 7% in conversions. Most stores lose thousands monthly without realizing it.",
  },
  {
    icon: (
      <svg className="w-8 h-8 text-[#0a2f23]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
      </svg>
    ),
    title: "Plugin Bloat",
    description:
      "Unused and redundant plugins drag down performance and add unnecessary recurring costs. The average store wastes $200–500/mo on plugins they don't need.",
  },
  {
    icon: (
      <svg className="w-8 h-8 text-[#0a2f23]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    title: "Hidden Costs",
    description:
      "Most store owners spend $3,000–6,000/year on unused tools without realizing it. Plugin subscriptions and performance penalties silently drain your margins.",
  },
];

const steps = [
  {
    step: "01",
    title: "Enter Your Store URL",
    description: "Enter your store URL and a few details. Takes 30 seconds.",
  },
  {
    step: "02",
    title: "We Scan Your Store",
    description: "Our engine analyzes page speed, detects plugins, and calculates revenue impact. Takes about 60 seconds.",
  },
  {
    step: "03",
    title: "Get Your Free Report",
    description: "Get a clear, actionable report — your store's technical health, not vague advice.",
  },
];

const testimonials = [
  {
    quote: "We had no idea we were paying $450/month for plugins we didn't even use. Tradual found it in 60 seconds.",
    name: "Sarah M.",
    role: "Shopify Store Owner",
    metric: "Saved $450/mo",
  },
  {
    quote: "Our load time dropped from 4.2s to 1.8s after following the recommendations. Conversions jumped 12%.",
    name: "James K.",
    role: "E-commerce Manager",
    metric: "+12% conversions",
  },
  {
    quote: "The free scan alone was more useful than the $2,000 audit we paid for last year.",
    name: "Lisa T.",
    role: "WooCommerce Store Owner",
    metric: "Free vs $2,000",
  },
];

const faqs = [
  {
    question: "Is this really free?",
    answer:
      "Yes — the Free Scan costs nothing and requires no credit card. A paid Full Audit is available if you want deeper analysis and hands-on optimization.",
  },
  {
    question: "How long does the scan take?",
    answer: "About 60 seconds. Just enter your store URL and we'll have your results ready in about a minute.",
  },
  {
    question: "What do you do with my data?",
    answer:
      "Your data is only used to generate your report. We never sell it, and you can request deletion at any time.",
  },
  {
    question: "Will this slow down my store?",
    answer:
      "No. We scan your store externally — the same way a visitor's browser would. There's no impact on your store's performance.",
  },
  {
    question: "What if I already have a CRO specialist?",
    answer:
      "We complement them perfectly. We fix the technical engine — speed, infrastructure, plugins. Your CRO specialist then optimizes how visitors convert. We build the car; they drive it.",
  },
  {
    question: "What platforms do you support?",
    answer:
      "Shopify and WooCommerce are fully supported with detailed plugin detection. Other platforms receive a basic performance scan.",
  },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-[#FAFAF8] text-gray-900 flex flex-col">
      <Header />

      {/* Hero */}
      <section className="bg-gradient-to-br from-[#0a2f23] to-[#1a4a3a] text-white py-28 px-4">
        <div className="max-w-4xl mx-auto text-center flex flex-col items-center gap-6">
          <div className="inline-block bg-white/10 text-[#c5a96f] text-xs font-medium uppercase tracking-widest px-4 py-1.5 rounded-full">
            Free Revenue Audit
          </div>
          <h1
            className="text-4xl sm:text-5xl md:text-6xl font-semibold leading-tight"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Unlock the Revenue Your Store
            <br />
            <span className="text-[#c5a96f]">Is Leaving on the Table.</span>
          </h1>
          <p className="text-[#c5a96f] font-medium text-lg">Get Your Free Audit in 60 Seconds.</p>
          <p className="text-lg sm:text-xl text-gray-300 max-w-2xl font-light">
            We scan your store's speed, plugins, and infrastructure — then show you exactly how much revenue you're losing and how to get it back.
          </p>
          <a
            href="#scan"
            className="bg-[#c5a96f] hover:bg-[#b8975e] text-white font-medium px-8 py-4 rounded-xl text-lg transition-colors shadow-lg tracking-wide"
          >
            Get My Free Audit
          </a>
          <p className="text-gray-400 text-sm">No credit card required · Results in 60 seconds</p>
        </div>
      </section>

      {/* Social Proof Bar */}
      <section className="py-8 px-4 bg-white border-b border-gray-100">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-sm text-gray-500 font-medium">
            Trusted by store owners generating over{" "}
            <span className="text-[#0a2f23] font-semibold">$50M in combined annual revenue</span>
          </p>
        </div>
      </section>

      {/* Pain Points */}
      <section className="py-24 px-4">
        <div className="max-w-6xl mx-auto">
          <h2
            className="text-3xl font-semibold text-center mb-14 text-gray-900"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Is Your Store Making These Costly Mistakes?
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {painPoints.map((point) => (
              <div key={point.title} className="bg-white rounded-2xl p-8 shadow-sm border border-gray-100 flex flex-col gap-4">
                <div className="w-14 h-14 rounded-xl bg-[#FAFAF8] flex items-center justify-center border border-gray-100">
                  {point.icon}
                </div>
                <h3 className="text-xl font-semibold" style={{ fontFamily: "var(--font-serif)" }}>{point.title}</h3>
                <p className="text-gray-500 text-sm leading-relaxed">{point.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="py-24 px-4 bg-white">
        <div className="max-w-6xl mx-auto">
          <h2
            className="text-3xl font-semibold text-center mb-4 text-gray-900"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            How It Works
          </h2>
          <p className="text-center text-gray-500 mb-16 max-w-xl mx-auto">
            Three simple steps to uncover exactly where your revenue is going.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
            {steps.map((s) => (
              <div key={s.step} className="flex flex-col items-center text-center gap-4">
                <div
                  className="w-16 h-16 rounded-2xl bg-[#0a2f23] text-white flex items-center justify-center text-xl font-semibold shadow-md"
                  style={{ fontFamily: "var(--font-serif)" }}
                >
                  {s.step}
                </div>
                <h3 className="text-lg font-semibold">{s.title}</h3>
                <p className="text-gray-500 text-sm leading-relaxed">{s.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="py-24 px-4 bg-[#FAFAF8]">
        <div className="max-w-6xl mx-auto">
          <h2
            className="text-3xl font-semibold text-center mb-14 text-gray-900"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Store Owners Are Already Saving Thousands
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {testimonials.map((t) => (
              <TestimonialCard key={t.name} {...t} />
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-24 px-4 bg-white">
        <div className="max-w-4xl mx-auto">
          <h2
            className="text-3xl font-semibold text-center mb-4"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Simple, Transparent Pricing
          </h2>
          <p className="text-center text-gray-500 mb-14 max-w-xl mx-auto">
            Start for free. Upgrade when you want the full picture.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-start">
            <PricingCard
              tier="free"
              title="Free Scan"
              subtitle="See how your store performs technically"
              features={[
                { text: "Performance score (0-100)" },
                { text: "Total plugin count" },
                { text: "Estimated monthly revenue loss" },
                { text: "Total plugin subscription costs" },
              ]}
              ctaLabel="Start My Free Audit"
              ctaHref="#scan"
            />
            <PricingCard
              tier="premium"
              title="Full Audit"
              subtitle="We fix your foundation — your CRO specialist does the rest"
              features={[
                { text: "Everything in Free Scan" },
                { text: "Plugin-by-plugin audit: which tools belong in your stack?" },
                { text: "Technical optimization roadmap: build your fastest store" },
                { text: "1-on-1 strategy call: what Tradual fixes and where a CRO specialist takes over" },
                { text: "Ongoing monitoring of your technical foundation" },
              ]}
              ctaLabel="Book a Free Strategy Call"
              ctaHref="mailto:info@tradual.com"
              ctaExternal
            />
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="py-24 px-4 bg-[#FAFAF8]">
        <div className="max-w-2xl mx-auto">
          <h2
            className="text-3xl font-semibold text-center mb-14 text-gray-900"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Frequently Asked Questions
          </h2>
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 px-8">
            {faqs.map((faq) => (
              <FaqItem key={faq.question} question={faq.question} answer={faq.answer} />
            ))}
          </div>
        </div>
      </section>

      {/* Lead Capture Form */}
      <section id="scan" className="py-24 px-4 bg-white">
        <div className="max-w-2xl mx-auto">
          <div className="text-center mb-10">
            <h2
              className="text-3xl font-semibold mb-3"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              See How Much Revenue You're Missing
            </h2>
            <p className="text-gray-500">
              Takes 30 seconds. Your personalized report is ready in about a minute.
            </p>
          </div>
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
            <LeadCaptureForm />
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}

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
    <div className="min-h-screen bg-tradual-bg text-tradual-primary flex flex-col">
      <Header />

      {/* Hero */}
      <section className="bg-gradient-to-br from-tradual-primary to-tradual-primary-light text-white py-28 px-4">
        <div className="max-w-4xl mx-auto text-center flex flex-col items-center gap-6">
          <p
            className="uppercase text-tradual-accent text-[11px] tracking-[0.18em]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Free Revenue Leak Audit
          </p>
          <h1
            className="text-4xl sm:text-5xl md:text-[64px] font-medium leading-[1.05]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Unlock the revenue your store
            <br />
            is leaving on the table.
          </h1>
          <p className="text-lg sm:text-xl text-white/80 max-w-2xl leading-relaxed">
            We scan your store's speed, plugins, and infrastructure — then show you exactly how much revenue you're losing and how to get it back.
          </p>
          <div className="flex flex-col sm:flex-row items-center gap-4 mt-2">
            <a
              href="#scan"
              className="inline-flex items-center justify-center bg-tradual-accent hover:opacity-90 text-tradual-primary font-medium px-8 py-3.5 text-base transition-opacity tracking-wide"
            >
              Get My Free Audit
            </a>
            <a
              href="#how-it-works"
              className="inline-flex items-center justify-center bg-transparent border border-tradual-accent text-tradual-accent hover:bg-tradual-accent/10 font-medium px-8 py-3.5 text-base transition-colors tracking-wide"
            >
              How It Works
            </a>
          </div>
          <p className="text-white/50 text-sm mt-1">No credit card required &middot; Results in 60 seconds</p>
        </div>
      </section>

      {/* Social Proof Bar */}
      <section className="py-8 px-4 bg-white border-b border-tradual-border">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-sm text-tradual-body font-medium">
            Trusted by store owners generating over{" "}
            <span className="text-tradual-primary font-semibold">$50M in combined annual revenue</span>
          </p>
        </div>
      </section>

      {/* Pain Points */}
      <section className="py-24 px-4">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <p
              className="uppercase text-tradual-accent text-[11px] tracking-[0.18em] mb-4"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              The problem
            </p>
            <h2
              className="text-[32px] md:text-[44px] leading-[1.08] font-medium text-tradual-primary"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Is your store making these costly mistakes?
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {painPoints.map((point) => (
              <div key={point.title} className="bg-white p-8 border border-tradual-border flex flex-col gap-4">
                <div className="w-14 h-14 flex items-center justify-center border border-tradual-border">
                  {point.icon}
                </div>
                <h3 className="text-xl font-medium" style={{ fontFamily: "var(--font-serif)" }}>{point.title}</h3>
                <p className="text-tradual-body text-sm leading-relaxed">{point.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="py-24 px-4 bg-tradual-surface-muted">
        <div className="max-w-6xl mx-auto">
          <div className="mb-12">
            <p
              className="uppercase text-tradual-accent text-[11px] tracking-[0.18em] mb-4"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              The process
            </p>
            <h2
              className="text-[32px] md:text-[44px] leading-[1.08] font-medium text-tradual-primary mb-4"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              How it works
            </h2>
            <p className="text-tradual-body text-base md:text-lg max-w-xl">
              Three simple steps to uncover exactly where your revenue is going.
            </p>
          </div>
          <div className="divide-y divide-tradual-primary/10 border-y border-tradual-primary/10">
            {steps.map((s) => (
              <div key={s.step} className="flex flex-col md:flex-row md:items-start gap-4 py-8">
                <span
                  className="text-[48px] leading-none text-tradual-accent/30 shrink-0 w-20 text-center md:text-left"
                  style={{ fontFamily: "var(--font-serif)" }}
                >
                  {s.step}
                </span>
                <div className="flex-1 min-w-0">
                  <h3 className="text-xl text-tradual-primary mb-1" style={{ fontFamily: "var(--font-serif)" }}>
                    {s.title}
                  </h3>
                  <p className="text-tradual-body text-sm md:text-base">{s.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="py-24 px-4 bg-white">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <p
              className="uppercase text-tradual-accent text-[11px] tracking-[0.18em] mb-4"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Proof
            </p>
            <h2
              className="text-[32px] md:text-[44px] leading-[1.08] font-medium text-tradual-primary"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Store owners are already saving thousands
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {testimonials.map((t) => (
              <TestimonialCard key={t.name} {...t} />
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-24 px-4 bg-tradual-surface-muted">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-14">
            <p
              className="uppercase text-tradual-accent text-[11px] tracking-[0.18em] mb-4"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Pricing
            </p>
            <h2
              className="text-[32px] md:text-[44px] leading-[1.08] font-medium text-tradual-primary mb-4"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Simple, transparent pricing
            </h2>
            <p className="text-tradual-body text-base md:text-lg max-w-xl mx-auto">
              Start for free. Upgrade when you want the full picture.
            </p>
          </div>
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
      <section className="py-24 px-4 bg-white">
        <div className="max-w-2xl mx-auto">
          <div className="text-center mb-14">
            <p
              className="uppercase text-tradual-accent text-[11px] tracking-[0.18em] mb-4"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              FAQ
            </p>
            <h2
              className="text-[32px] md:text-[44px] leading-[1.08] font-medium text-tradual-primary"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Frequently asked questions
            </h2>
          </div>
          <div className="bg-white border border-tradual-border px-8">
            {faqs.map((faq) => (
              <FaqItem key={faq.question} question={faq.question} answer={faq.answer} />
            ))}
          </div>
        </div>
      </section>

      {/* Lead Capture Form */}
      <section id="scan" className="py-24 px-4 bg-tradual-surface-muted">
        <div className="max-w-2xl mx-auto">
          <div className="text-center mb-10">
            <p
              className="uppercase text-tradual-accent text-[11px] tracking-[0.18em] mb-4"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Get started
            </p>
            <h2
              className="text-[32px] md:text-[44px] leading-[1.08] font-medium text-tradual-primary mb-3"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              See how much revenue you're missing
            </h2>
            <p className="text-tradual-body">
              Takes 30 seconds. Your personalized report is ready in about a minute.
            </p>
          </div>
          <div className="bg-white border border-tradual-border p-8">
            <LeadCaptureForm />
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}

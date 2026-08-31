export default function Header() {
  return (
    <div className="sticky top-4 z-50 px-4 pt-4">
      <header className="max-w-6xl mx-auto bg-[#0a2f23]/95 backdrop-blur-md border border-white/10 rounded-2xl shadow-sm shadow-black/10 px-6 sm:px-8 py-3.5">
        <div className="flex items-center justify-between">
          <a
            href="/"
            className="text-base uppercase font-bold tracking-wide text-white"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Tradual
          </a>
          <nav
            className="hidden md:flex items-center gap-8 text-sm text-white/80"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            <a href="#how-it-works" className="hover:text-[#c5a96f] transition-colors">
              How It Works
            </a>
            <a href="#pricing" className="hover:text-[#c5a96f] transition-colors">
              Pricing
            </a>
          </nav>
          <a
            href="#scan"
            className="bg-[#c5a96f] hover:opacity-90 text-[#0a2f23] text-sm font-medium px-5 py-2.5 transition-opacity tracking-wide"
          >
            Get Free Audit
          </a>
        </div>
      </header>
    </div>
  );
}

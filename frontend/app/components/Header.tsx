export default function Header({ overlay = false }: { overlay?: boolean }) {
  if (overlay) {
    return (
      <div className="fixed top-6 lg:top-12 left-0 right-0 z-50 px-5 sm:px-6 lg:px-8">
        <header className="max-w-7xl mx-auto bg-tradual-primary/10 backdrop-blur-md border border-tradual-primary/15 rounded-2xl shadow-sm px-6 sm:px-8 py-4 text-white">
          <div className="flex items-center justify-between">
            <a href="/" className="text-lg uppercase font-bold text-white">
              Tradual
            </a>
            <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-white">
              <a href="#how-it-works" className="hover:text-tradual-accent transition-colors">
                How It Works
              </a>
              <a href="#pricing" className="hover:text-tradual-accent transition-colors">
                Pricing
              </a>
            </nav>
            <a
              href="#scan"
              className="bg-tradual-accent text-tradual-primary px-6 py-2 font-medium hover:opacity-90 transition font-serif"
            >
              Get Free Audit
            </a>
          </div>
        </header>
      </div>
    );
  }

  return (
    <header className="sticky top-0 z-50 bg-white border-b border-gray-100">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <a href="/" className="text-xl font-semibold text-[#0a2f23]" style={{ fontFamily: "var(--font-serif)" }}>
          Tradual
        </a>
        <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-gray-500">
          <a href="#how-it-works" className="hover:text-[#c5a96f] transition-colors">
            How It Works
          </a>
          <a href="#pricing" className="hover:text-[#c5a96f] transition-colors">
            Pricing
          </a>
        </nav>
        <a
          href="#scan"
          className="bg-[#c5a96f] hover:bg-[#b8975e] text-white text-sm font-medium px-5 py-2 rounded-lg transition-colors tracking-wide"
        >
          Get Free Audit
        </a>
      </div>
    </header>
  );
}

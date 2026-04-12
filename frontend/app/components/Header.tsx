export default function Header() {
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

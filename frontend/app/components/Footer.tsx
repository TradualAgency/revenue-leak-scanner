export default function Footer() {
  return (
    <footer className="bg-white text-[#0a2f23] border-t border-[#0a2f23]/10">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-14 grid grid-cols-1 sm:grid-cols-3 gap-10">
        <div>
          <span className="text-lg font-bold uppercase tracking-wide" style={{ fontFamily: "var(--font-serif)" }}>
            Tradual
          </span>
          <p className="mt-3 text-xs text-[#0a2f23]/60 uppercase tracking-[0.12em]" style={{ fontFamily: "var(--font-serif)" }}>
            Find Your Revenue Leaks
          </p>
        </div>
        <nav>
          <p className="text-[10px] uppercase tracking-[0.18em] text-[#c5a96f] mb-4" style={{ fontFamily: "var(--font-serif)" }}>
            Product
          </p>
          <ul className="space-y-3 text-sm text-[#0a2f23]/80">
            <li>
              <a href="#how-it-works" className="hover:text-[#c5a96f] transition-colors">
                How It Works
              </a>
            </li>
            <li>
              <a href="#pricing" className="hover:text-[#c5a96f] transition-colors">
                Pricing
              </a>
            </li>
          </ul>
        </nav>
        <nav>
          <p className="text-[10px] uppercase tracking-[0.18em] text-[#c5a96f] mb-4" style={{ fontFamily: "var(--font-serif)" }}>
            Contact
          </p>
          <ul className="space-y-3 text-sm text-[#0a2f23]/80">
            <li>
              <a href="mailto:info@tradual.com" className="hover:text-[#c5a96f] transition-colors">
                info@tradual.com
              </a>
            </li>
          </ul>
        </nav>
      </div>
      <div className="border-t border-[#0a2f23]/10">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-5 text-center text-xs text-[#0a2f23]/60">
          &copy; {new Date().getFullYear()} Tradual. All rights reserved.
        </div>
      </div>
    </footer>
  );
}

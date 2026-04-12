export default function Footer() {
  return (
    <footer className="bg-[#0a2f23] text-gray-400 py-10 border-t border-[#c5a96f]/20">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm">
        <p>&copy; {new Date().getFullYear()} Tradual. All rights reserved.</p>
        <div className="flex gap-6">
          <a href="mailto:info@tradual.com" className="hover:text-[#c5a96f] transition-colors">
            Contact
          </a>
          <a href="#pricing" className="hover:text-[#c5a96f] transition-colors">
            Pricing
          </a>
        </div>
      </div>
    </footer>
  );
}

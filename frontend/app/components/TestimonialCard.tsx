interface TestimonialCardProps {
  quote: string;
  name: string;
  role: string;
  metric: string;
}

export default function TestimonialCard({ quote, name, role, metric }: TestimonialCardProps) {
  return (
    <div className="bg-white p-8 border border-tradual-border flex flex-col gap-5">
      <p className="text-[#0a2f23]/80 text-sm leading-relaxed italic">"{quote}"</p>
      <div className="flex items-center justify-between border-t border-tradual-border pt-4">
        <div>
          <div className="text-sm font-medium text-[#0a2f23]" style={{ fontFamily: "var(--font-serif)" }}>{name}</div>
          <div className="text-xs text-tradual-body">{role}</div>
        </div>
        <span className="text-[#c5a96f] text-xs font-semibold uppercase tracking-wide whitespace-nowrap">
          {metric}
        </span>
      </div>
    </div>
  );
}

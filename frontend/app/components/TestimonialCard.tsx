interface TestimonialCardProps {
  quote: string;
  name: string;
  role: string;
  metric: string;
}

export default function TestimonialCard({ quote, name, role, metric }: TestimonialCardProps) {
  return (
    <div className="bg-white rounded-2xl p-8 shadow-sm border border-gray-100 flex flex-col gap-5">
      <p className="text-gray-700 text-sm leading-relaxed italic">"{quote}"</p>
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-gray-900">{name}</div>
          <div className="text-xs text-gray-500">{role}</div>
        </div>
        <span className="bg-[#c5a96f]/10 text-[#c5a96f] text-xs font-semibold px-3 py-1 rounded-full whitespace-nowrap">
          {metric}
        </span>
      </div>
    </div>
  );
}

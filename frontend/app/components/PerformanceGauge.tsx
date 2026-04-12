interface PerformanceGaugeProps {
  score: number; // 0-100
  size?: number;
}

function scoreColor(score: number): string {
  if (score >= 70) return "#c5a96f";
  if (score >= 40) return "#F59E0B";
  return "#EF4444";
}

function scoreLabel(score: number): string {
  if (score >= 70) return "Good";
  if (score >= 40) return "Needs Work";
  return "Poor";
}

export default function PerformanceGauge({ score, size = 160 }: PerformanceGaugeProps) {
  const radius = 54;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * radius;
  // 270-degree arc (3/4 of circle)
  const arcLength = circumference * 0.75;
  const filled = arcLength * (score / 100);
  const color = scoreColor(score);

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        style={{ transform: "rotate(135deg)", position: "absolute", top: 0, left: 0 }}
        aria-hidden="true"
      >
        {/* Track */}
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke="#E5E7EB"
          strokeWidth="12"
          strokeDasharray={`${arcLength} ${circumference - arcLength}`}
          strokeLinecap="round"
        />
        {/* Progress */}
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="12"
          strokeDasharray={`${filled} ${circumference - filled}`}
          strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.6s ease" }}
        />
      </svg>
      {/* Centered label */}
      <div className="flex flex-col items-center z-10">
        <span className="text-4xl font-bold" style={{ color }} aria-label={`Score: ${score}`}>
          {score}
        </span>
        <span className="text-xs font-medium text-gray-500">{scoreLabel(score)}</span>
      </div>
    </div>
  );
}

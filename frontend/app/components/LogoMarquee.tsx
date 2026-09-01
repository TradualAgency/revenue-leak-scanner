interface Logo {
  name: string;
  src: string;
}

interface LogoMarqueeProps {
  logos: Logo[];
  className?: string;
}

export default function LogoMarquee({ logos, className = "" }: LogoMarqueeProps) {
  return (
    <div
      role="region"
      aria-label="Brands we work with"
      className={`group overflow-hidden marquee-mask ${className}`}
    >
      <div className="marquee-track flex w-max items-center animate-marquee group-hover:[animation-play-state:paused]">
        {logos.map((logo) => (
          <div key={logo.name} className="shrink-0 px-12">
            <img
              src={logo.src}
              alt={logo.name}
              loading="lazy"
              className="h-16 w-auto"
            />
          </div>
        ))}
        {logos.map((logo) => (
          <div key={`${logo.name}-clone`} data-marquee-clone className="shrink-0 px-12" aria-hidden="true">
            <img
              src={logo.src}
              alt=""
              loading="lazy"
              className="h-16 w-auto"
            />
          </div>
        ))}
      </div>
    </div>
  );
}

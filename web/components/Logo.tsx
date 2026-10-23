// FreeRise mark: sun over horizon (docs/brand/logos.html). Lower sun half masked by a small rect so rx corners survive.
export function Logo({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={className} aria-hidden="true">
      <rect width="64" height="64" rx="15" fill="#0e4f45" />
      <circle cx="32" cy="38" r="12" fill="#f2b84b" />
      <rect x="19" y="38" width="26" height="13" fill="#0e4f45" />
      <path d="M10 38h44" stroke="#eaf6f1" strokeWidth="3" strokeLinecap="round" />
      <path d="M16 46h32M22 53h20" stroke="#7fd1b5" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

/** Sun-over-horizon decoration (hero card, empty states). `ground` paints the strip under the horizon. */
export function SunHorizon({ width = 120, ground = "var(--bg)", line = "var(--border)", className }: { width?: number; ground?: string; line?: string; className?: string }) {
  return (
    <svg width={width} height={(width * 110) / 190} viewBox="0 0 190 110" className={className} aria-hidden="true">
      <circle cx="95" cy="95" r="52" fill="var(--sun)" opacity="0.95" />
      <rect x="0" y="92" width="190" height="20" fill={ground} />
      <path d="M10 92h170" stroke={line} strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

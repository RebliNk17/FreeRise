/** A household member's initial in a circle; `i` (their place in the household) alternates the color. */
export function Avatar({ name, i = 0, size = 40, className = "" }: { name: string; i?: number; size?: number; className?: string }) {
  return (
    <span
      aria-hidden
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-display font-extrabold uppercase ${i % 2 ? "bg-positive-fill text-white" : "bg-sun text-on-sun"} ${className}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.42) }}
    >
      {name.slice(0, 1)}
    </span>
  );
}

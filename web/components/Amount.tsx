import { formatILS } from "@/lib/format";
import { splitMoney } from "@/lib/home";
import type { Money as MoneyValue } from "@/lib/api";

/** plain: no green for positives (magnitudes like "spent"). */
export function Amount({ value, className = "", plain = false }: { value: MoneyValue; className?: string; plain?: boolean }) {
  const n = Number(value);
  return (
    <span dir="ltr" className={`font-display tabular-nums ${n > 0 && !plain ? "text-positive" : ""} ${className}`}>
      {formatILS(n).replace(/[‎‏]/g, "")}
    </span>
  );
}

/** "1,819.2 ₪" with the decimals in a smaller font (home cards). */
export function Money({ value, className = "" }: { value: number; className?: string }) {
  const { sign, int, dec } = splitMoney(value);
  return (
    <span dir="ltr" className={`font-display tabular-nums whitespace-nowrap ${className}`}>
      {sign}
      {int}
      {dec && <span className="text-[0.7em] opacity-70">{dec}</span>}
      <span className="text-[0.8em] font-normal"> ₪</span>
    </span>
  );
}

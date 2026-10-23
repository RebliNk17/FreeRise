import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";

const NAV = "flex size-8 shrink-0 items-center justify-center rounded-full border";

/** Centered month title + sub-line between round ‹ › buttons; next is disabled when `next` is null. */
export function CycleSwitcher({ title, sub, prev, next, prevLabel = "החודש הקודם", nextLabel = "החודש הבא", level: H = "h1" }: { level?: "h1" | "h2"; title: React.ReactNode; sub?: React.ReactNode; prev: string; next: string | null; prevLabel?: string; nextLabel?: string }) {
  return (
    <div className="flex items-center justify-center gap-3.5">
      <Link href={prev} className={`${NAV} border-border bg-surface hover:bg-sunken`} aria-label={prevLabel}>
        <ChevronRight size={18} />
      </Link>
      <div className="min-w-0 text-center">
        <H className="section-title">{title}</H>
        {sub && <p className="text-xs text-muted">{sub}</p>}
      </div>
      {next ? (
        <Link href={next} className={`${NAV} border-border bg-surface hover:bg-sunken`} aria-label={nextLabel}>
          <ChevronLeft size={18} />
        </Link>
      ) : (
        <button type="button" disabled className={`${NAV} border-hairline text-disabled`} aria-label={nextLabel}>
          <ChevronLeft size={18} />
        </button>
      )}
    </div>
  );
}

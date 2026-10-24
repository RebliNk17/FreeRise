import Link from "next/link";
import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";

const NAV = "flex size-8 shrink-0 items-center justify-center rounded-full border";

/** Centered month title (a button opening a picker when `onPick` is set) + sub-line between round ‹ › buttons; next is disabled when `next` is null. */
export function CycleSwitcher({
  title,
  sub,
  prev,
  next,
  prevLabel = "החודש הקודם",
  nextLabel = "החודש הבא",
  level: H = "h1",
  onPick,
}: {
  level?: "h1" | "h2";
  onPick?: () => void;
  title: React.ReactNode;
  sub?: React.ReactNode;
  prev: string;
  next: string | null;
  prevLabel?: string;
  nextLabel?: string;
}) {
  return (
    <div className="flex items-center justify-center gap-3.5">
      <Link href={prev} className={`${NAV} border-border bg-surface hover:bg-sunken`} aria-label={prevLabel}>
        <ChevronRight size={18} />
      </Link>
      {onPick ? (
        <button type="button" className="flex min-w-0 items-center gap-1.5 rounded-xl px-2 py-1 text-center hover:bg-sunken" aria-label="בחירת חודש התזרים" onClick={onPick}>
          <span>
            <H className="section-title">{title}</H>
            {sub && <span className="block text-xs text-muted">{sub}</span>}
          </span>
          <ChevronDown size={18} aria-hidden />
        </button>
      ) : (
        <div className="min-w-0 text-center">
          <H className="section-title">{title}</H>
          {sub && <p className="text-xs text-muted">{sub}</p>}
        </div>
      )}
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

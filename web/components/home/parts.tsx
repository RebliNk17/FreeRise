"use client";

import { useEffect, useRef, useState } from "react";
import { EllipsisVertical } from "lucide-react";
import { Money } from "@/components/Amount";
import { ProgressBar } from "@/components/Card";
import { weekBarPercent } from "@/lib/format";

/** ⋮ overflow menu; closes on outside pointer, Escape or selection. */
export function Menu({ label, items, icon = <EllipsisVertical size={18} /> }: { label: string; items: { label: string; onSelect: () => void; danger?: boolean; icon?: React.ReactNode }[]; icon?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button type="button" className="flex size-9 items-center justify-center rounded-xl text-muted hover:bg-sunken hover:text-text" aria-label={label} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {icon}
      </button>
      {open && (
        <ul role="menu" className="card absolute end-0 top-full z-30 mt-1 min-w-52 overflow-hidden py-1">
          {items.map((i) => (
            <li key={i.label} role="none">
              <button
                type="button"
                role="menuitem"
                className={`flex min-h-11 w-full items-center gap-2.5 px-4 py-2.5 text-start text-sm font-semibold hover:bg-sunken ${i.danger ? "text-danger" : ""}`}
                onClick={() => {
                  setOpen(false);
                  i.onSelect();
                }}
              >
                {i.icon && (
                  <span className={`flex shrink-0 ${i.danger ? "" : "text-muted"}`} aria-hidden>
                    {i.icon}
                  </span>
                )}
                {i.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** RiseUp-like hue per section: [spent amount, bar fill, bar track]. */
const TONES = {
  plain: ["text-text", "bg-brand", "bg-sunken"],
  variable: ["text-sun-strong", "bg-sun", "bg-sun-soft"],
  category: ["text-info", "bg-info", "bg-info-soft"],
  income: ["text-positive", "bg-positive-fill", "bg-brand-soft"],
} as const;

/** "יצא" (bold, colored) vs "צפוי לצאת", progress bar, and what's left / over. */
export function SpentHeader({
  spent,
  expected,
  labels = ["יצא", "צפוי לצאת"],
  remaining = ["נשאר להוציא", "חריגה של"],
  overIsBad = true,
  tone = "plain",
}: {
  spent: number;
  expected: number;
  labels?: [string, string];
  remaining?: [string, string];
  overIsBad?: boolean;
  tone?: keyof typeof TONES;
}) {
  const [text, fill, track] = TONES[tone];
  const over = spent > expected;
  const bad = over && overIsBad;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-end justify-between gap-4">
        <div className="flex flex-col">
          <span className="text-xs text-muted">{labels[0]}</span>
          <Money value={spent} className={`text-[28px] leading-tight font-extrabold ${bad ? "text-danger" : text}`} />
        </div>
        <div className="flex flex-col items-end">
          <span className="text-xs text-muted">{labels[1]}</span>
          <Money value={expected} className="text-lg font-bold text-muted" />
        </div>
      </div>
      <ProgressBar percent={weekBarPercent(spent, expected)} danger={bad} label={`${labels[0]} מתוך ${labels[1]}`} fill={fill} track={track} />
      <p className={`text-sm ${bad ? "font-semibold text-danger" : "text-muted"}`}>
        {over ? remaining[1] : remaining[0]} <Money value={Math.abs(expected - spent)} className="font-bold" />
      </p>
    </div>
  );
}

/** Rubik section title with an optional small action on the other side. */
export function SectionHeader({ title, action, id }: { title: React.ReactNode; action?: React.ReactNode; id?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 px-1 pt-1.5">
      <h2 id={id} className="section-title">
        {title}
      </h2>
      {action}
    </div>
  );
}

/** Column header row for the breakdown tables. */
export function TableHead({ cols }: { cols: [string, string, string] }) {
  return (
    <div className="grid grid-cols-[1fr_5rem_5rem_18px] gap-2 border-b border-hairline px-1 pb-2 text-xs font-semibold text-muted">
      <span>{cols[0]}</span>
      <span className="text-end">{cols[1]}</span>
      <span className="text-end">{cols[2]}</span>
      <span />
    </div>
  );
}

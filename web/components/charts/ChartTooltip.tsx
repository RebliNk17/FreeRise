"use client";

import { Money } from "@/components/Amount";

export type TooltipRow = { label: string; value: number; tone?: "danger" | "positive" | "muted" };

/** Themed tooltip / caption body: Hebrew title + labelled money rows (tokens only, so readable in both themes). */
export function TooltipCard({ title, rows }: { title: string; rows: TooltipRow[] }) {
  return (
    <div dir="rtl" className="min-w-36 rounded-[14px] border border-border bg-surface px-3 py-2 text-start text-text shadow-card">
      <p className="mb-1 text-[13px] font-bold">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="flex items-baseline justify-between gap-3 text-xs">
          <span className="text-muted">{r.label}</span>
          <Money value={r.value} className={`font-bold ${r.tone === "danger" ? "text-danger" : r.tone === "positive" ? "text-positive" : r.tone === "muted" ? "text-muted" : ""}`} />
        </p>
      ))}
    </div>
  );
}

/** Recharts `content` adapter: `describe` turns the hovered datum into title + rows. */
export function chartTooltip<T>(describe: (d: T) => { title: string; rows: TooltipRow[] }) {
  function Content({ active, payload }: { active?: boolean; payload?: readonly { payload?: unknown }[] }) {
    const d = payload?.[0]?.payload as T | undefined;
    if (!active || !d) return null;
    return <TooltipCard {...describe(d)} />;
  }
  return Content;
}

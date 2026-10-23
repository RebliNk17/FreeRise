"use client";

import { useState, useSyncExternalStore } from "react";
import { Bar, BarChart, Cell, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Money } from "@/components/Amount";
import { captionIndex, compactMoney } from "@/lib/chartFormat";
import { TooltipCard, type TooltipRow } from "./ChartTooltip";

/** One bar per month. `full` is the caption/tooltip title ("אפריל 2026"), `label` the axis tick ("אפר"). */
export type MonthDatum = { key: string; label: string; full: string; value: number; expected?: number };

const RM = "(prefers-reduced-motion: reduce)";
const subscribeRM = (cb: () => void) => {
  const m = matchMedia(RM);
  m.addEventListener("change", cb);
  return () => m.removeEventListener("change", cb);
};

/** Bars grow once on mount (600ms); never again on data changes, never under reduced motion. */
function useMountAnimation() {
  const reduced = useSyncExternalStore(subscribeRM, () => matchMedia(RM).matches, () => true);
  const [done, setDone] = useState(false);
  return { isAnimationActive: !reduced && !done, animationDuration: 600, onAnimationEnd: () => setDone(true) };
}

/**
 * Design-A month bar chart, shared by every monthly chart in the app.
 * - kind "net": green above 0, coral below, hairline at 0. kind "amount": brand bars; over `expected` turns coral
 *   when `overIsBad`. With `expected`, a soft track bar shows what was expected behind each bar.
 * - Order: RTL like the rest of the app — data is oldest first and drawn right-to-left, so the newest month is on the left.
 * - Tap/click (or the month chips) selects a bar; the caption above shows it (newest by default), so it works without hover.
 * - Value labels above bars when there are 6 or fewer; dashed average line with "ממוצע ₪X".
 */
export function MonthBars({
  data,
  kind = "amount",
  valueLabel,
  expectedLabel = "צפוי",
  overIsBad = true,
  average,
  ariaLabel,
  height = 176,
  currentKey,
}: {
  data: MonthDatum[];
  kind?: "net" | "amount";
  valueLabel: string;
  expectedLabel?: string;
  overIsBad?: boolean;
  average?: number | null;
  ariaLabel: string;
  height?: number;
  /** The month in progress / being viewed: drawn with a sun outline. */
  currentKey?: string;
}) {
  const [picked, setPicked] = useState<number | null>(null);
  const anim = useMountAnimation();
  const sel = captionIndex(data.length, picked);
  const hasExpected = data.some((d) => d.expected != null);
  const over = (d: MonthDatum) => overIsBad && d.expected != null && d.value > d.expected + 0.5;
  const fill = (d: MonthDatum) => (kind === "net" ? (d.value >= 0 ? "var(--positive)" : "var(--danger)") : over(d) ? "var(--danger)" : "var(--brand)");
  const rows = (d: MonthDatum): TooltipRow[] => [
    { label: valueLabel, value: d.value, tone: kind === "net" ? (d.value < 0 ? "danger" : "positive") : over(d) ? "danger" : undefined },
    ...(d.expected != null ? [{ label: expectedLabel, value: d.expected, tone: "muted" as const }] : []),
  ];
  const cur = data[sel];

  return (
    <div className="flex flex-col gap-2">
      <div className="flex min-h-11 items-end justify-between gap-2" aria-live="polite">
        {cur && (
          <p className="flex flex-col">
            <span className="text-xs text-muted">{cur.full}</span>
            <span className="flex items-baseline gap-2">
              <Money value={Math.round(cur.value)} className={`text-xl font-extrabold ${rows(cur)[0].tone === "danger" ? "text-danger" : ""}`} />
              {cur.expected != null && (
                <span className="text-xs text-muted">
                  {expectedLabel} <Money value={Math.round(cur.expected)} />
                </span>
              )}
            </span>
          </p>
        )}
        {average != null && (
          <p className="text-xs text-muted">
            ממוצע <Money value={Math.round(average)} className="font-bold text-text" />
          </p>
        )}
      </div>
      <div dir="ltr" style={{ height }} role="img" aria-label={ariaLabel}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: data.length <= 6 ? 18 : 6, right: average != null ? 66 : 4, left: 4, bottom: 0 }} barCategoryGap="22%" barGap={hasExpected ? "-100%" : 4}>
            <XAxis dataKey="label" tickLine={false} axisLine={false} reversed interval={0} tick={{ fontSize: data.length > 6 ? 10 : 12, fill: "var(--muted)" }} />
            <YAxis hide domain={kind === "net" ? [(min: number) => Math.min(0, min), (max: number) => Math.max(0, max)] : [0, "auto"]} />
            {kind === "net" && <ReferenceLine y={0} stroke="var(--border)" />}
            {average != null && (
              <ReferenceLine
                y={average}
                stroke="var(--sun-strong)"
                strokeDasharray="4 4"
                label={{ value: `\u2067ממוצע ${compactMoney(average)}\u2069`, position: "right", fill: "var(--muted)", fontSize: 10 }}
              />
            )}
            <Tooltip cursor={{ fill: "var(--sunken)", fillOpacity: 0.5, radius: 8 }} content={({ active, payload }) => {
                const d = payload?.[0]?.payload as MonthDatum | undefined;
                return active && d ? <TooltipCard title={d.full} rows={rows(d)} /> : null;
              }} isAnimationActive={false} />
            {hasExpected && <Bar dataKey="expected" fill="var(--sunken)" stroke="var(--border)" radius={[8, 8, 8, 8]} isAnimationActive={false} onClick={(_, i) => setPicked(i)} />}
            <Bar
              dataKey="value"
              radius={[8, 8, 8, 8]}
              background={hasExpected || kind === "net" ? undefined : { fill: "var(--sunken)", radius: 8 }}
              cursor="pointer"
              onClick={(_, i) => setPicked(i)}
              {...anim}
            >
              {data.map((d, i) => (
                <Cell
                  key={d.key}
                  fill={fill(d)}
                  fillOpacity={i === sel || d.key === currentKey ? 1 : 0.62}
                  stroke={i === sel ? "var(--sun-strong)" : d.key === currentKey ? "var(--sun)" : undefined}
                  strokeWidth={i === sel || d.key === currentKey ? 2 : 0}
                />
              ))}
              {data.length <= 6 && (
                <LabelList
                  dataKey="value"
                  content={({ x, y, width, height: h, value }) => {
                    const v = Number(value);
                    const below = v < 0;
                    return (
                      <text x={Number(x) + Number(width) / 2} y={below ? Number(y) + Number(h) + 12 : Number(y) - 5} textAnchor="middle" fontSize={10} fontWeight={700} fill="var(--muted)">
                        {compactMoney(v)}
                      </text>
                    );
                  }}
                />
              )}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {/* Keyboard / screen-reader way to pick a month (bars are SVG); same right-to-left order as the bars. */}
      <div className="flex flex-wrap justify-center gap-1" role="group" aria-label="בחירת חודש">
        {[...data.keys()].map((i) => (
          <button key={data[i].key} type="button" aria-pressed={i === sel} aria-label={data[i].full} className={`chip min-h-11 min-w-11 justify-center ${i === sel ? "bg-sun-soft text-text" : "bg-transparent text-muted"}`} onClick={() => setPicked(i)}>
            {data[i].label}
          </button>
        ))}
      </div>
    </div>
  );
}

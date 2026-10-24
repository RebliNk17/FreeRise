"use client";

import { useState } from "react";
import { Money } from "@/components/Amount";
import { Card } from "@/components/Card";
import { formatILS } from "@/lib/format";
import { totalSegments, type HomeData, type TotalSegment } from "@/lib/home";
import { Expander } from "./Expander";

/** RiseUp's sentence (spent so far out of what's expected), a donut of spent by group beside it, and the breakdown below. */
export function TotalCard({ d }: { d: HomeData }) {
  const { spent, expected } = d.total;
  const segs = totalSegments(d);
  const over = spent > expected + 0.5;
  return (
    <Card>
      <div className="flex items-center gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <p className="text-lg leading-snug font-bold">
            סך כל ההוצאות עד עכשיו <Money value={spent} className="text-danger" /> מתוך <Money value={expected} className="text-danger" /> שצפויים לצאת.
          </p>
          <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted" aria-label="מקרא">
            {segs.map((s) => (
              <li key={s.key} className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-full" style={{ background: s.tone }} aria-hidden />
                {s.label} <Money value={s.spent} className="font-semibold text-text" />
              </li>
            ))}
          </ul>
        </div>
        <Donut segs={segs} spent={spent} expected={expected} />
      </div>
      {over && (
        <p className="text-sm font-semibold text-danger">
          חריגה של <Money value={spent - expected} className="font-bold" /> מהצפוי
        </p>
      )}
      <Expander label={<span className="text-sm font-semibold text-brand">פירוט לפי סוג</span>} className="border-t border-hairline pt-1.5" buttonClassName="flex min-h-11 px-1">
        <ul className="flex flex-col divide-y divide-hairline pt-1">
          {segs.map((s) => {
            const o = s.spent > s.expected + 0.5;
            return (
              <li key={s.key} className="flex min-h-11 items-center gap-2 text-sm">
                <span className="size-2.5 shrink-0 rounded-full" style={{ background: s.tone }} aria-hidden />
                <span className="flex-1 font-semibold">{s.label}</span>
                <span className="text-xs text-muted">{s.key === "savings" ? "הופקד" : "יצא"}</span>
                <Money value={s.spent} className={`font-bold ${o && s.key !== "savings" ? "text-danger" : ""}`} />
                <span className="text-xs text-muted">
                  מתוך <Money value={s.expected} />
                </span>
              </li>
            );
          })}
        </ul>
      </Expander>
    </Card>
  );
}

const R = 46;
const C = 2 * Math.PI * R;
const GAP = 2; // surface gap between arcs

/** Ring = everything expected this cycle; arcs = spent per group (clockwise from the top), the rest of the ring is still to come.
 * Hover or focus an arc: the center reads that group instead of the overall percent. */
function Donut({ segs, spent, expected }: { segs: TotalSegment[]; spent: number; expected: number }) {
  const [active, setActive] = useState<TotalSegment | null>(null);
  const pct = expected > 0 ? Math.round((spent / expected) * 100) : 0;
  const lens = segs.map((s) => (s.percent / 100) * C);
  const arcs = segs.map((s, i) => ({ s, len: lens[i], start: lens.slice(0, i).reduce((a, b) => a + b, 0) }));
  return (
    <div className="relative size-30 shrink-0">
      <svg viewBox="0 0 120 120" className="size-full" role="group" aria-label={`הוצאות לפי סוג: ${pct}% מהצפוי`}>
        <g transform="rotate(-90 60 60)" fill="none">
          <circle cx="60" cy="60" r={R} stroke="var(--sunken)" strokeWidth="14" />
          {arcs.map(({ s, len, start }) =>
            len > GAP ? (
              <circle key={s.key} cx="60" cy="60" r={R} stroke={s.tone} strokeWidth={active?.key === s.key ? 18 : 14} strokeDasharray={`${len - GAP} ${C}`} strokeDashoffset={-(start + GAP / 2)} className="transition-[stroke-width] duration-150 motion-reduce:transition-none" />
            ) : null,
          )}
          {/* Hit targets wider than the arcs; focusable for keyboard readers of the center label. */}
          {arcs.map(({ s, len, start }) =>
            len > GAP ? (
              <circle
                key={s.key}
                cx="60"
                cy="60"
                r={R}
                stroke="transparent"
                strokeWidth="30"
                strokeDasharray={`${len} ${C}`}
                strokeDashoffset={-start}
                pointerEvents="stroke"
                tabIndex={0}
                aria-label={`${s.label}: ${formatILS(s.spent)}`}
                className="cursor-default outline-none"
                onPointerEnter={() => setActive(s)}
                onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(s)}
                onBlur={() => setActive(null)}
              />
            ) : null,
          )}
        </g>
      </svg>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center" aria-hidden>
        {active ? (
          <>
            <span className="text-[11px] text-muted">{active.label}</span>
            <Money value={active.spent} className="text-sm font-bold" />
          </>
        ) : (
          <>
            <span className="font-display text-xl leading-none font-extrabold">{pct}%</span>
            <span className="text-[11px] text-muted">מהצפוי</span>
          </>
        )}
      </div>
    </div>
  );
}

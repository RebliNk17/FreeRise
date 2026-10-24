"use client";

import { Money } from "@/components/Amount";
import { Card } from "@/components/Card";
import { formatCycleRange } from "@/lib/format";
import { totalSegments, type HomeData } from "@/lib/home";
import { Expander } from "./Expander";

/** "סך ההוצאות החודש": spent so far, stacked by group (fixed / variable / savings), what's still expected; tap for the breakdown. */
export function TotalCard({ d }: { d: HomeData }) {
  const { spent, expected } = d.total;
  const segs = totalSegments(d);
  const over = spent > expected + 0.5;
  const end = formatCycleRange(d.cycle.start, d.cycle.end).split(" – ")[1];
  return (
    <Card title="סך ההוצאות החודש">
      <div className="flex items-end justify-between gap-3">
        <span className="flex flex-col">
          <span className="text-xs text-muted">יצא</span>
          <Money value={Math.round(spent)} className={`font-display text-[34px] leading-none font-extrabold ${over ? "text-danger" : ""}`} />
        </span>
        <span className="text-sm text-muted">
          מתוך <Money value={Math.round(expected)} className="font-bold text-text" /> צפויים
        </span>
      </div>
      <div className={`flex h-3 w-full gap-0.5 overflow-hidden rounded-full bg-sunken ${over ? "ring-2 ring-danger" : ""}`} role="img" aria-label={segs.map((s) => `${s.label} ${Math.round(s.spent)} ₪`).join(", ")}>
        {segs.map((s) => s.percent > 0 && <span key={s.key} className={`h-full ${s.tone} first:rounded-s-full last:rounded-e-full`} style={{ width: `${s.percent}%` }} />)}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted" aria-hidden>
        {segs.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className={`size-2.5 rounded-full ${s.tone}`} />
            {s.label}
          </li>
        ))}
      </ul>
      <p className={`text-sm ${over ? "font-semibold text-danger" : "text-muted"}`}>
        {over ? (
          <>
            חריגה של <Money value={Math.round(spent - expected)} className="font-bold" /> מהצפוי
          </>
        ) : (
          <>
            עוד <Money value={Math.round(expected - spent)} className="font-bold text-text" /> צפויים לצאת עד <span dir="ltr">{end}</span>
          </>
        )}
      </p>
      <Expander label={<span className="text-sm font-semibold text-brand">פירוט לפי סוג</span>} className="border-t border-hairline pt-1.5" buttonClassName="flex min-h-11 px-1">
        <ul className="flex flex-col divide-y divide-hairline pt-1">
          {segs.map((s) => {
            const o = s.spent > s.expected + 0.5;
            return (
              <li key={s.key} className="flex min-h-11 items-center gap-2 text-sm">
                <span className={`size-2.5 shrink-0 rounded-full ${s.tone}`} aria-hidden />
                <span className="flex-1 font-semibold">{s.label}</span>
                <span className="text-xs text-muted">{s.key === "savings" ? "הופקד" : "יצא"}</span>
                <Money value={Math.round(s.spent)} className={`font-bold ${o && s.key !== "savings" ? "text-danger" : ""}`} />
                <span className="text-xs text-muted">
                  מתוך <Money value={Math.round(s.expected)} />
                </span>
              </li>
            );
          })}
        </ul>
      </Expander>
    </Card>
  );
}

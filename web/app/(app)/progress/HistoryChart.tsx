"use client";

import { useState } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { Amount } from "@/components/Amount";
import { Card, Status } from "@/components/Card";
import { Select } from "@/components/ui/Select";
import { categoryLabel, formatILS, monthName } from "@/lib/format";
import { progressHistoryPath, type ProgressHistory } from "@/lib/history";
import { useApi } from "@/lib/useApi";

type Tab = "income" | "fixed" | "variable";
const TABS: { key: Tab; label: string }[] = [
  { key: "income", label: "הכנסות" },
  { key: "fixed", label: "קבועות" },
  { key: "variable", label: "משתנות" },
];
const PERIODS = [3, 6, 12];

/** Bar per month for income / fixed / variable (optionally one category), with the monthly average; tap a bar for its amount. */
export function HistoryChart() {
  const [tab, setTab] = useState<Tab>("variable");
  const [months, setMonths] = useState(6);
  const [cat, setCat] = useState<number | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const { data, error } = useApi<ProgressHistory>(progressHistoryPath(tab, months, cat));
  const bars = (data?.cycles ?? []).map((c, i) => ({ i, label: monthName(c.label_month).slice(0, 3), full: `${monthName(c.label_month)} ${c.label_year}`, total: c.total }));
  const sel = picked != null ? bars[picked] : bars.at(-1);
  const alt = bars.map((b) => `${b.full}: ${formatILS(Math.round(b.total))}`).join(", ");
  const pick = (f: () => void) => () => {
    f();
    setPicked(null);
  };

  return (
    <Card title="היסטוריה חודשית">
      <div role="group" aria-label="סוג" className="grid grid-cols-3 gap-1 rounded-2xl bg-sunken p-1">
        {TABS.map((t) => (
          <button key={t.key} type="button" aria-pressed={tab === t.key} className={`min-h-11 rounded-xl text-sm font-bold ${tab === t.key ? "bg-surface text-text shadow-card" : "text-muted"}`} onClick={pick(() => (setTab(t.key), setCat(null)))}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="תקופה" className="flex gap-1">
          {PERIODS.map((m) => (
            <button key={m} type="button" aria-pressed={months === m} className={`chip min-h-11 px-3.5 text-sm ${months === m ? "bg-brand-fill text-brand-fg" : "bg-sunken text-text"}`} onClick={pick(() => setMonths(m))}>
              {m} חודשים
            </button>
          ))}
        </div>
        <Select
          className="min-w-40 flex-1"
          label="קטגוריה"
          value={cat == null ? "" : String(cat)}
          onChange={(v) => pick(() => setCat(v ? Number(v) : null))()}
          options={[{ value: "", label: "כל הקטגוריות" }, ...(data?.categories ?? []).map((c) => ({ value: String(c.category_id), label: categoryLabel(c.name) }))]}
        />
      </div>
      <Status loading={!data} error={error} />
      {data && (
        <>
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-sm" aria-live="polite">
              {sel && (
                <>
                  <span className="text-muted">{sel.full}: </span>
                  <Amount value={sel.total} plain className="font-bold" />
                </>
              )}
            </p>
            <p className="text-xs text-muted">
              ממוצע חודשי <Amount value={Math.round(data.average)} plain className="font-bold text-text" />
            </p>
          </div>
          <div dir="ltr" className="h-44" role="img" aria-label={alt}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={bars} margin={{ top: 4, right: 0, left: 0, bottom: 0 }} onClick={(s) => s?.activeTooltipIndex != null && setPicked(Number(s.activeTooltipIndex))}>
                <XAxis dataKey="label" tickLine={false} axisLine={false} reversed interval={0} tick={{ fontSize: months > 6 ? 10 : 12, fill: "var(--muted)" }} />
                <YAxis hide />
                <ReferenceLine y={data.average} stroke="var(--sun-strong)" strokeDasharray="4 4" />
                <Bar dataKey="total" radius={[6, 6, 0, 0]} isAnimationActive={false} cursor="pointer">
                  {bars.map((b) => (
                    <Cell key={b.i} fill={b.i === (sel?.i ?? -1) ? "var(--brand)" : "var(--positive)"} fillOpacity={b.i === (sel?.i ?? -1) ? 1 : 0.55} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {/* Keyboard / screen-reader alternative to tapping a bar. */}
          <div className="flex flex-wrap gap-1" role="group" aria-label="בחירת חודש">
            {bars.map((b) => (
              <button key={b.i} type="button" aria-pressed={b.i === sel?.i} className={`chip min-h-11 min-w-11 justify-center ${b.i === sel?.i ? "bg-brand-soft text-brand" : "bg-sunken text-muted"}`} onClick={() => setPicked(b.i)} aria-label={b.full}>
                {b.label}
              </button>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

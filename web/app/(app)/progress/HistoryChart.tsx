"use client";

import { useState } from "react";
import { Card, Status } from "@/components/Card";
import { MonthBars } from "@/components/charts/MonthBars";
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

/** Bar per month for income / fixed / variable (optionally one category), with the monthly average; tap a bar for its amount (MonthBars). */
export function HistoryChart() {
  const [tab, setTab] = useState<Tab>("variable");
  const [months, setMonths] = useState(6);
  const [cat, setCat] = useState<number | null>(null);
  const { data, error } = useApi<ProgressHistory>(progressHistoryPath(tab, months, cat));
  const bars = (data?.cycles ?? []).map((c) => ({ key: `${c.label_year}-${c.label_month}`, label: monthName(c.label_month).slice(0, 3), full: `${monthName(c.label_month)} ${c.label_year}`, value: c.total }));
  const alt = bars.map((b) => `${b.full}: ${formatILS(Math.round(b.value))}`).join(", ");

  return (
    <Card title="היסטוריה חודשית">
      <div role="group" aria-label="סוג" className="grid grid-cols-3 gap-1 rounded-2xl bg-sunken p-1">
        {TABS.map((t) => (
          <button key={t.key} type="button" aria-pressed={tab === t.key} className={`min-h-11 rounded-xl text-sm font-bold ${tab === t.key ? "bg-surface text-text shadow-card" : "text-muted"}`} onClick={() => (setTab(t.key), setCat(null))}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="תקופה" className="flex gap-1">
          {PERIODS.map((m) => (
            <button key={m} type="button" aria-pressed={months === m} className={`chip min-h-11 px-3.5 text-sm ${months === m ? "bg-brand-fill text-brand-fg" : "bg-sunken text-text"}`} onClick={() => setMonths(m)}>
              {m} חודשים
            </button>
          ))}
        </div>
        <Select
          className="min-w-40 flex-1"
          label="קטגוריה"
          value={cat == null ? "" : String(cat)}
          onChange={(v) => setCat(v ? Number(v) : null)}
          options={[{ value: "", label: "כל הקטגוריות" }, ...(data?.categories ?? []).map((c) => ({ value: String(c.category_id), label: categoryLabel(c.name) }))]}
        />
      </div>
      <Status loading={!data} error={error} />
      {data && (
        <>
          <MonthBars key={`${tab}-${months}-${cat}`} data={bars} valueLabel={tab === "income" ? "נכנס" : "יצא"} overIsBad={false} average={data.average} ariaLabel={alt} />
        </>
      )}
    </Card>
  );
}

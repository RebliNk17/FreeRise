"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { CURSOR, TOOLTIP_STYLE } from "@/components/chart";
import { Amount } from "@/components/Amount";
import { Card, Status } from "@/components/Card";
import { CategorySelect } from "@/components/CategorySelect";
import type { Cost } from "@/lib/api";
import { formatILS, monthName, txnCount } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function lastYear() {
  const to = new Date();
  const from = new Date(to);
  from.setFullYear(to.getFullYear() - 1);
  from.setDate(from.getDate() + 1);
  return { from: iso(from), to: iso(to) };
}

export default function CostPage() {
  const [range] = useState(lastYear);
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [from, setFrom] = useState(range.from);
  const [to, setTo] = useState(range.to);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  const params = new URLSearchParams();
  if (debounced) params.set("q", debounced);
  if (categoryId != null) params.set("category_id", String(categoryId));
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const { data, error } = useApi<Cost>(`/cost?${params}`);
  const filtered = Boolean(debounced || categoryId != null);

  const txParams = new URLSearchParams(params);
  txParams.set("label", "חיפוש הוצאות");
  const chart = (data?.monthly ?? []).map((m) => ({ key: `${m.label_year}-${m.label_month}`, label: monthName(m.label_month).slice(0, 3), name: `${monthName(m.label_month)} ${m.label_year}`, total: m.total }));
  const chartAlt = chart.map((m) => `${m.name}: ${formatILS(m.total)}`).join(", ");

  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">חיפוש הוצאות</h1>
      <div className="flex flex-col gap-3">
        <div className="relative">
          <Search size={18} className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-muted" />
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="על מה? למשל: וולט, דלק, חוג" className="input pr-10" aria-label="חיפוש בית עסק או תיאור" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="min-w-40 flex-1">
            <CategorySelect value={categoryId} onChange={setCategoryId} />
          </div>
          {categoryId != null && (
            <button className="btn-ghost" onClick={() => setCategoryId(null)}>
              כל הקטגוריות
            </button>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1.5 text-[13px] text-muted">
            מתאריך
            <input type="date" dir="ltr" className="input" value={from} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] text-muted">
            עד תאריך
            <input type="date" dir="ltr" className="input" value={to} onChange={(e) => setTo(e.target.value)} />
          </label>
        </div>
      </div>

      <Status loading={!data && !error} error={error} />
      {data && (
        <>
          <Card>
            <p className="text-sm text-muted">{filtered ? "סך הכול יצא על זה" : "סך כל ההוצאות בתקופה"}</p>
            <Amount value={data.total} plain className="text-[40px] leading-tight font-extrabold" />
            <p className="text-sm text-muted">
              בממוצע <Amount value={Math.round(data.avg_per_month)} plain className="font-semibold text-text" /> בחודש · {txnCount(data.count)}
            </p>
            {data.count > 0 && (
              <Link href={`/transactions?${txParams}`} className="text-sm text-brand underline">
                לכל העסקאות
              </Link>
            )}
          </Card>

          {chart.length > 1 && (
            <Card title="לפי חודש">
              <div dir="ltr" className="h-44" role="img" aria-label={chartAlt} title={chartAlt}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chart} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                    <XAxis dataKey="label" tickLine={false} axisLine={false} reversed interval={0} tick={{ fontSize: 11, fill: "var(--muted)" }} />
                    <Tooltip cursor={CURSOR} contentStyle={TOOLTIP_STYLE} formatter={(v) => formatILS(Number(v))} labelFormatter={(_, p) => p?.[0]?.payload?.name ?? ""} />
                    <Bar dataKey="total" fill="var(--brand)" radius={[6, 6, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          )}

          {data.top_merchants.length > 0 && (
            <Card title="איפה הכי הרבה">
              <ul className="flex flex-col gap-2 text-sm">
                {data.top_merchants.map((m) => (
                  <li key={m.merchant_key} className="flex items-baseline gap-2">
                    <span className="flex-1 truncate">{m.sample}</span>
                    <span className="text-xs text-muted">{txnCount(m.count)}</span>
                    <Amount value={m.total} plain className="font-semibold" />
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

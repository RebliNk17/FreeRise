"use client";

import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CURSOR, TOOLTIP_STYLE } from "@/components/chart";
import { Amount } from "@/components/Amount";
import { Card, Status } from "@/components/Card";
import type { CategoryChange, Progress } from "@/lib/api";
import { categoryLabel, formatDate, formatILS, monthName } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { HistoryChart } from "./HistoryChart";

export default function ProgressPage() {
  const { data, error } = useApi<Progress>("/progress");
  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">המגמות שלי</h1>
      <Status loading={!data} error={error} empty={data && data.cycles.length === 0} />
      {data && data.cycles.length > 0 && <ProgressView p={data} />}
      {data && data.cycles.length > 0 && <HistoryChart />}
    </div>
  );
}

function ProgressView({ p }: { p: Progress }) {
  const n = p.cycles.length;
  const bars = p.cycles.map((c) => ({ key: c.cycle.start, label: monthName(c.cycle.label_month).slice(0, 3), full: monthName(c.cycle.label_month), net: c.net }));
  const alt = bars.map((b) => `${b.full}: ${formatILS(b.net)}`).join(", ");

  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        <Stat label="ממוצע לחודש (נכנס פחות יצא)">
          <Amount value={p.avg_net} className={p.avg_net < 0 ? "text-danger" : ""} />
        </Stat>
        <Stat label="חודשים שנגמרו בפלוס">
          <span>
            {p.positive_cycles} מתוך {n}
          </span>
        </Stat>
        <Stat label="הפקדות לחיסכון בממוצע">
          <Amount value={p.savings_avg} plain />
          <span className="text-xs text-muted">
            סה״כ <Amount value={p.savings_total} plain />
          </span>
        </Stat>
        <Stat label={p.since ? `מצטבר מאז ${formatDate(p.since)}` : "מצטבר"}>
          <Amount value={p.cumulative_net} className={p.cumulative_net < 0 ? "text-danger" : ""} />
        </Stat>
      </div>

      <Card title={`איך נגמרו ${n} החודשים האחרונים`}>
        <div dir="ltr" className="h-40" role="img" aria-label={alt} title={alt}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={bars} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <XAxis dataKey="label" tickLine={false} axisLine={false} reversed tick={{ fontSize: 12, fill: "var(--muted)" }} />
              <YAxis hide domain={[(min: number) => Math.min(0, min), (max: number) => Math.max(0, max)]} />
              <ReferenceLine y={0} stroke="var(--hairline)" />
              <Tooltip cursor={CURSOR} contentStyle={TOOLTIP_STYLE} formatter={(v) => formatILS(Number(v))} labelFormatter={(_, items) => items?.[0]?.payload?.full ?? ""} />
              <Bar dataKey="net" radius={[6, 6, 6, 6]} isAnimationActive={false}>
                {bars.map((b) => (
                  <Cell key={b.key} fill={b.net >= 0 ? "var(--positive)" : "var(--danger)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {p.increases.length + p.decreases.length > 0 && (
        <Card title="מה השתנה בהוצאות">
          <p className="text-xs text-muted">ממוצע חודשי ב-3 החודשים האחרונים לעומת 3 החודשים שלפניהם</p>
          <ul className="flex flex-col gap-2 text-sm">
            {p.increases.map((c) => (
              <ChangeRow key={`u${c.category_id}`} c={c} />
            ))}
            {p.decreases.map((c) => (
              <ChangeRow key={`d${c.category_id}`} c={c} />
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="card flex flex-col gap-1 p-4">
      <span className="text-xs text-muted">{label}</span>
      <span className="flex flex-col text-xl font-bold">{children}</span>
    </section>
  );
}

function ChangeRow({ c }: { c: CategoryChange }) {
  const up = c.change_pct > 0;
  return (
    <li className="flex items-baseline gap-2">
      <span className={up ? "text-danger" : "text-positive"} aria-label={up ? "עלייה" : "ירידה"}>
        {up ? "▲" : "▼"}
      </span>
      <span className="flex-1 truncate">{categoryLabel(c.name)}</span>
      <span className="text-xs text-muted">
        <Amount value={c.previous} plain /> ← <Amount value={c.current} plain />
      </span>
      <span dir="ltr" className={`w-14 text-end font-semibold tabular-nums ${up ? "text-danger" : "text-positive"}`}>
        {up ? "+" : ""}
        {Math.round(c.change_pct * 100)}%
      </span>
    </li>
  );
}

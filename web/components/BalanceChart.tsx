"use client";

import { useId } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartTooltip } from "@/components/charts/ChartTooltip";
import { formatDate, formatILS } from "@/lib/format";

type Point = { date: string; balance: number };
const Tip = chartTooltip<Point>((d) => ({ title: formatDate(d.date), rows: [{ label: "יתרה", value: d.balance }] }));

/** Fund balance over time: brand line over a soft gradient, themed tooltip. Dates run left to right (time axis). */
export function BalanceChart({ data }: { data: Point[] }) {
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  if (data.length < 2) return null;
  const last = data[data.length - 1];
  return (
    <div dir="ltr" className="h-44" role="img" aria-label={`יתרה מ־${formatDate(data[0].date)} (${formatILS(data[0].balance)}) עד ${formatDate(last.date)} (${formatILS(last.balance)})`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.28} />
              <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" tickFormatter={(d: string) => formatDate(d).slice(3)} tickLine={false} axisLine={false} minTickGap={24} tick={{ fontSize: 11, fill: "var(--muted)" }} />
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Tooltip content={<Tip />} cursor={{ stroke: "var(--border)" }} isAnimationActive={false} />
          <Area type="monotone" dataKey="balance" stroke="var(--brand)" strokeWidth={2.5} fill={`url(#${id})`} dot={false} activeDot={{ r: 5, fill: "var(--brand)", stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

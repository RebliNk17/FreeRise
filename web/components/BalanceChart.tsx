"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { TOOLTIP_STYLE } from "@/components/chart";
import { formatDate, formatILS } from "@/lib/format";

export function BalanceChart({ data }: { data: { date: string; balance: number }[] }) {
  if (data.length < 2) return null;
  return (
    <div dir="ltr" className="h-44">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <XAxis dataKey="date" tickFormatter={(d: string) => formatDate(d).slice(3)} tickLine={false} axisLine={false} minTickGap={24} tick={{ fontSize: 11, fill: "var(--muted)" }} />
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => formatILS(Number(v))} labelFormatter={(d) => formatDate(String(d))} />
          <Line type="monotone" dataKey="balance" stroke="var(--brand)" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

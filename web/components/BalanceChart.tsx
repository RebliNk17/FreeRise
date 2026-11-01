"use client";

import { useId } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Amount } from "@/components/Amount";
import { chartTooltip } from "@/components/charts/ChartTooltip";
import { formatDate, formatILS } from "@/lib/format";

/** `label` names the value in the tooltip ("יתרה" by default; e.g. "רווח מצטבר"). `gain`: how much of
 * `balance` is gains, which splits it into deposited (dashed line) and gained (the band above it). */
type Point = { date: string; balance: number; label?: string; gain?: number };
const cents = (x: number) => Math.round(x * 100) / 100;
const Tip = chartTooltip<Point>((d) => ({
  title: formatDate(d.date),
  rows:
    d.gain == null
      ? [{ label: d.label ?? "יתרה", value: d.balance }]
      : [
          { label: "סה״כ", value: d.balance },
          { label: "הופקד", value: cents(d.balance - d.gain) },
          { label: "רווח", value: d.gain, tone: d.gain < 0 ? "danger" : "positive" },
        ],
}));

/** Fund balance over time: brand line over a soft gradient, themed tooltip. Dates run left to right (time axis). */
export function BalanceChart({ data }: { data: Point[] }) {
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  if (data.length < 2) return null;
  const last = data[data.length - 1];
  const gain = last.gain;
  const rows = gain != null ? data.map((d) => ({ ...d, deposited: cents(d.balance - (d.gain ?? 0)) })) : data;
  return (
    <div>
      <div dir="ltr" className="h-44" role="img" aria-label={`${data[0].label ?? "יתרה"} מ־${formatDate(data[0].date)} (${formatILS(data[0].balance)}) עד ${formatDate(last.date)} (${formatILS(last.balance)})`}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={rows} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
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
            {gain != null && (
              <Area type="monotone" dataKey="deposited" stroke="var(--muted)" strokeWidth={2} strokeDasharray="5 4" fill="var(--muted)" fillOpacity={0.1} dot={false} activeDot={{ r: 4, fill: "var(--muted)", stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
      {gain != null && (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="h-0.5 w-3 rounded bg-brand" />
            סה״כ <Amount value={last.balance} plain className="font-bold text-text" />
          </li>
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="w-3 border-t-2 border-dashed border-muted" />
            הופקד <Amount value={cents(last.balance - gain)} plain className="font-bold text-text" />
          </li>
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="h-2 w-3 rounded-sm bg-brand/25" />
            רווח <Amount value={gain} className={`font-bold ${gain < 0 ? "text-danger" : ""}`} />
          </li>
        </ul>
      )}
    </div>
  );
}

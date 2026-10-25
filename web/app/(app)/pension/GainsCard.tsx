"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Amount } from "@/components/Amount";
import { Card } from "@/components/Card";
import { MonthBars } from "@/components/charts/MonthBars";
import type { Fund, MonthGain } from "@/lib/api";
import { formatPct, monthName } from "@/lib/format";
import { periodLabel, periodOf, periodsWithData, samePeriod, summarize, type Period, type Unit } from "@/lib/pension";

const UNITS: { key: Unit; label: string }[] = [
  { key: "m", label: "חודש" },
  { key: "q", label: "רבעון" },
  { key: "y", label: "שנה" },
];
const NAV =
  "flex size-10 shrink-0 items-center justify-center rounded-full border border-border bg-surface hover:bg-sunken disabled:border-hairline disabled:text-disabled disabled:hover:bg-surface";
const cents = (x: number) => Math.round(x * 100) / 100;

/** Signed exact amount: "+₪22,307.62" / "−₪1,496". */
export function Signed({ value, className = "" }: { value: number; className?: string }) {
  return (
    <span className={`${value >= 0 ? "text-positive" : "text-danger"} ${className}`}>
      <span dir="ltr">{value >= 0 ? "+" : "−"}</span>
      <Amount value={Math.abs(value)} plain />
    </span>
  );
}

/** The portal's own yearly report summed over the funds that have `year` (fees and insurance live only here). */
function yearReport(funds: Fund[], year: number) {
  const rows = funds.flatMap((f) => f.yearly_movements.filter((y) => Number(y.year) === year));
  if (!rows.length) return null;
  const sum = (k: "opening_balance" | "deposits" | "gains" | "management_fees" | "insurance_costs" | "closing_balance") =>
    cents(rows.reduce((s, r) => s + (r[k] ?? 0), 0));
  return {
    opening: sum("opening_balance"),
    deposits: sum("deposits"),
    gains: sum("gains"),
    fees: sum("management_fees"),
    insurance: sum("insurance_costs"),
    closing: sum("closing_balance"),
  };
}

const fundLabel = (f: Fund) => (f.product_type === "pension" ? f.name : `${f.name} · ${f.track ?? f.company ?? ""}`);

export function GainsCard({ funds, gains }: { funds: Fund[]; gains: MonthGain[] }) {
  const reportYears = [...new Set(funds.flatMap((f) => f.yearly_movements.map((y) => Number(y.year))))];
  const periodsFor = (u: Unit): Period[] => {
    const ps = periodsWithData(gains, u);
    if (u !== "y") return ps;
    const years = [...new Set([...ps.map((p) => p.year), ...reportYears])].sort();
    return years.map((year) => ({ unit: "y", year, n: 0 }));
  };
  const [unit, setUnit] = useState<Unit>(() => (gains.length ? "m" : "y"));
  const periods = periodsFor(unit);
  const [picked, setPicked] = useState<Period | null>(null);
  const i = picked ? periods.findIndex((p) => samePeriod(p, picked)) : -1;
  const at = i >= 0 ? i : periods.length - 1;
  const p = periods[at];

  if (!p)
    return (
      <Card title="רווחים">
        <p className="text-sm text-muted">רווח לפי חודש יופיע אחרי שיהיו יתרות של שני חודשים רצופים. מגדל והפניקס מתעדכנים מעכשיו כל יום.</p>
      </Card>
    );

  const s = summarize(gains, p);
  const report = p.unit === "y" ? yearReport(funds, p.year) : null;
  const gain = report && !s.months.length ? report.gains : s.gain;
  const deposits = report && !s.months.length ? report.deposits : s.deposits;
  const start = report && !s.months.length ? report.opening : s.start;
  const end = report && !s.months.length ? report.closing : s.end;
  // One fund, or a group its provider reports only as a sum (Phoenix): "4 קרנות השתלמות · הפניקס, יחד".
  const series = [...s.bySeries].map(([key, value]) => {
    const fs = key
      .split(",")
      .map((id) => funds.find((f) => f.id === Number(id)))
      .filter((f): f is Fund => !!f);
    const f = fs[0];
    const group = fs.length > 1;
    return {
      key,
      value,
      short: group ? (f?.company ?? "יחד") : f?.product_type === "pension" ? f.name.replace("פנסיה ", "") : (f?.track ?? f?.company ?? f?.name ?? ""),
      label: group ? `${fs.length} קרנות ${f?.company ?? ""}, יחד` : f ? fundLabel(f) : key,
    };
  });
  const lastMonth = gains.reduce((m, g) => (g.month > m ? g.month : m), "");
  const partial = p.unit !== "m" && !!lastMonth && samePeriod(periodOf(lastMonth, p.unit), p) && !report;

  function switchUnit(u: Unit) {
    // Stay at the same point in time: the newest month of the current period.
    const anchor = s.months.at(-1)?.month ?? (p.unit === "y" ? `${p.year}-12-01` : null);
    const next = periodsFor(u);
    setUnit(u);
    setPicked(anchor ? (next.find((q) => samePeriod(q, periodOf(anchor, u))) ?? null) : null);
  }

  const bars =
    p.unit === "m"
      ? series.map(({ key, short, label, value }) => ({ key, label: short, full: label, value }))
      : s.months.map((m) => {
          const n = Number(m.month.slice(5, 7));
          return {
            key: m.month,
            label: monthName(n).slice(0, 3),
            full: `${monthName(n)} ${m.month.slice(0, 4)}`,
            value: m.gain,
          };
        });

  return (
    <Card title="רווחים" className="rise">
      <div role="group" aria-label="תקופה" className="grid grid-cols-3 gap-1 rounded-2xl bg-sunken p-1">
        {UNITS.map((u) => (
          <button
            key={u.key}
            type="button"
            aria-pressed={unit === u.key}
            className={`min-h-10 rounded-xl text-sm font-bold ${unit === u.key ? "bg-surface text-text shadow-card" : "text-muted"}`}
            onClick={() => switchUnit(u.key)}
          >
            {u.label}
          </button>
        ))}
      </div>
      <div className="flex items-center justify-between gap-3">
        <button type="button" className={NAV} aria-label="התקופה הקודמת" disabled={at === 0} onClick={() => setPicked(periods[at - 1])}>
          <ChevronRight size={18} />
        </button>
        <div className="text-center">
          <h3 className="section-title">
            {periodLabel(p)}
            {partial && <span className="text-sm font-normal text-muted"> (עד כה)</span>}
          </h3>
          {report && <p className="text-xs text-muted">לפי הדוח השנתי של הקרנות</p>}
        </div>
        <button type="button" className={NAV} aria-label="התקופה הבאה" disabled={at === periods.length - 1} onClick={() => setPicked(periods[at + 1])}>
          <ChevronLeft size={18} />
        </button>
      </div>
      <div key={`${p.unit}${p.year}${p.n}`} className="rise text-center">
        <Signed value={gain} className="font-display text-[34px] leading-tight font-extrabold" />
        <p className="text-sm text-muted">
          {start > 0 && <span dir="ltr">{formatPct(gain / start)}</span>}
          {start > 0 && " · "}הפקדות <Amount value={deposits} plain />
        </p>
        {start > 0 && (
          <p className="text-xs text-faint">
            יתרה <Amount value={start} plain /> ← <Amount value={end} plain />
          </p>
        )}
      </div>
      {bars.length > 1 && <MonthBars key={`bars-${p.unit}${p.year}${p.n}`} data={bars} kind="net" valueLabel="רווח" ariaLabel={`רווח ב${periodLabel(p)}`} />}
      {report && (report.fees > 0 || report.insurance > 0) && (
        <div className="flex flex-col gap-1.5 border-t border-hairline pt-3 text-sm">
          <p className="text-xs text-muted">לאן הלך הכסף</p>
          {(
            [
              ["יתרת פתיחה", report.opening, "b"],
              ["הפקדות", report.deposits, "var(--info)"],
              ["רווח מהשקעות", cents(report.gains + report.fees + report.insurance), "var(--positive)"],
              ["דמי ניהול", -report.fees, "var(--sun)"],
              ["ביטוח", -report.insurance, "var(--sun)"],
              ["יתרת סגירה", report.closing, "b"],
            ] as const
          ).map(([label, v, color]) =>
            color === "b" ? (
              <div key={label} className="flex justify-between font-bold">
                <span>{label}</span>
                <Amount value={v} plain />
              </div>
            ) : (
              <div key={label} className="flex items-center gap-3">
                <span className="w-24 shrink-0">{label}</span>
                <span className="h-2 flex-1 overflow-hidden rounded-full bg-sunken">
                  <span
                    className="grow-x block h-full rounded-full"
                    style={{
                      width: `${Math.min(100, (Math.abs(v) / Math.max(report.deposits, Math.abs(report.gains) + report.fees + report.insurance, 1)) * 100)}%`,
                      background: color,
                    }}
                  />
                </span>
                <Signed value={v} className="w-28 shrink-0 text-end" />
              </div>
            ),
          )}
        </div>
      )}
      {series.length > 0 && (
        <details className="border-t border-hairline pt-2">
          <summary className="cursor-pointer py-1 text-sm font-bold">רווח לפי קופה</summary>
          <ul className="flex flex-col">
            {series.map((x) => (
              <li key={x.key} className="flex justify-between gap-3 border-t border-hairline py-2 text-sm">
                <span className="truncate">{x.label}</span>
                <Signed value={x.value} className="font-bold" />
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

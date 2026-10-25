import type { MonthGain } from "@/lib/api";
import { monthName } from "@/lib/format";

export type { MonthGain };
export type Unit = "m" | "q" | "y";
/** n: month 1–12, quarter 1–4, or 0 for a year. */
export type Period = { unit: Unit; year: number; n: number };

const cents = (x: number) => Math.round(x * 100) / 100;

export function periodOf(month: string, unit: Unit): Period {
  const [y, m] = month.split("-").map(Number);
  return {
    unit,
    year: y,
    n: unit === "m" ? m : unit === "q" ? Math.ceil(m / 3) : 0,
  };
}

const key = (p: Period) => `${p.year}-${String(p.n).padStart(2, "0")}`;
export const samePeriod = (a: Period, b: Period) => a.unit === b.unit && key(a) === key(b);

/** Periods that have any gains, oldest first. */
export function periodsWithData(gains: MonthGain[], unit: Unit): Period[] {
  const seen = new Map<string, Period>();
  for (const g of gains) {
    const p = periodOf(g.month, unit);
    seen.set(key(p), p);
  }
  return [...seen].sort(([a], [b]) => a.localeCompare(b)).map(([, p]) => p);
}

export function periodLabel(p: Period): string {
  return p.unit === "y" ? `${p.year}` : p.unit === "q" ? `רבעון ${p.n} · ${p.year}` : `${monthName(p.n)} ${p.year}`;
}

export const seriesKey = (g: MonthGain) => g.fund_ids.join(",");

export type PeriodSummary = {
  gain: number;
  deposits: number;
  start: number; // each fund's balance before its first month in the period
  end: number; // each fund's balance at its last month in the period
  months: { month: string; gain: number }[]; // oldest first
  /** Gain per series: one fund ("7"), or a group reported as a whole ("1,2,3,4"). */
  bySeries: Map<string, number>;
};

export function summarize(gains: MonthGain[], p: Period): PeriodSummary {
  const rows = gains.filter((g) => samePeriod(periodOf(g.month, p.unit), p)).sort((a, b) => a.month.localeCompare(b.month));
  const first = new Map<string, MonthGain>();
  const last = new Map<string, MonthGain>();
  const byMonth = new Map<string, number>();
  const bySeries = new Map<string, number>();
  for (const g of rows) {
    const k = seriesKey(g);
    if (!first.has(k)) first.set(k, g);
    last.set(k, g);
    byMonth.set(g.month, (byMonth.get(g.month) ?? 0) + g.gain);
    bySeries.set(k, cents((bySeries.get(k) ?? 0) + g.gain));
  }
  const sum = (xs: number[]) => cents(xs.reduce((s, x) => s + x, 0));
  return {
    gain: sum(rows.map((g) => g.gain)),
    deposits: sum(rows.map((g) => g.deposits)),
    start: sum([...first.values()].map((g) => g.start_balance)),
    end: sum([...last.values()].map((g) => g.end_balance)),
    months: [...byMonth].map(([month, gain]) => ({ month, gain: cents(gain) })),
    bySeries,
  };
}

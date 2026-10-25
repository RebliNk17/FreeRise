import { expect, test } from "bun:test";
import { periodLabel, periodsWithData, summarize, type MonthGain } from "./pension";

const g = (fund: number, month: string, start_balance: number, end_balance: number, deposits: number): MonthGain => ({
  fund_ids: [fund],
  month,
  start_balance,
  end_balance,
  deposits,
  gain: Math.round((end_balance - start_balance - deposits) * 100) / 100,
});

const gains = [
  g(1, "2026-07-01", 1000, 1100.1, 50),
  g(1, "2026-08-01", 1100.1, 1150.3, 50),
  g(2, "2026-08-01", 500, 490.25, 0),
  g(1, "2026-10-01", 1150.3, 1300, 50),
];

test("quarter sums months and funds exactly", () => {
  const s = summarize(gains, { unit: "q", year: 2026, n: 3 });
  expect(s.gain).toBe(40.55); // 50.1 + 0.2 − 9.75
  expect(s.deposits).toBe(100);
  expect([s.start, s.end]).toEqual([1500, 1640.55]);
  expect(s.months).toEqual([
    { month: "2026-07-01", gain: 50.1 },
    { month: "2026-08-01", gain: -9.55 },
  ]);
  expect(s.bySeries.get("2")).toBe(-9.75);
});

test("periods with data, oldest first, and labels", () => {
  expect(periodsWithData(gains, "q").map(periodLabel)).toEqual(["רבעון 3 · 2026", "רבעון 4 · 2026"]);
  expect(periodsWithData(gains, "m").map(periodLabel)).toEqual(["יולי 2026", "אוגוסט 2026", "אוקטובר 2026"]);
  expect(periodsWithData(gains, "y").map(periodLabel)).toEqual(["2026"]);
});

test("a group is one series", () => {
  const grouped = [{ ...g(1, "2026-08-01", 1000, 1100, 50), fund_ids: [3, 4] }];
  const s = summarize(grouped, { unit: "m", year: 2026, n: 8 });
  expect([...s.bySeries]).toEqual([["3,4", 50]]);
});

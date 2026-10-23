import { expect, test } from "bun:test";
import { planTotals, toLines, WEEKS_PER_MONTH } from "./planner";

test("toLines flattens groups with stable keys", () => {
  const lines = toLines({ months: 6, income: [{ label: "משכורת", amount: 10000 }], fixed: [{ label: "משכנתא", amount: 3000 }], savings: [], variable: [{ label: "כלכלה", amount: 2000 }], goal: 500 });
  expect(lines.map((l) => [l.key, l.group, l.amount])).toEqual([
    ["income0", "income", "10000"],
    ["fixed0", "fixed", "3000"],
    ["variable0", "variable", "2000"],
  ]);
});

test("planTotals: month end and weekly allowance", () => {
  const lines = [
    { key: "a", group: "income" as const, label: "", amount: "10000" },
    { key: "b", group: "fixed" as const, label: "", amount: "3000" },
    { key: "c", group: "savings" as const, label: "", amount: "1000" },
    { key: "d", group: "variable" as const, label: "", amount: "4000" },
    { key: "e", group: "variable" as const, label: "", amount: "oops" },
  ];
  const t = planTotals(lines, 1000);
  expect(t.month_end).toBe(2000);
  expect(t.weekly_allowance).toBeCloseTo(5000 / WEEKS_PER_MONTH);
});

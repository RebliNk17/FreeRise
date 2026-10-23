// Typical-month planner (whatif): a representative month the user edits; nothing is saved.

export type PlanGroup = "income" | "fixed" | "savings" | "variable";
export type PlanLine = { key: string; group: PlanGroup; label: string; amount: string };
export type TypicalMonth = { months: number; income: Line[]; fixed: Line[]; savings: Line[]; variable: Line[]; goal: number };
type Line = { label: string; amount: number };

export const WEEKS_PER_MONTH = 30.44 / 7;
export const PLAN_GROUPS: PlanGroup[] = ["income", "fixed", "savings", "variable"];

/** API month → editable lines (keys stable per group + index). */
export const toLines = (t: TypicalMonth): PlanLine[] => PLAN_GROUPS.flatMap((g) => t[g].map((l, i) => ({ key: `${g}${i}`, group: g, label: l.label, amount: String(l.amount) })));

/** Totals; month_end = income − fixed − savings − variable;
 * weekly_allowance = what's left for variable spending after fixed, savings and the goal, per week. */
export function planTotals(lines: PlanLine[], goal: number) {
  const sum = (g: PlanGroup) => lines.filter((l) => l.group === g).reduce((s, l) => s + (Number(l.amount) || 0), 0);
  const income = sum("income");
  const fixed = sum("fixed");
  const savings = sum("savings");
  const variable = sum("variable");
  return {
    income,
    fixed,
    savings,
    variable,
    month_end: income - fixed - savings - variable,
    weekly_allowance: (income - fixed - savings - goal) / WEEKS_PER_MONTH,
  };
}

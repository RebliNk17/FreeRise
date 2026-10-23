// "חודשים קודמים" (GET /home/history) and /progress history charts (GET /progress/history).
import { withHidden } from "./viewFilter";

export type HistoryKind = "variable" | "fixed" | "savings" | "income" | "category";
export type HomeHistory = { cycles: { label_year: number; label_month: number; spent: number; expected: number }[]; avg_spent: number; avg_expected: number; basis: string };
export type ProgressHistory = { cycles: { label_year: number; label_month: number; total: number }[]; average: number; categories: { category_id: number; name: string }[] };

/** The 6 cycles before the viewed one, for one card. */
export function historyPath(kind: HistoryKind, cycle: { label_year: number; label_month: number }, hidden: number[], categoryId?: number) {
  const p = new URLSearchParams({ kind, year: String(cycle.label_year), month: String(cycle.label_month) });
  if (categoryId != null) p.set("category_id", String(categoryId));
  return withHidden(`/home/history?${p}`, hidden);
}

export function progressHistoryPath(group: "income" | "fixed" | "variable", months: number, categoryId: number | null) {
  const p = new URLSearchParams({ group, months: String(months) });
  if (categoryId != null) p.set("category_id", String(categoryId));
  return `/progress/history?${p}`;
}

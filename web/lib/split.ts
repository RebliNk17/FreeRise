// Splitting one transaction into category parts (amounts entered as positive numbers).

export type SplitRow = { category_id: number | null; amount: string };

const cents = (n: number) => Math.round(n * 100);

/** What's still to assign: |total| − sum of the rows (in shekels, cent-exact). */
export const splitLeft = (total: number, rows: SplitRow[]) => (cents(Math.abs(total)) - rows.reduce((s, r) => s + cents(Number(r.amount) || 0), 0)) / 100;

/** Why the split can't be saved yet, or null when it can. */
export function splitProblem(total: number, rows: SplitRow[]): string | null {
  if (rows.length < 2) return "צריך לפחות שני חלקים";
  if (rows.some((r) => r.category_id == null)) return "לכל חלק צריך קטגוריה";
  if (new Set(rows.map((r) => r.category_id)).size !== rows.length) return "כל קטגוריה פעם אחת";
  if (rows.some((r) => !(Number(r.amount) > 0))) return "לכל חלק צריך סכום חיובי";
  if (splitLeft(total, rows) !== 0) return "סכומי החלקים צריכים להסתכם בסכום העסקה";
  return null;
}

/** API body: parts carry the transaction's sign. */
export const splitBody = (total: number, rows: SplitRow[]) => ({
  parts: rows.map((r) => ({ category_id: r.category_id!, amount: (Math.sign(total) * cents(Number(r.amount))) / 100 })),
});

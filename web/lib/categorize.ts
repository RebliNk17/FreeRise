// Merchant-at-a-time categorizing (home "N עסקאות לסיווג" sheet).
import type { Category, Group, Uncategorized } from "./api";
import { formatDate, txnCount } from "./format";

/** Transactions behind the uncategorized merchants. */
export const pendingCount = (list: Pick<Uncategorized, "count">[]) => list.reduce((n, u) => n + u.count, 0);

const merchants = (n: number) => (n === 1 ? "בית עסק אחד" : `${n} בתי עסק`);

/** Home chip: "111 עסקאות לסיווג · 64 בתי עסק" — both from the same /categories/uncategorized list
 * the sheet walks (one merchant at a time, each choice categorizes all its transactions). */
export function pendingLabel(list: Pick<Uncategorized, "count">[]) {
  const n = pendingCount(list);
  return `${n === 1 ? "עסקה אחת" : `${n} עסקאות`} לסיווג · ${merchants(list.length)}`;
}

/** Sheet header: "בית עסק 3 מתוך 64". */
export const merchantProgress = (i: number, total: number) => `בית עסק ${i + 1} מתוך ${total}`;

/** Sheet: "נשארו 111 עסקאות", dropping as merchants are categorized. */
export const txnsLeft = (n: number) => (n === 1 ? "נשארה עסקה אחת" : `נשארו ${n} עסקאות`);

/** Groups a merchant may be sorted into from the quick buttons (spending first; credits also income). */
export const quickGroups = (total: number): Group[] => (total > 0 ? ["income", "variable", "fixed", "savings"] : ["variable", "fixed", "savings"]);

/** The sheet's quick buttons: a likely fixed charge (monthly / installments) gets fixed categories
 * (דיגיטל, עמלות, תקשורת…) first, then the usual picks. */
export function merchantPicks(cats: Category[], usage: number[], total: number, fixed: boolean, n = 6): Category[] {
  if (!fixed || total > 0) return quickPicks(cats, usage, quickGroups(total), n);
  const first = quickPicks(cats, usage, ["fixed"], n - 2);
  return [...first, ...quickPicks(cats, usage, ["variable", "savings"], n - first.length)];
}

// LTR isolates keep "₪89" and date ranges in order inside Hebrew text
export const ltr = (s: string) => `\u2066${s}\u2069`;
const ils = (n: number) => ltr(`₪${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 2 })}`); // exact: money is never rounded
const mmyy = (iso: string) => `${iso.slice(5, 7)}.${iso.slice(2, 4)}`;

/** The merchant's pattern on the categorize card, and whether it looks like a fixed expense:
 * "חיוב חודשי · ₪89 · 12 חודשים (מ-11.25)", "תשלום 4/6 · ₪233 לחודש", else "N עסקאות · ₪total · dd.mm.yy–dd.mm.yy". */
export function merchantSummary(u: Pick<Uncategorized, "count" | "total" | "first_date" | "sample_date" | "monthly" | "installment">): { text: string; fixed: boolean } {
  if (u.installment) return { text: `תשלום ${u.installment.number ?? "?"}/${u.installment.total} · ${ils(u.installment.amount)} לחודש`, fixed: true };
  if (u.monthly) return { text: `חיוב חודשי · ${ils(u.monthly.amount)} · ${u.monthly.months} חודשים (מ-${ltr(mmyy(u.monthly.since))})`, fixed: true };
  const range = ltr(u.first_date === u.sample_date ? formatDate(u.sample_date) : `${formatDate(u.first_date)}–${formatDate(u.sample_date)}`);
  return { text: `${txnCount(u.count)} · ${ils(u.total)} · ${range}`, fixed: false };
}

/** Up to `n` quick-pick categories: most used first (usage = ids by use), then by sort order; only `groups`. */
export function quickPicks(cats: Category[], usage: number[], groups: Group[], n = 6): Category[] {
  const rank = new Map(usage.map((id, i) => [id, i]));
  return cats
    .filter((c) => groups.includes(c.group))
    .sort((a, b) => (rank.get(a.id) ?? Infinity) - (rank.get(b.id) ?? Infinity) || a.sort_order - b.sort_order || a.id - b.id)
    .slice(0, n);
}

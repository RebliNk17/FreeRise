// Home screen (GET /api/home/...)
import type { CycleShift, Group } from "./api";

export type Txn = {
  id: number;
  date: string;
  amount: number; // signed
  description: string;
  merchant_key: string | null;
  category_id: number | null;
  category_name: string | null;
  group: Group | null;
  account_id: number;
  account_label: string;
  note: string | null;
  installment_number: number | null;
  installment_total: number | null;
  status: string;
  account_holder: string;
  cycle_shift: CycleShift | null;
  cycle_label: string | null; // e.g. "ספטמבר 2026"
  fixed_income_id: number | null; // confirmed income item of this merchant
  cycle_date_source: "auto" | "manual" | null;
  split_total: number | null; // split txn: the whole amount (amount/category are this part's)
  split: { category_id: number; category_name: string; amount: number }[] | null;
  review: { assignee: string | null; note: string | null } | null; // flagged "לבדוק עם…"
};

/** List key: a split txn appears once per part. */
export const txnKey = (t: Pick<Txn, "id" | "category_id">) => `${t.id}:${t.category_id ?? ""}`;

/** "ישראכרט ••5678 (שי)" — the holder only when the household has more than one. */
export const accountWithHolder = (t: Pick<Txn, "account_label" | "account_holder">, multi: boolean) => (multi && t.account_holder ? `${t.account_label} (${t.account_holder})` : t.account_label);

/** "שויך לספטמבר" for a txn counted in a neighbour cycle, else null. */
export const shiftChip = (t: Pick<Txn, "cycle_shift" | "cycle_label">) => (t.cycle_shift && t.cycle_label ? `שויך ל${t.cycle_label.split(" ")[0]}` : null);

export type Week = {
  index: number;
  start: string;
  end: string;
  spent: number;
  left: number;
  expected: number | null;
  is_current: boolean;
  is_past: boolean;
  transactions: Txn[];
};

export type TrackedCategory = {
  category_id: number;
  name: string;
  spent: number;
  expected: number;
  expected_overridden: boolean;
  left: number;
  mode: "weekly" | "monthly";
  weeks: Week[] | null;
  transactions: Txn[];
  history: { label_year: number; label_month: number; spent: number }[];
  pinned?: boolean; // a default starter category: always shown, even with no activity
};

export type FixedItem = {
  label: string;
  account_label: string | null;
  expected_date: string | null;
  expected_amount: number;
  actual_amount: number;
  status: "charged" | "expected" | "overdue";
  transactions: Txn[];
  recurring_id: number | null;
  installment_number?: number | null; // an installment payment: n of N
  installment_total?: number | null;
};

/** "תשלום 3/6" for an installment item, else null. */
export const installmentLabel = (it: Pick<FixedItem, "installment_number" | "installment_total">) => (it.installment_total && it.installment_total > 1 ? `תשלום ${it.installment_number ?? "?"}/${it.installment_total}` : null);

export type FixedGroup = { category_id: number | null; name: string; spent: number; expected: number; items: FixedItem[] };

export type HomeData = {
  cycle: { start: string; end: string; label_year: number; label_month: number; is_current: boolean; prev: { year: number; month: number }; next: { year: number; month: number } | null };
  summary: { week_left: number; next_week_allowance: number | null; goal: number; goal_personal: number; goal_plans: number; variable_allowance: number } | null;
  variable: { spent: number; allowance: number; weeks: Week[] };
  tracked: TrackedCategory[];
  untracked_available: { category_id: number; name: string }[];
  savings: { spent: number; expected: number; transactions: Txn[] };
  fixed: { spent: number; expected: number; groups: FixedGroup[] };
  total: { spent: number; expected: number };
  income: { received: number; expected: number; fixed_groups: FixedGroup[]; variable: { received: number; transactions: Txn[] } };
  multi_holder: boolean; // accounts belong to more than one person
  moved_next: { transactions: Txn[] }; // current cycle: happened here, attributed to the not-yet-open next cycle
  fees: FixedGroup | null; // the עמלות category: its own card, not part of fixed
};

/** 1819.2 → {sign: "", int: "1,819", dec: ".2"}; at most 2 decimals, trailing zeros dropped. */
export function splitMoney(n: number) {
  const s = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(Math.abs(n));
  const [int, dec] = s.split(".");
  const sign = n < 0 && s !== "0" ? "-" : "";
  return { sign, int, dec: dec ? `.${dec}` : "" };
}

export type WeekStatus = "past" | "current" | "future";
export const weekStatus = (w: Pick<Week, "is_current" | "is_past">): WeekStatus => (w.is_current ? "current" : w.is_past ? "past" : "future");

/** Overspent week: left below 0, or spent above its expected allowance. */
export const weekOver = (w: Pick<Week, "spent" | "left" | "expected">) => w.left < -0.005 || (w.expected != null && w.spent - w.expected > 0.005);

/** Days in a week span (inclusive), and its Hebrew label. */
export const weekDays = (w: Pick<Week, "start" | "end">) => Math.round((Date.parse(w.end) - Date.parse(w.start)) / 86_400_000) + 1;
export const daysLabel = (n: number) => (n === 1 ? "יום אחד" : `${n} ימים`);

/** Tracked cards with no spending and nothing expected — hidden behind a collapsed row. */
export const isIdle = (c: Pick<TrackedCategory, "spent" | "expected" | "pinned">) => !c.pinned && c.spent === 0 && c.expected === 0;

/** Carousel index with wraparound in both directions; 0 for an empty list. */
export const wrapIndex = (i: number, n: number) => (n <= 0 ? 0 : ((i % n) + n) % n);

export const FIXED_STATUS: Record<FixedItem["status"], { label: string; tone: string }> = {
  charged: { label: "ירד", tone: "bg-brand-soft text-brand" },
  expected: { label: "צפוי", tone: "bg-sunken text-muted" },
  overdue: { label: "לא ירד עדיין", tone: "bg-sun-soft text-text" },
};
export const fixedStatusLabel = (s: FixedItem["status"]) => FIXED_STATUS[s].label;

/** Line under a progress bar: what's left, or by how much it went over. */
export const leftLabel = (spent: number, expected: number) => (spent > expected ? { text: "חריגה של", value: spent - expected, over: true } : { text: "נשאר להוציא", value: expected - spent, over: false });

export type TotalSegment = { key: "fixed" | "variable" | "savings" | "fees"; label: string; spent: number; expected: number; percent: number; tone: string };

/** "סך ההוצאות החודש": per-group spent vs expected, and each group's share of the stacked bar
 * (of whichever is bigger, spent or expected, so the bar never overflows). "משתנות" is the
 * tracked categories plus the rest of variable spending: whatever the total has beyond fixed
 * and savings (the API's total counts each transaction once). */
export function totalSegments(d: Pick<HomeData, "fixed" | "savings" | "total"> & { fees?: HomeData["fees"] }): TotalSegment[] {
  const scale = Math.max(d.total.spent, d.total.expected, 1);
  const seg = (key: TotalSegment["key"], label: string, spent: number, expected: number, tone: string) => ({ key, label, spent, expected, percent: (Math.max(0, spent) / scale) * 100, tone });
  const fees = d.fees ?? { spent: 0, expected: 0 };
  return [
    seg("fixed", "קבועות", d.fixed.spent, d.fixed.expected, "bg-sun"),
    seg("variable", "משתנות", d.total.spent - d.fixed.spent - d.savings.spent - fees.spent, d.total.expected - d.fixed.expected - d.savings.expected - fees.expected, "bg-brand"),
    seg("savings", "חיסכון", d.savings.spent, d.savings.expected, "bg-info"),
    ...(d.fees ? [seg("fees", "עמלות", fees.spent, fees.expected, "bg-danger")] : []),
  ];
}

/** Map every Txn in the home tree (any `transactions` array); return null to drop it. */
export function mapTxns<T>(node: T, fn: (t: Txn) => Txn | null): T {
  if (Array.isArray(node)) return node.map((x) => mapTxns(x, fn)) as T;
  if (!node || typeof node !== "object") return node;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(node)) {
    out[k] = k === "transactions" && Array.isArray(v) ? (v as Txn[]).map(fn).filter((t): t is Txn => t !== null) : mapTxns(v, fn);
  }
  return out as T;
}

export function findTxn(data: HomeData, id: number): Txn | undefined {
  let found: Txn | undefined;
  mapTxns(data, (t) => ((found ??= t.id === id ? t : undefined), t));
  return found;
}

export function formatILS(n: number): string {
  const digits = Number.isInteger(n) ? 0 : 2;
  return new Intl.NumberFormat("he-IL", {
    style: "currency",
    currency: "ILS",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n);
}

const pad = (n: number) => String(n).padStart(2, "0");

/** ISO date or datetime → DD.MM.YY. Date-only strings are not shifted by timezone. */
export function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (m) return `${m[3]}.${m[2]}.${m[1].slice(2)}`;
  const d = new Date(iso);
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${String(d.getFullYear()).slice(2)}`;
}

const HEB_MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"];

/** 1-based month → Hebrew name. */
export const monthName = (m: number) => HEB_MONTHS[m - 1] ?? String(m);

const dm = (iso: string) => {
  const [, m, d] = iso.split("-").map(Number);
  return `${d}.${m}`;
};

/** ("2026-09-10", "2026-10-09") → "ספטמבר 2026 (10.9 עד 9.10)"; label month = start's month. */
export function formatCycleLabel(start: string, end: string): string {
  const [y, m] = start.split("-").map(Number);
  return `${monthName(m)} ${y} (${dm(start)} עד ${dm(end)})`;
}

/** ("2026-10-10", "2026-11-09") → "10.10 – 9.11" (home cycle switcher sub-line). */
export const formatCycleRange = (start: string, end: string) => `${dm(start)} – ${dm(end)}`;

/** Share of the weekly allowance spent, clamped 0–100. No allowance → full bar once anything is spent. */
export function weekBarPercent(spent: number, allowance: number): number {
  if (allowance <= 0) return spent > 0 ? 100 : 0;
  return Math.min(100, Math.max(0, (spent / allowance) * 100));
}

/** Fraction → percent string: 0.1064 → "10.64%"; null → "—". */
export const formatPct = (f: number | null) => (f == null ? "—" : `${(f * 100).toFixed(2)}%`);

/** Tailwind color for a signed return; neutral when unknown. */
export const pctColor = (f: number | null) => (f == null ? "text-muted" : f >= 0 ? "text-positive" : "text-danger");

/** Value already in percent (0.6 → "0.60%"); null → "—". */
export const formatPercentValue = (p: number | null) => (p == null ? "—" : `${p.toFixed(2)}%`);

const CATEGORY_DISPLAY: Record<string, string> = { כלכלה: "סופר" };
export const categoryLabel = (name: string | null | undefined) => (name ? (CATEGORY_DISPLAY[name] ?? name) : "לא מסווג");

/** 1 → "עסקה אחת", 3 → "3 עסקאות" (Hebrew has no "1 עסקאות"). */
export const txnCount = (n: number) => (n === 1 ? "עסקה אחת" : `${n} עסקאות`);

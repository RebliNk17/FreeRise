// Shared chart text helpers (components/charts).

/** Compact money for bar labels: 8645.9 → "8.6K", 950 → "950", -1200 → "-1.2K", 1250000 → "1.3M". */
export function compactMoney(n: number): string {
  const a = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  const fmt = (x: number) => (x >= 100 ? Math.round(x).toString() : x.toFixed(1).replace(/\.0$/, ""));
  if (a >= 1_000_000) return `${sign}${fmt(a / 1_000_000)}M`;
  if (a >= 1000) return `${sign}${fmt(a / 1000)}K`;
  return `${sign}${Math.round(a)}`;
}

/** Which bar the caption describes: the picked one, else the newest (last). -1 when empty. */
export const captionIndex = (n: number, picked: number | null) => (picked != null && picked >= 0 && picked < n ? picked : n - 1);
